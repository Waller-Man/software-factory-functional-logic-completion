/** Host-only ReqCompleter entry. Run owns tasks, models, queries and downloads. */
import {Service, type Context} from '@deepseek-ai/cordis';
import z from '@deepseek-ai/schemastery';
import {AsyncLocalStorage} from 'node:async_hooks';
import type {Agent} from '@deepseek-ai/dsh-agent';
import {registerRunTool} from '@software-factory/runtime-sdk';
import {CompletionRuntime} from './runtime.ts';
import {TOOL, INPUT_SCHEMA, CompletionError, type Options, type Input} from './contracts.ts';

declare module '@deepseek-ai/cordis' {
  interface Context {functionalLogicCompletion: FunctionalLogicCompletion}
}

export default class FunctionalLogicCompletion extends Service {
  static inject = ['tools', 'sfRuntime', 'subprocess', 'sandboxPolicy'];
  static Config = z.object({
    pythonPath: z.string().default('').description('服务端独立虚拟环境的 Python 解释器绝对路径；空值使用插件 .venv。'),
    maxIterations: z.number().step(1).min(1).max(20).default(5),
    maxConcurrent: z.number().step(1).min(1).max(16).default(1),
    probeTimeoutMs: z.number().step(1).min(1000).max(120000).default(15000),
    graceMs: z.number().step(1).min(100).max(30000).default(3000),
    maxProtocolBytes: z.number().step(1).min(4096).max(8388608).default(8388608),
    maxLogBytes: z.number().step(1).min(4096).max(268435456).default(16777216),
  });

  constructor(ctx: Context, private readonly options: Options) {
    super(ctx, 'functionalLogicCompletion');
  }

  async *[Service.init]() {
    const runtime = new CompletionRuntime(this.ctx, this.options);
    yield () => runtime.dispose();
    await runtime.initialize();

    // Deny read-only calls before Run creates files, as well as at business entry.
    this.ctx.tools.guard(exec => {
      const args = exec.arguments;
      const startsReq = exec.name === 'sf_runtime_run_tool' && args !== null
        && typeof args === 'object' && 'toolId' in args && args.toolId === TOOL;
      if (exec.name !== TOOL && !startsReq) return;
      if (!exec.agent) return 'NO_SESSION: 需要有效的 DSH 调用会话。';
      if (this.ctx.sandboxPolicy.resolve({session: exec.agent.session}).mode === 'read-only') {
        return 'READ_ONLY: 请在具有工作区写入许可的会话中启动任务。';
      }
    });
    // The SDK exposes no Agent. Retain the real caller for policy/path checks.
    const callers = new AsyncLocalStorage<Agent>();
    this.ctx.on('tools/execute', (exec, next) => {
      if (exec.name !== TOOL) return next();
      if (!exec.agent) throw new CompletionError('NO_SESSION', '需要有效的 DSH 调用会话。');
      return callers.run(exec.agent, next);
    });
    registerRunTool<Input>(this.ctx, {
      toolId: TOOL,
      description: '通过软件工厂 Run 执行 ReqCompleter v2.0。输入 software_intro 自然语言需求，交付需求说明书 DOCX、检查材料 ZIP 和结构化结果；保留逐轮材料。方法收敛不代表需求内容已经完整正确。请通过 sf_runtime_run_tool 启动。',
      inputSchema: INPUT_SCHEMA,
      execute: (input, execution) => runtime.run(input, execution, callers.getStore()),
    });
  }
}
