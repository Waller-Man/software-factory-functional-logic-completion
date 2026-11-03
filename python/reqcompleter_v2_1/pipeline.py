"""Run the unchanged v2.0 core, then add the v2.1 hierarchy and illustrated output."""
from __future__ import annotations

import io
import json
import zipfile

from reqcompleter_v2_0.pipeline import Pipeline as CorePipeline
from reqcompleter_v2_0.storage import TaskStore
from . import BUSINESS_VERSION, ADAPTER_VERSION
from .document import save_document
from .hierarchy import generate_tree, generate_diagrams
from .render import PlantUML


class CoreStore(TaskStore):
    @staticmethod
    def relative_path(relative):
        # The core's earlier document is inspection material, never a v2.1 final.
        if relative.startswith("final/"):
            return "intermediate/core-v2_0/" + relative[6:]
        return TaskStore.relative_path(relative)


class CoreClient:
    def __init__(self, client):
        self.client = client

    def __getattr__(self, name):
        return getattr(self.client, name)

    def set_step(self, name, iteration=0):
        self.client.set_step("core_document" if name == "save_docx" else name, iteration)

    def emit(self, event_type, **fields):
        if isinstance(fields.get("path"), str):
            fields["path"] = CoreStore.relative_path(fields["path"])
        return self.client.emit(event_type, **fields)


class Pipeline:
    def __init__(self, client, store, max_iterations=5, java_path="java", plantuml_jar=None):
        self.client, self.store = client, store
        self.max_iterations = max_iterations
        self.renderer = PlantUML(java_path, plantuml_jar)

    def run(self, software_intro):
        self.client.set_step("render_environment")
        self.store.write_json("intermediate/v2_1/renderer.json", self.renderer.probe())
        self.client.emit("step", step="render_environment", status="completed")
        core_store = CoreStore(self.store.root)
        core_store.files = self.store.files
        result = CorePipeline(CoreClient(self.client), core_store, self.max_iterations).run(software_intro)
        # The core converges exactly as before; the following steps only change delivery.
        tree = generate_tree(self.client, self.store, result)
        diagrams = generate_diagrams(self.client, self.store, self.renderer, tree, software_intro)
        result.update({"business_version": BUSINESS_VERSION, "adapter_version": ADAPTER_VERSION,
                       "functional_tree": tree, "diagrams": diagrams, "diagram_status": "generated",
                       "document_status": "pending"})
        self.store.write_json("final/functional-tree.json", tree)
        self.client.set_step("save_docx")
        result["docx_path"] = save_document(self.store, result)
        result["document_status"] = "succeeded"
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as package:
            package.write(self.store.path("final/functional-tree.json"), "functional-tree.json")
            package.writestr("index.json", json.dumps([
                {**entry, **{key: entry[key].removeprefix("intermediate/v2_1/diagrams/")
                            for key in ("source", "image")}} for entry in diagrams
            ], ensure_ascii=False, indent=2))
            for entry in diagrams:
                for key in ("source", "image"):
                    relative = entry[key]
                    package.write(self.store.path(relative), relative.removeprefix("intermediate/v2_1/diagrams/"))
        self.store.write_bytes("final/diagrams.zip", archive.getvalue())
        result["files"] = sorted(self.store.files | {"final/result.json"})
        self.store.write_json("final/result.json", result)
        self.client.emit("step", step="save_docx", status="completed")
        self.client.emit("artifact", path=result["docx_path"], kind="requirements_docx")
        return result
