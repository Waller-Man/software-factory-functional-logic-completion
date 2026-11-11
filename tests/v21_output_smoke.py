"""Small mocked-model/local-Java output verification; no full ReqCompleter run."""
from copy import deepcopy
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from uuid import uuid4
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from docx import Document
from reqcompleter_v2_0.pipeline import Pipeline as Core, save_document as save_core_document
from reqcompleter_v2_0.protocol import ModelClient, TaskError, Cancelled
from reqcompleter_v2_0.storage import TaskStore
from reqcompleter_v2_1.hierarchy import validate_tree, generate_diagrams
from reqcompleter_v2_1.pipeline import Pipeline, CoreClient, CoreStore
from reqcompleter_v2_1.render import PlantUML
from worker_v21_output import synthetic_core

FIXTURE = json.loads((ROOT / "tests/v21-fixture.json").read_text(encoding="utf-8"))
USE_CASE = '@startuml\nactor 管理员\nrectangle 商品系统 {\nusecase "商品增加" as UC1\n管理员 --> UC1\n}\n@enduml'
ACTIVITY = '@startuml\nstart\n:录入商品信息;\nif (信息有效?) then (是)\n:保存商品;\nelse (否)\n:提示修正;\nendif\nstop\n@enduml'


class OutputSmoke(unittest.TestCase):
    def test_core_document_artifact_notification_preserves_kind_and_redirects_path(self):
        store = CoreStore(ROOT / "test-results" / ("v21-core-event-" + uuid4().hex))
        output = io.StringIO()
        client = ModelClient("core-event-regression", store, io.StringIO(), output)
        adapter = CoreClient(client)
        result = deepcopy(FIXTURE["core"])
        adapter.set_step("save_docx", 1)
        docx_path = save_core_document(store, result)
        # Exact notification emitted by the unchanged core after DOCX creation.
        adapter.emit("artifact", path=docx_path, kind="requirements_docx")
        events = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(events[-1]["type"], "artifact")
        self.assertEqual(events[-1]["kind"], "requirements_docx")
        self.assertEqual(events[-1]["path"], "intermediate/core-v2_0/requirements.docx")
        self.assertEqual(events[0]["step"], "core_document")
        self.assertEqual(client.counter, 0, "Regression must not call a model")
        self.assertTrue((store.root / events[-1]["path"]).is_file())
        self.assertFalse((store.root / "final/requirements.docx").exists())

    def test_tree_rejects_duplicate_identifiers(self):
        tree = deepcopy(FIXTURE["tree"])
        tree["functions"][0]["children"][0]["id"] = "F001"
        with self.assertRaises(TaskError):
            validate_tree(tree)

    def test_real_pngs_embedded_in_docx_and_zip_index_resolves(self):
        directory = ROOT / "test-results" / ("v21-output-" + uuid4().hex)
        store = TaskStore(directory)
        replies = [json.dumps(FIXTURE["tree"], ensure_ascii=False), USE_CASE, USE_CASE, ACTIVITY, ACTIVITY]
        responses = ''.join(json.dumps({"type":"model_response", "id":f"m{index:06d}", "result":{"text":text}}, ensure_ascii=False)+'\n'
                            for index,text in enumerate(replies,1))
        output = io.StringIO()
        client = ModelClient("v21-offline", store, io.StringIO(responses), output)
        with patch.object(Core, "run", synthetic_core):
            result = Pipeline(client, store).run(FIXTURE["core"]["software_intro"])
        self.assertEqual(result["business_version"], "2.1")
        self.assertEqual(result["diagram_status"], "generated")
        self.assertFalse(result["converged"])
        self.assertEqual(len(result["diagrams"]), 4)
        document = Document(store.path(result["docx_path"]))
        self.assertEqual(len(document.inline_shapes), 4)
        self.assertTrue(any("保存商品" in paragraph.text for paragraph in document.paragraphs))
        self.assertEqual([entry["kind"] for entry in result["diagrams"]].count("activity"), 2)
        with zipfile.ZipFile(store.path("final/diagrams.zip")) as package:
            entries = json.loads(package.read("index.json"))
            for entry in entries:
                self.assertIn(entry["source"], package.namelist())
                self.assertTrue(package.read(entry["image"]).startswith(b"\x89PNG"))
        events = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(len([event for event in events if event["type"] == "model_request"]), 5)
        print(f"Illustrated sample: {store.path(result['docx_path'])}")

    def test_invalid_ai_source_preserved_and_render_failure_is_not_success(self):
        store = TaskStore(ROOT / "test-results" / ("v21-invalid-" + uuid4().hex))
        renderer = PlantUML()
        fenced = "```plantuml\n" + USE_CASE + "\n```"
        with self.assertRaises(TaskError) as caught:
            renderer.render(fenced, store, "intermediate/invalid/fenced")
        self.assertEqual(caught.exception.code, "INVALID_DIAGRAM")
        self.assertEqual(store.path("intermediate/invalid/fenced.puml").read_text(encoding="utf-8"), fenced)
        with self.assertRaises(TaskError):
            renderer.render("@startuml\nthis is definitely invalid diagram syntax !!!\n@enduml", store, "intermediate/invalid/syntax")
        self.assertFalse((store.root / "intermediate/invalid/syntax.png").exists())


class DiagramTolerance(unittest.TestCase):
    def run_sample(self, replies):
        store = TaskStore(ROOT / "test-results" / ("v21-tolerance-" + uuid4().hex))
        responses = "".join(json.dumps({"type": "model_response", "id": f"m{i:06d}",
                                       "result": {"text": text}}, ensure_ascii=False) + "\n"
                            for i, text in enumerate([json.dumps(FIXTURE["tree"], ensure_ascii=False), *replies], 1))
        output = io.StringIO()
        client = ModelClient("v21-tolerance", store, io.StringIO(responses), output)
        with patch.object(Core, "run", synthetic_core):
            result = Pipeline(client, store).run(FIXTURE["core"]["software_intro"])
        return result, store, [json.loads(line) for line in output.getvalue().splitlines()]

    def test_format_and_render_errors_corrected_with_original_attempts_retained(self):
        missing_end = ACTIVITY.removesuffix("\n@enduml")
        bad_syntax = "@startuml\nthis is definitely invalid diagram syntax !!!\n@enduml"
        result, store, events = self.run_sample([USE_CASE, USE_CASE, missing_end, bad_syntax, ACTIVITY, ACTIVITY])
        self.assertEqual(result["diagram_status"], "generated")
        self.assertEqual(result["diagram_failures"], [])
        entry = next(e for e in result["diagrams"] if e["nodeId"] == "F001_01")
        self.assertEqual(len(entry["attempts"]), 3)
        self.assertEqual([a["status"] for a in entry["attempts"]], ["failed", "failed", "generated"])
        self.assertEqual(store.path(entry["attempts"][0]["source"]).read_text(encoding="utf-8"), missing_end)
        requests = [e for e in events if e["type"] == "model_request"]
        self.assertEqual(len(requests), 7)
        self.assertIn("末行缺少", requests[4]["messages"][1]["content"])
        self.assertIn("DIAGRAM_RENDER_FAILED", requests[5]["messages"][1]["content"])
        self.assertIn("previousSource", requests[4]["messages"][1]["content"])
        self.assertEqual(len(Document(store.path(result["docx_path"])).inline_shapes), 4)
        for attempt in entry["attempts"][:2]:
            self.assertTrue(store.path(attempt["errorPath"]).is_file())

    def test_exhausted_system_and_leaf_diagrams_skipped_but_later_images_docx_and_zip_complete(self):
        invalid = ACTIVITY.removesuffix("\n@enduml")
        result, store, events = self.run_sample([invalid] * 3 + [USE_CASE] + [invalid] * 3 + [ACTIVITY])
        self.assertEqual(result["diagram_status"], "partial")
        self.assertEqual(result["document_status"], "succeeded")
        self.assertEqual([e["nodeId"] for e in result["diagram_failures"]], ["SYSTEM", "F001_01"])
        self.assertTrue(all(len(e["attempts"]) == 3 for e in result["diagram_failures"]))
        self.assertEqual(len([e for e in events if e["type"] == "model_request"]), 9)
        self.assertEqual(result["diagrams"][-1]["status"], "generated")
        document = Document(store.path(result["docx_path"]))
        self.assertEqual(len(document.inline_shapes), 2)
        text = "\n".join(p.text for p in document.paragraphs)
        self.assertEqual(text.count("本节图未生成"), 2)
        self.assertIn("录入商品名称、价格，检查必填项。", text)
        self.assertIn("部分图缺失", text)
        with zipfile.ZipFile(store.path("final/diagrams.zip")) as package:
            for entry in json.loads(package.read("index.json")):
                self.assertIn(entry["source"], package.namelist())
                if entry["status"] == "skipped":
                    self.assertNotIn("image", entry)
                else:
                    self.assertIn(entry["image"], package.namelist())
                for attempt in entry["attempts"]:
                    self.assertIn(attempt["source"], package.namelist())
                    if attempt.get("errorPath"):
                        self.assertIn(attempt["errorPath"], package.namelist())

    def test_model_cancellation_is_not_retried_or_skipped(self):
        from unittest.mock import Mock
        client = Mock()
        client.complete.side_effect = Cancelled()
        store = TaskStore(ROOT / "test-results" / ("v21-cancel-" + uuid4().hex))
        with self.assertRaises(Cancelled):
            generate_diagrams(client, store, PlantUML(), FIXTURE["tree"], "small input")
        self.assertEqual(client.complete.call_count, 1)

    def test_environment_failure_is_not_retried_or_skipped(self):
        from unittest.mock import Mock
        client, renderer = Mock(), Mock()
        client.complete.return_value = USE_CASE
        renderer.render.side_effect = TaskError("JAVA_NOT_READY", "Java unavailable")
        store = TaskStore(ROOT / "test-results" / ("v21-environment-" + uuid4().hex))
        with self.assertRaises(TaskError) as caught:
            generate_diagrams(client, store, renderer, FIXTURE["tree"], "small input")
        self.assertEqual(caught.exception.code, "JAVA_NOT_READY")
        self.assertEqual(client.complete.call_count, 1)


if __name__ == "__main__":
    unittest.main()
