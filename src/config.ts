import z from '@deepseek-ai/schemastery';
import type {Volatile} from '@deepseek-ai/cordis';
import type {Options} from './contracts.ts';

export type LiveOptions = {[K in keyof Options]: Volatile<Options[K]>};
export const Config = z.object({
    pythonPath: z.string().default('').description('服务端独立虚拟环境的 Python 解释器绝对路径；空值使用插件 .venv。').volatile(),
    maxIterations: z.number().step(1).min(1).max(20).default(5).volatile(),
    maxConcurrent: z.number().step(1).min(1).max(16).default(1).volatile(),
    probeTimeoutMs: z.number().step(1).min(1000).max(120000).default(15000).volatile(),
    graceMs: z.number().step(1).min(100).max(30000).default(3000).volatile(),
    maxProtocolBytes: z.number().step(1).min(4096).max(8388608).default(8388608).volatile(),
    maxLogBytes: z.number().step(1).min(4096).max(268435456).default(16777216).volatile(),
  });

export function snapshotOptions(config: LiveOptions): Readonly<Options> {
  return Object.freeze(Object.fromEntries(Object.entries(config).map(([key, value]) => [key, value.get()])) as unknown as Options);
}
