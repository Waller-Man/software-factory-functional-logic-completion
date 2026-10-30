"""Small storage/startup regressions; no business pipeline or model calls."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
import worker
from reqcompleter_v2_0.storage import TaskStore


class StartupErrors(unittest.TestCase):
    def test_denied_atomic_write_does_not_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            store = TaskStore(directory)
            with patch("os.open", side_effect=PermissionError("write denied")) as create:
                with self.assertRaises(PermissionError):
                    store.write_json("logs/error.json", {"error": "test"})
                self.assertEqual(create.call_count, 1)

    def test_denied_error_file_still_reports_original_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            start = {"type": "start", "protocolVersion": 1, "runId": "denied-test",
                     "software_intro": "synthetic", "max_iterations": 1, "output_dir": directory}
            output, errors = io.StringIO(), io.StringIO()
            with patch.object(sys, "stdin", io.StringIO(json.dumps(start) + "\n")), \
                    contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors), \
                    patch.object(Path, "open", side_effect=PermissionError("claim denied")), \
                    patch("os.open", side_effect=PermissionError("error log denied")):
                status = worker.run_worker()
            self.assertEqual(status, 1)
            event = json.loads(output.getvalue())
            self.assertEqual(event["type"], "error")
            self.assertEqual(event["runId"], "denied-test")
            self.assertIn("claim denied", event["error"]["message"])
            self.assertIn("error log denied", errors.getvalue())

    def test_denied_archive_does_not_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("os.open", side_effect=PermissionError("archive denied")) as create:
                with self.assertRaises(PermissionError):
                    worker.archive(directory)
                self.assertEqual(create.call_count, 1)


if __name__ == "__main__":
    unittest.main()
