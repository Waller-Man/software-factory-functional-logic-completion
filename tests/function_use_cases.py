"""Small function-description and diagram-context checks; no real model or full core."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from reqcompleter_v2_0.protocol import TaskError, Cancelled
from reqcompleter_v2_0.storage import TaskStore
from reqcompleter_v2_1.use_cases import generate_function_use_cases
from reqcompleter_v2_1.hierarchy import generate_diagrams, flatten

FIXTURE = json.loads((ROOT / "tests/v21-fixture.json").read_text(encoding="utf-8"))


class FunctionUseCases(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="req-descriptions-")
        self.addCleanup(self.directory.cleanup)
        self.store = TaskStore(self.directory.name)

    def test_identity_parent_and_saved_flows_reach_activity_prompt(self):
        client = Mock()
        # Model-supplied identity must not replace the function-tree identity.
        replies = [json.dumps({**value, "id": "WRONG", "name": "不应采用的名称"}, ensure_ascii=False)
                   for value in FIXTURE["useCaseFlows"].values()]
        client.complete.side_effect = replies
        cases = generate_function_use_cases(client, self.store, FIXTURE["tree"], FIXTURE["core"])
        self.assertEqual([(c["id"], c["name"]) for c in cases],
                         [(node["id"], node["name"]) for node, *_ in flatten(FIXTURE["tree"])])
        self.assertEqual(cases[1]["parentId"], "F001")
        child_prompt = client.complete.call_args_list[1].args[1]
        self.assertIn('"parentUseCase": {"id": "F001"', child_prompt)
        self.assertIn(FIXTURE["core"]["nonfunctional_requirements"], child_prompt)
        self.assertTrue(self.store.path("intermediate/v2_1/use-cases/F001_01.json").is_file())
        renderer = Mock()
        renderer.render.side_effect = lambda raw, store, prefix: (prefix + ".puml", prefix + ".png")
        client.complete.side_effect = None
        client.complete.return_value = "@startuml\nstart\n:操作;\nstop\n@enduml"
        client.complete.reset_mock()
        diagrams = generate_diagrams(client, self.store, renderer, FIXTURE["tree"], FIXTURE["core"]["software_intro"], cases)
        self.assertEqual(len(diagrams), 4, "The image count and group/leaf split are unchanged")
        activity_prompt = client.complete.call_args_list[2].args[1]
        context = json.loads(activity_prompt[activity_prompt.index('{"systemName"'):])
        self.assertEqual(context["useCase"], cases[1])
        self.assertEqual(context["parentUseCase"], cases[0])
        self.assertIn("返回第1步重新输入", context["useCase"]["alternativeFlows"][0])
        self.assertEqual(diagrams[2]["useCaseId"], "F001_01")

    def test_incomplete_description_retries_with_error_then_fails_without_drawing(self):
        client = Mock()
        client.complete.return_value = '{"mainFlow": []}'
        with self.assertRaises(TaskError) as caught:
            generate_function_use_cases(client, self.store, FIXTURE["tree"], FIXTURE["core"])
        self.assertEqual(caught.exception.code, "INVALID_FUNCTION_USE_CASE")
        self.assertEqual(client.complete.call_count, 3)
        self.assertIn("preconditions", client.complete.call_args_list[1].args[1])
        self.assertTrue(self.store.path("intermediate/v2_1/use-cases/F001.attempt-03.error.json").is_file())

    def test_cancellation_propagates_without_retry(self):
        client = Mock()
        client.complete.side_effect = Cancelled()
        with self.assertRaises(Cancelled):
            generate_function_use_cases(client, self.store, FIXTURE["tree"], FIXTURE["core"])
        self.assertEqual(client.complete.call_count, 1)


if __name__ == "__main__":
    unittest.main()
