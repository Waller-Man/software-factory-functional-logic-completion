import test from 'node:test';
import assert from 'node:assert/strict';
import {ProgressEstimate} from '../src/progress.ts';

test('flow estimates cover startup, variable iteration limits and delivery', () => {
  for (const limit of [1, 5, 20]) {
    const progress = new ProgressEstimate(limit);
    let previous = 0;
    const check = (stage: string, status: string, round = 0) => {
      const value = progress.advance(stage, status, round);
      assert.ok(Number.isInteger(value) && value >= previous && value < 100);
      previous = value;
    };
    for (const stage of ['starting', 'extract_entities', 'generate_use_cases', 'describe_use_cases',
      'generate_er_model', 'generate_crud', 'check_er_model']) {
      check(stage, 'running'); check(stage, 'completed');
    }
    assert.equal(previous, 38);
    for (let round = 1; round <= limit; round++) {
      for (const stage of ['crud_check', 'complete_use_cases', 'complete_er_model', 'complete_crud']) {
        check(stage, 'running', round); check(stage, 'completed', round);
      }
    }
    assert.equal(previous, 78);
    for (const stage of ['functional_requirements', 'external_interface', 'nonfunctional_requirements',
      'use_case_plantuml', 'er_plantuml', 'save_docx', 'publishing']) {
      check(stage, 'running'); check(stage, 'completed');
    }
    assert.equal(previous, 99);
    assert.equal(progress.finish(), 100);
  }
});

test('early convergence jumps ahead and skipped or repeated stages cannot regress', () => {
  const progress = new ProgressEstimate(5);
  assert.equal(progress.advance('generate_use_cases'), 8);
  assert.equal(progress.advance('crud_check', 'running', 1), 38);
  assert.equal(progress.advance('crud_check', 'completed', 1, true), 78);
  assert.equal(progress.advance('functional_requirements'), 78);
  assert.equal(progress.advance('functional_requirements', 'completed'), 84);
  assert.equal(progress.advance('complete_use_cases', 'running', 1), 84);
  assert.equal(progress.advance('unknown-stage'), 84);
});
