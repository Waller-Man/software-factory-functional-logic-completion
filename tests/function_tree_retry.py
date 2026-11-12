"""Function-tree validation retry checks only; no full pipeline, Java or real models."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'python'))
from reqcompleter_v2_0.protocol import TaskError, Cancelled
from reqcompleter_v2_0.storage import TaskStore
from reqcompleter_v2_1.hierarchy import generate_tree

FIXTURE = json.loads((ROOT / 'tests/v21-fixture.json').read_text(encoding='utf-8'))

class TreeRetry(unittest.TestCase):
    def store(self):
        directory = tempfile.TemporaryDirectory(prefix='req-tree-')
        self.addCleanup(directory.cleanup)
        return TaskStore(directory.name)

    def test_syntax_and_structure_errors_repaired_on_last_attempt(self):
        client = Mock()
        broken = '{"functions":[{"id":"F013_04","children":[]]}'
        client.complete.side_effect = [broken, '{}', json.dumps(FIXTURE['tree'], ensure_ascii=False)]
        store = self.store()
        self.assertEqual(generate_tree(client, store, FIXTURE['core']), FIXTURE['tree'])
        self.assertEqual(client.complete.call_count, 3)
        self.assertIn('字符位置', client.complete.call_args_list[1].args[1])
        self.assertIn('非空功能列表', client.complete.call_args_list[2].args[1])
        self.assertEqual(store.path('intermediate/v2_1/function-tree.attempt-01.raw.txt').read_text(encoding='utf-8'), broken)
        self.assertTrue(store.path('intermediate/v2_1/function-tree.attempt-02.error.json').is_file())

    def test_three_invalid_attempts_fail_with_all_evidence_saved(self):
        client = Mock();client.complete.return_value = '{}';store = self.store()
        with self.assertRaises(TaskError) as caught:generate_tree(client, store, FIXTURE['core'])
        self.assertEqual(caught.exception.code, 'INVALID_FUNCTION_TREE')
        self.assertEqual(client.complete.call_count, 3)
        self.assertFalse((store.root/'intermediate/v2_1/functional-tree.json').exists())
        self.assertTrue((store.root/'intermediate/v2_1/function-tree.attempt-03.error.json').is_file())

    def test_cancel_is_never_retried(self):
        client=Mock();client.complete.side_effect=Cancelled();store=self.store()
        with self.assertRaises(Cancelled):generate_tree(client,store,FIXTURE['core'])
        self.assertEqual(client.complete.call_count,1)

if __name__=='__main__':unittest.main()
