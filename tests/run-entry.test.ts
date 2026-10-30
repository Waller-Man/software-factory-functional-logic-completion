/** Small native Run checks. Synthetic algorithm/model; no profile installation. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {randomUUID} from 'node:crypto';
import {mkdir, mkdtemp, readFile, stat} from 'node:fs/promises';
import {join, resolve} from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';
import {Context} from '@deepseek-ai/cordis';
import {SessionId} from '@deepseek-ai/dsh-session';
import {LlmAdapter, ToolCallId, type GenerateOptions} from '@deepseek-ai/dsh-llm';
import Registry from '@deepseek-ai/dsh-typert-registry';
import SubprocessLocal from '@deepseek-ai/dsh-subprocess-local';
import type {SubprocessSpawnSpec, SubprocessHandle} from '@deepseek-ai/dsh-subprocess';
import SandboxPolicy from '@deepseek-ai/dsh-sandbox-policy';
import {mountAgentLoopTestDependencies, mountAgentLoopTestHarness} from '@deepseek-ai/dsh-agent-loop-testkit';
import Plugin from '../lib/index.js';

const root = fileURLToPath(new URL('..', import.meta.url));
const runtimeSource = resolve(process.env.SF_RUNTIME_SOURCE ?? join(root, '../reconstruct/packages/runtime'));
const {default: Runtime} = await import(pathToFileURL(join(runtimeSource, 'lib/index.js')).href);
const TOOL = 'sf_functional_logic_completion_v2_0';

async function fixture(options: {mode?: 'read-only' | 'workspace-write'; stallStartup?: boolean} = {}) {
  const ctx = new Context();
  const results = join(root, 'test-results'); await mkdir(results, {recursive: true});
  const workspace = await mkdtemp(join(process.env.REQ_ENTRY_TEST_PARENT ?? results, 'run-entry-'));
  await mountAgentLoopTestDependencies(ctx, {workingDirectory: true});
  const harness = await mountAgentLoopTestHarness(ctx);
  const agent = await harness.create(SessionId('req-entry-' + randomUUID()),
    {provider: 'mock-A', model: 'mock'}, {cwd: workspace});
  await ctx.plugin(Registry);
  await ctx.plugin(SubprocessLocal);
  await ctx.plugin(SandboxPolicy, {mode: options.mode ?? 'workspace-write'});
  // Deliberately mount no sandbox service: this is a trusted managed backend.
  const spawn = ctx.subprocess.spawn.bind(ctx.subprocess);
  const workers: SubprocessHandle[] = [];
  const launches: SubprocessSpawnSpec[] = [];
  ctx.subprocess.spawn = (spec: SubprocessSpawnSpec) => {
    launches.push(spec);
    const business = spec.argv.includes(join(root, 'python/worker.py')) && !spec.argv.includes('--probe') && !spec.argv.includes('--archive');
    const handle = spawn(business ? {...spec,
      env: {...spec.env, REQ_TEST_STALL_STARTUP: options.stallStartup ? '1' : '0'},
      argv: spec.argv.map(arg => arg === join(root, 'python/worker.py') ? join(root, 'tests/worker_stub.py') : arg)} : spec);
    if (business) workers.push(handle);
    return handle;
  };
  const requests: GenerateOptions[] = [];
  class MockModel extends LlmAdapter {
    async listModels(provider: string) {return [{provider, id: 'mock', name: 'Synthetic model'}];}
    async *stream(options: GenerateOptions) {
      requests.push(options);
      yield {type: 'text-delta' as const, index: 0, text: 'synthetic reply'};
      yield {type: 'usage' as const, usage: {inputTokens: 3, outputTokens: 2}};
      yield {type: 'finish' as const, reason: {kind: 'stop' as const}};
    }
  }
  ctx.llm.registerAdapter(['mock-A', 'mock-B'], new MockModel());
  await ctx.plugin(Runtime, {allowedToolIds: [TOOL], defaultTimeoutMs: 15000});
  const plugin = await ctx.plugin(Plugin, options.stallStartup ? {probeTimeoutMs: 1000} : {});
  async function call(action: string, args: object) {
    const result = await ctx.tools.execute({name: 'sf_runtime_' + action, arguments: args,
      agent, callId: ToolCallId(randomUUID()), signal: AbortSignal.timeout(20000)});
    assert.equal(result.isError, false, JSON.stringify(result));
    const value = (result as any).value; assert.equal(value.ok, true, JSON.stringify(value));
    return value.data;
  }
  async function finish(runId: string) {
    let seq = 0;
    for (let round = 0; round < 100; round++) {
      const update = await call('wait_run', {runId, afterSeq: seq, waitMs: 200});
      seq = update.lastSeq;
      if (['completed', 'failed', 'cancelled', 'interrupted'].includes(update.run.status)) return call('get_run', {runId});
    }
    throw new Error('Entry smoke did not finish');
  }
  return {ctx, agent, workspace, workers, requests, call, finish, plugin, launches};
}

test('managed Python writes Run files without a sandbox service', {timeout: 30000}, async t => {
  const f = await fixture(); t.after(() => f.ctx.fiber.dispose());
  const accepted = await f.call('run_tool', {toolId: TOOL, input: {software_intro: 'synthetic_test'}});
  const run = await f.finish(accepted.runId);
  assert.equal(run.status, 'completed', JSON.stringify(run));
  const directory = join(f.workspace, 'outputs/runs', run.runId);
  assert.ok(f.launches.every(spec => spec.argv[0] === join(root, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python')));
  assert.ok((await stat(join(directory, 'input/worker-claim.json'))).size > 0);
  assert.ok((await stat(join(directory, 'final/requirements.docx'))).size > 0);
  assert.ok((await stat(join(directory, 'final/checks.zip'))).size > 0);
  assert.equal(f.requests.length, 1);
});

test('read-only Run start is denied before task files or workers are created', {timeout: 20000}, async t => {
  const f = await fixture({mode: 'read-only'}); t.after(() => f.ctx.fiber.dispose());
  const result = await f.ctx.tools.execute({name: 'sf_runtime_run_tool', arguments: {toolId: TOOL, input: {software_intro: 'synthetic'}},
    agent: f.agent, callId: ToolCallId(randomUUID()), signal: AbortSignal.timeout(10000)});
  assert.equal(result.isError, true);
  assert.match(JSON.stringify(result), /READ_ONLY/);
  await assert.rejects(stat(join(f.workspace, 'outputs')), {code: 'ENOENT'});
  assert.equal(f.workers.length, 0);
  assert.equal(f.requests.length, 0);
});

test('failure survives unavailable error, stderr and manifest files', {timeout: 20000}, async t => {
  const f = await fixture(); t.after(() => f.ctx.fiber.dispose());
  const accepted = await f.call('run_tool', {toolId: TOOL, input: {software_intro: 'errors-unwritable'}});
  const run = await f.finish(accepted.runId);
  assert.equal(run.status, 'failed', JSON.stringify(run));
  assert.match(run.message, /fixture primary failure/);
  assert.equal(f.requests.length, 0);
});

test('missing worker startup acknowledgement fails within the startup timeout', {timeout: 20000}, async t => {
  const f = await fixture({stallStartup: true}); t.after(() => f.ctx.fiber.dispose());
  const accepted = await f.call('run_tool', {toolId: TOOL, input: {software_intro: 'synthetic'}});
  const run = await f.finish(accepted.runId);
  assert.equal(run.status, 'failed', JSON.stringify(run));
  assert.match(run.message, /PYTHON_START_TIMEOUT/);
  assert.equal(f.requests.length, 0);
  assert.equal(await f.workers[0]!.waitForExit(AbortSignal.timeout(1000)), true);
});

test('built SDK entry: native Run, fake model, real small DOCX and artifact IDs', {timeout: 30000}, async t => {
  const f = await fixture(); t.after(() => f.ctx.fiber.dispose());
  const contract = await f.call('get_tool_contract', {toolId: TOOL});
  assert.deepEqual(contract.inputSchema.required, ['software_intro']);
  const direct = await f.ctx.tools.execute({name: TOOL, arguments: {software_intro: 'direct'}, agent: f.agent,
    callId: ToolCallId(randomUUID()), signal: AbortSignal.timeout(1000)});
  assert.equal(direct.isError, true, 'Direct calls must not bypass Run');
  for (const specified of [false, true]) {
    const accepted = await f.call('run_tool', {toolId: TOOL, input: {software_intro: 'synthetic_test'},
      ...(specified ? {model: {provider: 'mock-B', model: 'mock'}} : {})});
    const run = await f.finish(accepted.runId);
    assert.equal(run.status, 'completed', JSON.stringify(run));
    assert.equal(run.model.provider, specified ? 'mock-B' : 'mock-A');
    const directory = join(f.workspace, 'outputs/runs', run.runId);
    const stored = JSON.parse(await readFile(join(directory, 'run.json'), 'utf8'));
    const stages = stored.events.filter((event: any) => event.type === 'progress').map((event: any) => event.data);
    assert.equal(stages[0].stage, 'starting');
    assert.equal(stages[0].stageName, '启动准备');
    assert.equal(stages[0].progress, 0);
    assert.equal(stages[1].stage, 'starting');
    assert.match(stages[1].message, /完成目录写入检查/);
    const extraction = stages.find((stage: any) => stage.stage === 'extract_entities');
    assert.ok(extraction);
    assert.equal(extraction.progress, 2);
    assert.ok(stages.every((stage: any, index: number) => Number.isFinite(stage.progress)
      && (index === 0 || stage.progress >= stages[index - 1].progress)), 'Flow estimates must remain numeric and monotonic');
    assert.equal(stages.at(-1).progress, 100);
    assert.equal(run.progress, 100);
    const request = JSON.parse(await readFile(join(directory, 'input/request.json'), 'utf8'));
    assert.equal(request.toolId, TOOL, 'Run request is not overwritten by Python');
    assert.equal(JSON.parse(await readFile(join(directory, 'input/reqcompleter-request.json'), 'utf8')).runId, run.runId);
    assert.equal(run.result.files.length, 3);
    assert.ok(run.artifacts.some((a: any) => a.relativePath === 'intermediate/initial/entities.json'));
    assert.ok(run.artifacts.some((a: any) => a.relativePath === 'snapshots/iterations/001/after.json'));
    for (const file of run.result.files) {
      assert.ok(file.artifactId && file.relativePath.startsWith('final/'));
      assert.ok((await stat(join(directory, file.relativePath))).size > 0);
      const view = await f.call('get_artifact', {runId: run.runId, artifactId: file.artifactId});
      assert.match(view.downloadUrl, /^\/api\/sf-runtime\/download\?/);
    }
    const manifest = JSON.parse(await readFile(join(directory, 'manifest.json'), 'utf8'));
    assert.equal(manifest.model.provider, run.model.provider);
    assert.equal(manifest.convergenceStatus, 'not_converged', 'File generation must not imply convergence');
    assert.equal(f.agent.options.provider, 'mock-A');
  }
  assert.equal(f.requests.length, 2, 'Only one synthetic model call per task');
  assert.ok(f.requests.every(r => r.sessionId?.startsWith('sf-run-model-')));
  await f.plugin.dispose();
  assert.equal(f.ctx.tools.get(TOOL, f.agent), undefined);
});

test('native Run cancellation stops the Python fixture and retains partial materials', {timeout: 20000}, async t => {
  const f = await fixture(); t.after(() => f.ctx.fiber.dispose());
  const accepted = await f.call('run_tool', {toolId: TOOL, input: {software_intro: 'cancel'}});
  let seq = 0;
  for (let round = 0; round < 60; round++) {
    const update = await f.call('wait_run', {runId: accepted.runId, afterSeq: seq, waitMs: 200});
    seq = update.lastSeq;
    if (update.run.stage === 'extract_entities') break;
  }
  await f.call('cancel_run', {runId: accepted.runId});
  const run = await f.finish(accepted.runId);
  assert.equal(run.status, 'cancelled', JSON.stringify(run));
  assert.equal(run.result, undefined);
  assert.equal(f.workers.length, 1);
  assert.equal(await f.workers[0]!.waitForExit(AbortSignal.timeout(1000)), true);
  assert.ok((await stat(join(f.workspace, 'outputs/runs', run.runId, 'snapshots/iterations/001/before.json'))).isFile());
});
