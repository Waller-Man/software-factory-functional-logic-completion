import test from 'node:test';
import assert from 'node:assert/strict';
import {ProgressEstimate} from '../src/progress.ts';

test('core, hierarchy, per-image progress and delivery are numeric and monotonic', () => {
  const progress = new ProgressEstimate(5);
  assert.equal(progress.advance('starting'), 0);
  assert.equal(progress.advance('starting', 'completed'), 2);
  assert.equal(progress.advance('extract_entities'), 2);
  assert.equal(progress.advance('crud_check', 'completed', 1, true), 53);
  assert.equal(progress.advance('core_document', 'completed'), 67);
  assert.equal(progress.advance('functional_hierarchy', 'completed'), 73);
  assert.equal(progress.advance('layer_use_cases', 'running', 0, false, 1, 2), 78);
  assert.equal(progress.advance('layer_use_cases', 'completed'), 84);
  assert.equal(progress.advance('leaf_activities', 'running', 0, false, 1, 2), 89);
  assert.equal(progress.advance('leaf_activities', 'completed'), 94);
  assert.equal(progress.advance('extract_entities'), 94);
  assert.equal(progress.advance('save_docx', 'completed'), 98);
  assert.equal(progress.advance('publishing', 'completed'), 99);
  assert.equal(progress.finish(), 100);
});

test('configured core iteration limits cannot finish v2.1 output early', () => {
  for (const max of [1, 5, 20]) {
    const progress = new ProgressEstimate(max);
    assert.ok(progress.advance('complete_crud', 'completed', max) < 67);
    assert.equal(progress.advance('functional_hierarchy'), 67);
    assert.equal(progress.advance('unknown'), 67);
    assert.equal(progress.advance('leaf_activities', 'running', 0, false, -1, 5), 84);
  }
});
