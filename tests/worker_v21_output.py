"""Only the expensive core is substituted; v2.1 model bridge/render/export are real."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
import worker_v2_1
from reqcompleter_v2_0.pipeline import Pipeline as Core, save_document


def synthetic_core(self, intro):
    result = json.loads((ROOT / "tests/v21-fixture.json").read_text(encoding="utf-8"))["core"]
    result["software_intro"] = intro
    self.store.write_json("initial/entities.json", result["data_entities"])
    self.store.write_json("iterations/001/before.json", result)
    self.store.write_json("iterations/001/after.json", result)
    result["docx_path"] = save_document(self.store, result)
    result["document_status"] = "succeeded"
    self.store.write_json("final/result.json", result)
    # Keep the real core's completion boundary in mocked Run/output tests.
    self.client.emit("artifact", path=result["docx_path"], kind="requirements_docx")
    return result


Core.run = synthetic_core
if __name__ == "__main__":
    raise SystemExit(worker_v2_1.main())
