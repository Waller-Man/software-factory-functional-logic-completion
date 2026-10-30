/** Python adapter only; task identity, model isolation and delivery belong to Run. */
import type {Context} from '@deepseek-ai/cordis';
import type {Agent} from '@deepseek-ai/dsh-agent';
import type {SubprocessHandle} from '@deepseek-ai/dsh-subprocess';
import type {} from '@deepseek-ai/dsh-sandbox-policy';
import type {ExecutionContext, BusinessResult} from '@software-factory/runtime-sdk';
import {access, appendFile, mkdir, readdir, realpath, rename, stat, writeFile} from 'node:fs/promises';
import {isAbsolute, join, relative, sep} from 'node:path';
import {fileURLToPath} from 'node:url';
import {randomUUID} from 'node:crypto';
import {StringDecoder} from 'node:string_decoder';
import {CompletionError, errorCode, PACKAGE_VERSION, TOOL, type Input, type Options} from './contracts.ts';
import {jsonLines, send, workerEvent, type WorkerFinal} from './protocol.ts';
import {REQCOMPLETER_V2_0 as VERSION} from './versions/reqcompleter-v2_0.ts';
import {ProgressEstimate} from './progress.ts';

const packageRoot = fileURLToPath(new URL('../', import.meta.url));
const pythonEnv = {PYTHONDONTWRITEBYTECODE: '1', PYTHONUNBUFFERED: '1', PYTHONUTF8: '1', PYTHONNOUSERSITE: '1'};
const stageNames: Record<string, string> = {
  starting: '启动准备',
  extract_entities: '提取实体', generate_use_cases: '生成用例', describe_use_cases: '描述用例',
  generate_er_model: '生成 E-R 模型', generate_crud: '生成 CRUD 三元组', check_er_model: '检查 E-R 模型',
  crud_check: '检查 CRUD 缺口', complete_use_cases: '补全用例', complete_er_model: '补全 E-R 模型',
  complete_crud: '补全 CRUD', functional_requirements: '生成功能需求', external_interface: '生成接口需求',
  nonfunctional_requirements: '生成非功能需求', use_case_plantuml: '生成用例图源码', er_plantuml: '生成 E-R 图源码',
  save_docx: '生成需求说明书', publishing: '登记交付文件',
};

export function runtimePaths(options: Options) {
  const python = options.pythonPath || join(packageRoot, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
  if (!isAbsolute(python)) throw new CompletionError('INVALID_CONFIG', 'pythonPath 必须是服务端解释器的绝对路径。');
  return {python, worker: join(packageRoot, VERSION.workerRelativePath)};
}
export async function atomicJson(path: string, value: unknown): Promise<void> {
  const pending = path + '.' + randomUUID() + '.tmp';
  await writeFile(pending, JSON.stringify(value, null, 2) + '\n', {flag: 'wx', mode: 0o600});
  await rename(pending, path);
}
function mime(path: string): string {
  if (path.endsWith('.docx')) return 'application/vnd.openxmlformats-officedocument.wordprocessingml.document';
  if (path.endsWith('.zip')) return 'application/zip';
  if (path.endsWith('.json')) return 'application/json';
  if (path.endsWith('.csv')) return 'text/csv';
  return 'text/plain';
}

export class CompletionRuntime {
  readonly paths: ReturnType<typeof runtimePaths>;
  private readonly lifetime = new AbortController();
  private readonly active = new Set<Promise<BusinessResult>>();
  constructor(private readonly ctx: Context, private readonly options: Options) {
    this.paths = runtimePaths(options);
  }

  async initialize(): Promise<void> {
    await access(this.paths.python); await access(this.paths.worker);
    const text = await this.command(['--probe'], packageRoot, AbortSignal.timeout(this.options.probeTimeoutMs));
    if (JSON.parse(text).ready !== true) throw new CompletionError('PYTHON_NOT_READY', '请先准备 Python 独立环境与锁定依赖。');
  }

  run(input: Readonly<Input>, execution: ExecutionContext, caller?: Agent): Promise<BusinessResult> {
    execution.signal.throwIfAborted(); this.lifetime.signal.throwIfAborted();
    if (!input.software_intro?.trim() || input.software_intro.length > 100000) throw new CompletionError('INVALID_INPUT', 'software_intro 不能为空或超过 100000 字符。');
    if (!caller) throw new CompletionError('NO_SESSION', '缺少正常 Tool 执行链的调用会话。');
    if (this.active.size >= this.options.maxConcurrent) throw new CompletionError('BUSY', 'ReqCompleter 已达到并发上限，请稍后重试。');
    const policy = this.ctx.sandboxPolicy.resolve({session: caller.session});
    if (policy.mode === 'read-only') throw new CompletionError('READ_ONLY', '请在具有工作区写入许可的会话中启动任务。');
    const work = this.execute(input, execution, policy);
    this.active.add(work);
    void work.then(() => this.active.delete(work), () => this.active.delete(work));
    return work;
  }

  async dispose(): Promise<void> {
    this.lifetime.abort(new CompletionError('HOST_INTERRUPTED', '插件已停用。'));
    await Promise.allSettled([...this.active]);
  }

  private async execute(input: Readonly<Input>, execution: ExecutionContext,
    policy: ReturnType<Context['sandboxPolicy']['resolve']>): Promise<BusinessResult> {
    const signal = AbortSignal.any([execution.signal, this.lifetime.signal]);
    const directory = execution.outputDirectory;
    const estimate = new ProgressEstimate(this.options.maxIterations);
    const indexed = new Set<string>();
    const manifest: Record<string, unknown> = {
      runId: execution.runId, toolId: TOOL, packageVersion: PACKAGE_VERSION,
      businessVersion: VERSION.businessVersion, implementationVersion: VERSION.implementationVersion,
      sourceSha256: VERSION.sourceSha256, model: execution.model.selection ?? null,
      parameters: {maxIterations: this.options.maxIterations}, startedAt: new Date().toISOString(),
    };
    let directoryValidated = false;
    try {
      const workspace = await realpath(policy.workspaceRoot), taskDirectory = await realpath(directory);
      const taskRelative = relative(workspace, taskDirectory);
      if (!taskRelative || taskRelative === '..' || taskRelative.startsWith('..' + sep) || isAbsolute(taskRelative)) {
        throw new CompletionError('INVALID_PATH', 'Run 任务目录必须位于发起会话的工作区内。');
      }
      directoryValidated = true;
      await atomicJson(join(directory, 'manifest.json'), manifest);
      await execution.reportProgress({stage: 'starting', stageName: '启动准备', progress: estimate.advance('starting'),
        message: '正在启动 Python 并检查任务目录写入。'});
      await execution.log('ReqCompleter v2.0 开始执行；模型和任务目录由 Run 固定。', 'starting');
      const registerMaterials = () => this.materials(execution, indexed);
      const result = await this.worker(input, execution, signal, registerMaterials, estimate);
      signal.throwIfAborted();
      if (result.docx_path !== 'final/requirements.docx' || !(await stat(join(directory, result.docx_path))).size) {
        throw new CompletionError('DOCX_FAILED', 'Python 未生成有效的非空需求文档。');
      }
      Object.assign(manifest, {
        executionStatus: 'succeeded', documentStatus: 'generated',
        convergenceStatus: result.converged ? 'converged' : 'not_converged',
        iterations: result.iterations, reachedIterationLimit: result.reached_iteration_limit,
        finishedAt: new Date().toISOString(),
      });
      await atomicJson(join(directory, 'manifest.json'), manifest);
      await execution.reportProgress({stage: 'publishing', stageName: stageNames.publishing!,
        progress: estimate.advance('publishing'), message: '正在打包并登记交付文件（估算进度）。'});
      // Archive once, after business metadata is final. Run's run.json remains authoritative.
      await this.command(['--archive', directory], directory, signal);
      await registerMaterials();
      const files: string[] = [];
      for (const name of ['requirements.docx', 'checks.zip', 'result.json']) {
        const file = await execution.addArtifact({kind: 'final', name, relativePath: 'final/' + name, mime: mime(name)});
        files.push(file.artifactId);
      }
      const text = `需求说明书已生成；检查轮次 ${result.iterations}，${result.converged ? '方法判定收敛' : '方法未判定收敛'}，${result.reached_iteration_limit ? '已达到迭代上限' : '未达到迭代上限'}。收敛不代表需求内容已经完整正确。`;
      await execution.log(text, 'publishing');
      await execution.reportProgress({stage: 'completed', stageName: '交付完成', progress: estimate.finish(),
        message: '文档及检查材料已登记；最终任务是否成功以 Run 状态为准。'});
      return {text, files};
    } catch (error) {
      Object.assign(manifest, {
        executionStatus: signal.aborted ? 'stopped' : 'failed', errorCode: errorCode(error),
        finishedAt: new Date().toISOString(),
      });
      if (!signal.aborted) {
        // Auxiliary I/O must never replace the original failure returned to Run.
        await execution.reportIssue({level: 'error', code: errorCode(error),
          message: error instanceof Error ? error.message : 'Python 执行失败。'}).catch(() => {});
      }
      if (directoryValidated) {
        await atomicJson(join(directory, 'manifest.json'), manifest).catch(() => {});
        if (!signal.aborted) await this.materials(execution, indexed).catch(() => {});
      }
      throw error;
    }
  }

  private async materials(execution: ExecutionContext, indexed: Set<string>): Promise<void> {
    const visit = async (relative: string): Promise<void> => {
      for (const entry of await readdir(join(execution.outputDirectory, relative), {withFileTypes: true})) {
        if (entry.name.startsWith('.') || entry.name.endsWith('.tmp') || entry.name.endsWith('.partial') || entry.isSymbolicLink()) continue;
        const path = relative + '/' + entry.name;
        if (entry.isDirectory()) await visit(path);
        else if (entry.isFile() && !indexed.has(path)) {
          await execution.addArtifact({kind: 'intermediate', name: path, relativePath: path, mime: mime(path)});
          indexed.add(path);
        }
      }
    };
    for (const folder of ['intermediate', 'snapshots']) {
      await mkdir(join(execution.outputDirectory, folder), {recursive: true});
      await visit(folder);
    }
  }

  private async worker(input: Readonly<Input>, execution: ExecutionContext,
    signal: AbortSignal,
    registerMaterials: () => Promise<void>, estimate: ProgressEstimate): Promise<WorkerFinal> {
    const argv = [this.paths.python, '-B', '-u', this.paths.worker];
    let handle: SubprocessHandle | undefined;
    let stopping: Promise<void> | undefined;
    const stop = (): Promise<void> => stopping ??= (async () => {
      if (!handle) return;
      handle.terminate(); await handle.done.catch(() => {});
      if (!await handle.waitForExit(AbortSignal.timeout(this.options.graceMs * 2))) throw new CompletionError('PROCESS_CLEANUP', 'Python 进程尚未退出。');
    })();
    execution.registerCleanup(stop);
    const processAbort = new AbortController();
    const runningSignal = AbortSignal.any([signal, processAbort.signal]);
    handle = this.ctx.subprocess.spawn({argv, cwd: execution.outputDirectory, stdio: {stdin: 'pipe', stdout: 'pipe', stderr: 'pipe'}, graceMs: this.options.graceMs, signal: runningSignal, env: pythonEnv});
    const startupTimer = setTimeout(() => processAbort.abort(new CompletionError('PYTHON_START_TIMEOUT',
      'Python 未在启动时限内确认任务目录写入。')), this.options.probeTimeoutMs);
    const process = handle;
    const outcome = process.done;
    void outcome.catch(error => processAbort.abort(error));
    const stderr = (async () => {
      if (!process.stderr) return;
      let bytes = 0, pending = '';
      const decoder = new StringDecoder('utf8');
      for await (const chunk of process.stderr) {
        bytes += Buffer.byteLength(chunk);
        if (bytes > this.options.maxLogBytes) throw new CompletionError('LOG_LIMIT', 'Python 日志超过限制。');
        await appendFile(join(execution.outputDirectory, 'logs/stderr.log'), chunk, {mode: 0o600}).catch(() => {});
        pending += decoder.write(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
        let end: number;
        while ((end = pending.indexOf('\n')) >= 0 || pending.length >= 8000) {
          const count = end >= 0 ? Math.min(end, 8000) : 8000;
          const line = pending.slice(0, count); pending = pending.slice(count + (count === end ? 1 : 0));
          if (line.trim() && !runningSignal.aborted) await execution.log(line, 'python');
        }
      }
      pending += decoder.end();
      if (pending.trim() && !runningSignal.aborted) await execution.log(pending, 'python');
    })();
    void stderr.catch(error => processAbort.abort(error));
    const cancel = () => {
      if (process.stdin && !process.stdin.destroyed) void send(process.stdin, {type: 'cancel', protocolVersion: 1, runId: execution.runId}, this.options.maxProtocolBytes).catch(() => {});
    };
    signal.addEventListener('abort', cancel, {once: true});
    let failed = false;
    try {
      if (!process.stdin || !process.stdout) throw new CompletionError('PROCESS_IO', 'Python 标准输入输出管道不可用。');
      await send(process.stdin, {type: 'start', protocolVersion: 1, runId: execution.runId,
        software_intro: input.software_intro, max_iterations: this.options.maxIterations, output_dir: execution.outputDirectory}, this.options.maxProtocolBytes);
      let final: WorkerFinal | undefined;
      const requests = new Set<string>();
      for await (const line of jsonLines(process.stdout, this.options.maxProtocolBytes)) {
        runningSignal.throwIfAborted();
        const event = workerEvent(line, execution.runId);
        clearTimeout(startupTimer);
        if (final) throw new CompletionError('PROTOCOL_ERROR', 'Python 在最终结果之后继续发送消息。');
        if (event.type === 'model_request') {
          if (requests.has(event.id)) throw new CompletionError('PROTOCOL_ERROR', '模型请求 ID 重复。');
          requests.add(event.id);
          await registerMaterials();
          try {
            const answer = await execution.model.call({messages: event.messages});
            await send(process.stdin, {type: 'model_response', protocolVersion: 1, runId: execution.runId, id: event.id, result: {text: answer.text}}, this.options.maxProtocolBytes);
          } catch (error) {
            await send(process.stdin, {type: 'model_response', protocolVersion: 1, runId: execution.runId, id: event.id,
              error: {code: errorCode(error), message: 'Run 模型调用失败，停止生成。'}}, this.options.maxProtocolBytes).catch(() => {});
            throw error;
          }
        } else if (event.type === 'step') {
          const round = typeof event.iteration === 'number' ? event.iteration : 0;
          await execution.reportProgress({stage: event.step, stageName: stageNames[event.step] ?? event.step,
            progress: estimate.advance(event.step, event.status, round, event.converged === true),
            message: event.step === 'starting' && event.status === 'completed'
              ? 'Python 已接收任务并完成目录写入检查（估算进度）。'
              : `${round ? `第 ${round} 轮：` : ''}${event.status === 'completed' ? '阶段完成' : '正在处理'}（估算进度）`});
          await registerMaterials();
        } else if (event.type === 'artifact') {
          // Final files are registered only after successful worker exit.
          await execution.log(`文件已保存：${event.path}`, event.kind);
        } else if (event.type === 'error') {
          throw new CompletionError(event.error.code, event.error.message);
        } else final = event.result;
      }
      const ended = await outcome; await stderr; runningSignal.throwIfAborted();
      if (ended.exitCode !== 0 || !final) throw new CompletionError('PYTHON_EXIT', 'Python 未成功返回最终结果。');
      return final;
    } catch (error) {
      failed = true;
      throw error;
    } finally {
      clearTimeout(startupTimer);
      signal.removeEventListener('abort', cancel);
      let cleanupError: unknown;
      try { await stop(); } catch (error) { cleanupError = error; }
      await Promise.allSettled([outcome, stderr]);
      if (cleanupError && !failed) throw cleanupError;
    }
  }

  private async command(args: string[], cwd: string, signal: AbortSignal): Promise<string> {
    const argv = [this.paths.python, '-B', this.paths.worker, ...args];
    const handle = this.ctx.subprocess.spawn({argv, cwd,
      stdio: {stdin: 'ignore', stdout: {maxBytes: this.options.maxProtocolBytes}, stderr: {maxBytes: 4096}},
      graceMs: this.options.graceMs, signal, env: pythonEnv});
    let failed = false;
    try {
      const outcome = await handle.done; signal.throwIfAborted();
      if (outcome.exitCode !== 0) throw new CompletionError(args[0] === '--probe' ? 'PYTHON_NOT_READY' : 'ARCHIVE_FAILED', 'Python 环境检查或检查包生成失败。');
      const output = handle.collected.stdout?.readFrom(0);
      if (!output || output.lossy) throw new CompletionError('PROCESS_IO', 'Python 命令未返回完整输出。');
      return output.text;
    } catch (error) {
      failed = true;
      throw error;
    } finally {
      handle.terminate(); await handle.done.catch(() => {});
      try {
        if (!await handle.waitForExit(AbortSignal.timeout(this.options.graceMs * 2))) {
          throw new CompletionError('PROCESS_CLEANUP', 'Python 命令进程尚未退出。');
        }
      } catch (error) { if (!failed) throw error; }
    }
  }
}
