"""Synthetic algorithm for the Run entry smoke. Never runs the real Pipeline."""
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
import worker
import reqcompleter_v2_0.pipeline as pipeline
from reqcompleter_v2_0.protocol import read_message
from docx import Document
import io


class StubPipeline:
    def __init__(self, client, store, max_iterations):
        self.client, self.store = client, store

    def run(self, intro):
        if intro == "errors-unwritable":
            self.store.path("logs/error.json").mkdir()
            self.store.path("logs/stderr.log").mkdir()
            manifest = self.store.root / "manifest.json"
            manifest.unlink()
            manifest.mkdir()
            raise RuntimeError("fixture primary failure")
        self.store.write_json("initial/entities.json", ["synthetic_test"])
        self.store.write_json("iterations/001/before.json", {"synthetic_test": True})
        self.client.set_step("extract_entities")
        if intro == "cancel":
            # Block on the existing protocol; cancellation must stop this process.
            read_message(sys.stdin)
            raise RuntimeError("cancelled fixture must not complete")
        answer = self.client.complete("ExtraTest", intro)
        self.client.emit("step", step="extract_entities", status="completed", path="initial/entities.json")
        document = Document()
        document.add_paragraph("synthetic_test: " + answer)
        content = io.BytesIO()
        document.save(content)
        self.store.write_bytes("final/requirements.docx", content.getvalue())
        self.store.write_json("iterations/001/after.json", {"synthetic_test": True})
        result = {"synthetic_test": True, "iterations": 1, "converged": False,
                  "reached_iteration_limit": False, "docx_path": "final/requirements.docx"}
        self.store.write_json("final/result.json", result)
        return result


pipeline.Pipeline = StubPipeline
if __name__ == "__main__":
    if os.environ.get("REQ_TEST_STALL_STARTUP") == "1":
        sys.stdin.read()
    else:
        raise SystemExit(worker.main())
