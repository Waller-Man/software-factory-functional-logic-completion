"""One worker, one task; JSONL stdout is reserved for host protocol events."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import sys


class TaskError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class Cancelled(TaskError):
    def __init__(self, message="Task cancelled by host"):
        super().__init__("CANCELLED", message)


def read_message(stream):
    # Host also limits bytes; avoid accepting an unbounded line from a broken peer.
    line = stream.readline(8 * 1024 * 1024 + 1)
    if not line:
        raise TaskError("HOST_CLOSED", "Host closed the protocol input")
    if len(line) > 8 * 1024 * 1024:
        raise TaskError("PROTOCOL_ERROR", "Protocol message exceeds 8 MiB")
    try:
        value = json.loads(line)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise TaskError("PROTOCOL_ERROR", "Protocol input is not valid JSON") from error
    if not isinstance(value, dict):
        raise TaskError("PROTOCOL_ERROR", "Protocol message must be an object")
    return value


class ModelClient:
    def __init__(self, run_id, store, input_stream=None, output_stream=None):
        self.run_id = run_id
        self.store = store
        self.input = input_stream or sys.stdin
        self.output = output_stream or sys.stdout
        self.stage = "initial"
        self.iteration = 0
        self.counter = 0

    def emit(self, event_type, **fields):
        if isinstance(fields.get("path"), str):
            fields["path"] = self.store.relative_path(fields["path"])
        value = {"type": event_type, "protocolVersion": 1, "runId": self.run_id, **fields}
        self.output.write(json.dumps(value, ensure_ascii=False, allow_nan=False) + "\n")
        self.output.flush()
        self.store.event({"time": datetime.now(timezone.utc).isoformat(), **value})
        return value

    def set_step(self, stage, iteration=0):
        self.stage, self.iteration = stage, iteration
        self.emit("step", step=stage, iteration=iteration, status="running")

    def complete(self, module, prompt):
        self.counter += 1
        request_id = f"m{self.counter:06d}"
        # Preserve module boundaries: the original modules sent system + current prompt,
        # not their accumulated self.memory. Never import a host chat history here.
        system = "You are an AI assistant." if module == "UC_Agent" else "你是人工智能助手"
        if module == "ExtraTest":
            system = "You are an requirement engineering expert"
        messages = [{"role": "system", "content": system}, {"role": "user", "content": prompt}]
        request = {"id": request_id, "stage": self.stage, "iteration": self.iteration,
                   "module": module, "messages": messages}
        self.store.write_json(f"intermediate/model/{request_id}.request.json", request)
        self.emit("model_request", **request)
        response = read_message(self.input)
        if response.get("type") == "cancel":
            raise Cancelled()
        if response.get("type") != "model_response" or response.get("id") != request_id:
            raise TaskError("PROTOCOL_ERROR", "Model response does not match the pending request")
        if response.get("runId") not in (None, self.run_id):
            raise TaskError("PROTOCOL_ERROR", "Model response belongs to another task")
        if response.get("error"):
            error = response["error"]
            if not isinstance(error, dict):
                raise TaskError("PROTOCOL_ERROR", "Model error must be structured")
            safe_error = {"code": str(error.get("code", "MODEL_ERROR")),
                          "message": str(error.get("message", "Host model request failed"))}
            self.store.write_json(f"intermediate/model/{request_id}.error.json", safe_error)
            raise TaskError(safe_error["code"], safe_error["message"])
        result = response.get("result")
        text = result.get("text") if isinstance(result, dict) else None
        if not isinstance(text, str) or not text.strip():
            raise TaskError("INVALID_MODEL_OUTPUT", "Host returned no visible model text")
        self.store.write_json(f"intermediate/model/{request_id}.response.json", {"text": text})
        return text.strip()
