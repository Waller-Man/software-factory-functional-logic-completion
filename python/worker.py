"""DSH ReqCompleter task worker. Never invokes a model provider directly."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib
import importlib.metadata
import json
import os
from pathlib import Path
import signal
import sys
from uuid import uuid4
import zipfile

from reqcompleter_v2_0 import ADAPTER_VERSION, BUSINESS_VERSION, SOURCE_SHA256
from reqcompleter_v2_0.protocol import Cancelled, ModelClient, TaskError, read_message
from reqcompleter_v2_0.storage import TaskStore


def probe():
    dependencies = {}
    ready = sys.version_info >= (3, 10)
    expected = {"pandas": "2.2.3", "python-docx": "1.1.2"}
    for module_name, distribution in (("pandas", "pandas"), ("docx", "python-docx")):
        try:
            importlib.import_module(module_name)
            version = importlib.metadata.version(distribution)
            matches = version == expected[distribution]
            dependencies[distribution] = {"available": True, "version": version,
                                          "expectedVersion": expected[distribution], "matchesLock": matches}
            ready = ready and matches
        except (ImportError, OSError, ValueError) as error:
            dependencies[distribution] = {"available": False, "error": type(error).__name__}
            ready = False
    return {"protocolVersion": 1, "ready": ready,
            "python": {"version": sys.version.split()[0], "executable": sys.executable,
                       "minimum": "3.10", "recommended": "3.12"},
            "dependencies": dependencies, "businessVersion": BUSINESS_VERSION,
            "adapterVersion": ADAPTER_VERSION, "sourceSha256": SOURCE_SHA256}


def archive(output_dir):
    store = TaskStore(output_dir)
    destination = store.path("final/checks.zip")
    temporary = None
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
        candidate = destination.with_name(".pending-" + uuid4().hex)
        descriptor = os.open(candidate, flags, 0o600)
        temporary = candidate
        with os.fdopen(descriptor, "wb"):
            pass
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as package:
            for source in sorted(store.root.rglob("*")):
                if not source.is_file() or source.is_symlink():
                    continue
                relative = source.relative_to(store.root).as_posix()
                if (relative in ("run.json", "final/checks.zip", "final/requirements.docx")
                        or any(part.startswith((".pending-", ".tmp")) for part in source.relative_to(store.root).parts)
                        or source.name.endswith((".partial", ".tmp"))):
                    continue
                if store.root not in source.resolve().parents:
                    continue
                package.write(source, relative)
        with zipfile.ZipFile(temporary) as package:
            if package.testzip():
                raise TaskError("ARCHIVE_FAILED", "Generated checks archive is invalid")
        os.replace(temporary, destination)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()
    return {"path": "final/checks.zip"}


def validate_start(message):
    if message.get("type") != "start" or message.get("protocolVersion") != 1:
        raise TaskError("PROTOCOL_ERROR", "First message must be a protocol version 1 start request")
    run_id = message.get("runId")
    if not isinstance(run_id, str) or not run_id or len(run_id) > 128:
        raise TaskError("INVALID_INPUT", "runId must be a nonempty string up to 128 characters")
    intro = message.get("software_intro")
    if not isinstance(intro, str) or not intro.strip() or len(intro) > 200000:
        raise TaskError("INVALID_INPUT", "software_intro must contain 1 to 200000 characters")
    iterations = message.get("max_iterations", 5)
    if isinstance(iterations, bool) or not isinstance(iterations, int) or not 1 <= iterations <= 20:
        raise TaskError("INVALID_INPUT", "max_iterations must be an integer from 1 to 20")
    output_dir = message.get("output_dir")
    if not isinstance(output_dir, str) or not Path(output_dir).is_absolute():
        raise TaskError("INVALID_INPUT", "output_dir must be an absolute host task directory")
    return {"runId": run_id, "software_intro": intro, "max_iterations": iterations,
            "output_dir": output_dir}


def run_worker():
    client, store = None, None
    run_id = "unknown"
    try:
        start = read_message(sys.stdin)
        if isinstance(start.get("runId"), str):
            run_id = start["runId"]
        config = validate_start(start)
        store = TaskStore(config["output_dir"])
        try:
            # Exclusive creation prevents two processes from claiming one run directory.
            with store.path("input/worker-claim.json").open("x", encoding="utf-8") as claim:
                json.dump({"runId": run_id}, claim)
            store.files.add("input/worker-claim.json")
        except FileExistsError as caught:
            raise TaskError("TASK_DIRECTORY_EXISTS", "Task output directory is already claimed") from caught
        client = ModelClient(run_id, store)
        store.write_json("input/reqcompleter-request.json", {
            "protocolVersion": 1, "runId": run_id, "software_intro": config["software_intro"],
            "max_iterations": config["max_iterations"], "business_version": BUSINESS_VERSION,
            "adapter_version": ADAPTER_VERSION, "source_sha256": SOURCE_SHA256,
        })
        store.write_text("input/software-intro.txt", config["software_intro"])
        client.emit("step", step="starting", iteration=0, status="completed")
        from reqcompleter_v2_0.pipeline import Pipeline
        result = Pipeline(client, store, config["max_iterations"]).run(config["software_intro"])
        result["files"] = sorted(store.files)
        store.write_json("final/result.json", result)
        # TS creates the checks archive once, after writing the business manifest.
        client.emit("final", result=result)
        return 0
    except KeyboardInterrupt:
        error = Cancelled()
    except TaskError as caught:
        error = caught
    except Exception as caught:
        # Dependency/code faults remain failures and never become business text.
        error = TaskError("PYTHON_ERROR", f"{type(caught).__name__}: {caught}")
    payload = {"code": error.code, "message": str(error), "stage": client.stage if client else "startup",
               "iteration": client.iteration if client else 0,
               "time": datetime.now(timezone.utc).isoformat()}
    try:
        if store:
            store.write_json("logs/error.json", payload)
    except Exception as logging_error:
        print(f"[{run_id}] Error file unavailable: {type(logging_error).__name__}: {logging_error}",
              file=sys.stderr, flush=True)
    # Error delivery must not depend on TaskStore or ModelClient.emit's event log.
    try:
        print(json.dumps({"type": "error", "protocolVersion": 1, "runId": run_id, "error": payload}, ensure_ascii=False), flush=True)
    finally:
        print(f"[{run_id}] {error.code}: {error}", file=sys.stderr, flush=True)
    return 130 if error.code == "CANCELLED" else 1


def main():
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", action="store_true")
    parser.add_argument("--archive", metavar="OUTPUT_DIR")
    options = parser.parse_args()
    if options.probe:
        result = probe()
        print(json.dumps(result, ensure_ascii=False), flush=True)
        return 0 if result["ready"] else 2
    if options.archive:
        try:
            print(json.dumps(archive(options.archive), ensure_ascii=False), flush=True)
            return 0
        except Exception as error:
            print(json.dumps({"error": {"code": "ARCHIVE_FAILED", "message": str(error)}}, ensure_ascii=False), flush=True)
            return 1
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(Cancelled()))
    return run_worker()


if __name__ == "__main__":
    raise SystemExit(main())
