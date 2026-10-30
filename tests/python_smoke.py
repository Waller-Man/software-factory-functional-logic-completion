"""Small offline entry/protocol checks. Does not run the ReqCompleter pipeline."""
import io
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from reqcompleter_v2_0.crud import parse_crud_triplets, programmatic_crud_gap_detection, parse_llm_gap_response, name_list
from reqcompleter_v2_0.protocol import ModelClient, TaskError, Cancelled
from reqcompleter_v2_0.storage import TaskStore
from worker import archive, validate_start


class EntrySmoke(unittest.TestCase):
    def test_original_empty_crud_returns_no_actionable_gaps(self):
        complete, gaps = programmatic_crud_gap_detection([], ["订单"])
        self.assertFalse(complete)
        self.assertEqual(gaps, [])

    def test_original_combined_operations_are_not_split(self):
        triples = parse_crud_triplets('[("订单", "管理订单", "CRUD")]')
        self.assertEqual(triples, [("订单", "管理订单", "CRUD")])
        self.assertFalse(programmatic_crud_gap_detection(triples, ["订单"])[0])

    def test_original_checker_parse_failure_allows_programmatic_fallback(self):
        self.assertIsNone(parse_llm_gap_response("not JSON"))
        self.assertEqual(parse_llm_gap_response('说明：{"status":"complete","missing":[]} 结束'), {"status": "complete", "missing": []})

    def test_original_parsing_preserves_duplicates_and_regex_fallback(self):
        self.assertEqual(name_list("订单、订单,客户\n管理员，图书"), ["订单", "订单", "客户\n管理员，图书"])
        self.assertEqual(parse_crud_triplets('新增内容：("订单", "新增订单", "c")'), [("订单", "新增订单", "C")])

    def test_original_business_methods_and_helpers_match_source_fingerprints(self):
        fixture = json.loads((ROOT / "tests/original-v2_0-fingerprints.json").read_text(encoding="utf-8"))
        def fingerprints(path):
            return {node.name: hashlib.sha256(ast.dump(node, include_attributes=False).encode("utf-8")).hexdigest()
                    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))) if isinstance(node, ast.FunctionDef)}
        for filename, expected in fixture["modules"].items():
            actual = fingerprints(ROOT / "python/reqcompleter_v2_0" / filename)
            for name, digest in expected.items():
                self.assertEqual(actual[name], digest, f"{filename}:{name} differs from original business code")
        actual = fingerprints(ROOT / "python/reqcompleter_v2_0/crud.py")
        for name, digest in fixture["helpers"].items():
            self.assertEqual(actual[name], digest, f"CRUD helper {name} differs from original")

    def test_model_bridge_one_fake_request(self):
        # A single transport round trip, not a fake end-to-end business run.
        with tempfile.TemporaryDirectory(dir=ROOT / "python") as directory:
            output = io.StringIO()
            input_stream = io.StringIO(json.dumps({"type": "model_response", "id": "m000001", "result": {"text": "离线回复"}}) + "\n")
            client = ModelClient("smoke", TaskStore(directory), input_stream, output)
            self.assertEqual(client.complete("ExtraTest", "入口探测"), "离线回复")
            event = json.loads(output.getvalue())
            self.assertEqual(event["type"], "model_request")
            self.assertEqual(len(event["messages"]), 2)
            self.assertEqual(event["runId"], "smoke")

    def test_bridge_preserves_all_original_system_instructions(self):
        systems = json.loads((ROOT / "tests/original-v2_0-fingerprints.json").read_text(encoding="utf-8"))["systems"]
        responses = ''.join(json.dumps({"type": "model_response", "id": f"m{index:06d}", "result": {"text": "offline"}}) + '\n'
                            for index in range(1, len(systems) + 1))
        with tempfile.TemporaryDirectory(dir=ROOT / "python") as directory:
            output = io.StringIO()
            client = ModelClient("systems", TaskStore(directory), io.StringIO(responses), output)
            for module in systems:
                client.complete(module, "explicit input")
            for line in output.getvalue().splitlines():
                event = json.loads(line)
                self.assertEqual(event["messages"], [{"role": "system", "content": systems[event["module"]]}, {"role": "user", "content": "explicit input"}])

    def test_model_error_and_cancel_propagate(self):
        for response, error_type in (({"type": "cancel"}, Cancelled),
                                     ({"type": "model_response", "id": "m000001", "error": {"code": "DENIED", "message": "blocked"}}, TaskError)):
            with tempfile.TemporaryDirectory(dir=ROOT / "python") as directory:
                client = ModelClient("smoke", TaskStore(directory), io.StringIO(json.dumps(response) + "\n"), io.StringIO())
                with self.assertRaises(error_type):
                    client.complete("ExtraTest", "入口探测")

    def test_start_validation_and_no_demo_fallback(self):
        with self.assertRaises(TaskError):
            validate_start({"type": "start", "protocolVersion": 1, "runId": "smoke", "software_intro": "", "output_dir": str(ROOT)})

    def test_archive_is_local_and_excludes_docx_pending(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "python") as directory:
            store = TaskStore(directory)
            store.write_text("input/software-intro.txt", "入口探测")
            store.write_text("manifest.json", "{}")
            store.write_text("final/requirements.docx", "not a real document")
            store.write_text("final/stale.partial", "unfinished")
            self.assertEqual(archive(directory), {"path": "final/checks.zip"})
            with zipfile.ZipFile(Path(directory) / "final/checks.zip") as package:
                self.assertIn("manifest.json", package.namelist())
                self.assertIn("input/software-intro.txt", package.namelist())
                self.assertNotIn("final/requirements.docx", package.namelist())
                self.assertNotIn("final/stale.partial", package.namelist())

    def test_worker_rejects_invalid_start_without_business(self):
        process = subprocess.run([sys.executable, str(ROOT / "python/worker.py")], input='{"type":"invalid"}\n', capture_output=True, text=True, encoding="utf-8")
        self.assertNotEqual(process.returncode, 0)
        self.assertEqual(json.loads(process.stdout)["error"]["code"], "PROTOCOL_ERROR")


if __name__ == "__main__":
    unittest.main()
