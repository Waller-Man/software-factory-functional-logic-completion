"""Task-local, atomic artifact storage. No plugin-directory output defaults."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
from pathlib import Path
from uuid import uuid4


def json_value(value):
    """Serialize business state explicitly, including DataFrames and sets."""
    if hasattr(value, "columns") and hasattr(value, "index") and hasattr(value, "to_numpy"):
        return {
            "indexName": value.index.name or "useCase",
            "index": [str(item) for item in value.index],
            "columns": [str(item) for item in value.columns],
            "data": [[str(cell) for cell in row] for row in value.fillna("").to_numpy().tolist()],
        }
    if isinstance(value, dict):
        return {str(key): json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(item) for item in value]
    if isinstance(value, set):
        return [json_value(item) for item in sorted(value)]
    if isinstance(value, Path):
        return str(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"Unsupported business state type: {type(value).__name__}")


class TaskStore:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.files = set()

    @staticmethod
    def relative_path(relative):
        # Run reserves intermediate/ and snapshots/ for downloadable materials.
        # Keep the algorithm's logical names; change only their physical storage.
        if relative.startswith("initial/"):
            return "intermediate/" + relative
        if relative.startswith("iterations/"):
            return "snapshots/" + relative
        return relative

    def path(self, relative):
        relative = self.relative_path(relative)
        target = (self.root / relative).resolve()
        if target == self.root or self.root not in target.parents:
            raise ValueError("Artifact path must stay within task output directory")
        target.parent.mkdir(parents=True, exist_ok=True)
        return target

    def write_bytes(self, relative, content):
        target = self.path(relative)
        temporary = None
        try:
            # A single exclusive create fails promptly on denied Windows ACLs.
            # tempfile retries PermissionError on Windows and can spin for hours.
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
            candidate = target.with_name(".pending-" + uuid4().hex)
            descriptor = os.open(candidate, flags, 0o600)
            temporary = candidate
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
        finally:
            if temporary and temporary.exists():
                temporary.unlink()
        self.files.add(str(target.relative_to(self.root)).replace("\\", "/"))
        return target

    def write_text(self, relative, content):
        return self.write_bytes(relative, str(content).encode("utf-8"))

    def write_json(self, relative, content):
        return self.write_text(relative, json.dumps(json_value(content), ensure_ascii=False, indent=2, allow_nan=False) + "\n")

    def event(self, content):
        target = self.path("logs/events.jsonl")
        with target.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(json_value(content), ensure_ascii=False, allow_nan=False) + "\n")
            stream.flush()
        self.files.add("logs/events.jsonl")

    def matrix(self, relative, matrix):
        value = json_value(matrix)
        self.write_json(relative + ".json", value)
        stream = io.StringIO(newline="")
        writer = csv.writer(stream)
        writer.writerow([value["indexName"]] + value["columns"])
        for index, row in zip(value["index"], value["data"]):
            writer.writerow([index] + row)
        self.write_text(relative + ".csv", stream.getvalue())

    def index(self):
        return [
            {"path": relative, "size": self.path(relative).stat().st_size,
             "sha256": hashlib.sha256(self.path(relative).read_bytes()).hexdigest()}
            for relative in sorted(self.files)
        ]
