/** Host-only ReqCompleter entry. Run owns tasks, models, queries and downloads. */
import {Service, type Context} from '@deepseek-ai/cordis';
import type {} from '@deepseek-ai/dsh-settings';
import {Config, snapshotOptions, type LiveOptions} from './config.ts';
import {AsyncLocalStorage} from 'node:async_hooks';
import type {Agent} from '@deepseek-ai/dsh-agent';
import {registerRunTool} from '@software-factory/runtime-sdk';
import {CompletionRuntime} from './runtime.ts';
import {TOOL, INPUT_SCHEMA, CompletionError, type Options, type Input} from './contracts.ts';

declare module '@deepseek-ai/cordis' {
  interface Context {functionalLogicCompletionV21: FunctionalLogicCompletionV21}
}

export default class FunctionalLogicCompletionV21 extends Service {
  static inject = ['tools', 'sfRuntime', 'subprocess', 'sandboxPolicy'];
  static Config = Config;

  constructor(ctx: Context, private readonly options: LiveOptions) {
    super(ctx, 'functionalLogicCompletionV21');
  }

  async *[Service.init]() {
    const running = new Set<CompletionRuntime>();
    const settings = this.ctx.inject(['settings'], scope => {
      scope.effect(() => scope.settings.configure({auto: false}, this.ctx.fiber));
    });
    yield async () => { await Promise.all([...running].map(runtime => runtime.dispose())); await settings.dispose(); };

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
      description: '通过软件工厂 Run 执行 ReqCompleter v2.1。输入 software_intro 自然语言需求，交付含分层功能、各层用例图和叶子活动图的 DOCX、功能树、图文件 ZIP、检查材料和结构化结果；保留逐轮材料。方法收敛不代表需求内容已经完整正确。请通过 sf_runtime_run_tool 启动。',
      inputSchema: INPUT_SCHEMA,
      modelProtocols: ['openai-completions'],
      execute: async (input, execution) => {
        const options = snapshotOptions(this.options);
        if (running.size >= options.maxConcurrent) throw new CompletionError('BUSY', 'ReqCompleter 已达到并发上限，请稍后重试。');
        const runtime = new CompletionRuntime(this.ctx, options);
        running.add(runtime);
        try { return await runtime.run(input, execution, callers.getStore()); }
        finally { running.delete(runtime); await runtime.dispose(); }
      },
    });
  }
}
