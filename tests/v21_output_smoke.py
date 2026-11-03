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
from reqcompleter_v2_0.protocol import ModelClient, TaskError
from reqcompleter_v2_0.storage import TaskStore
from reqcompleter_v2_1.hierarchy import validate_tree
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


if __name__ == "__main__":
    unittest.main()
