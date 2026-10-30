import {REQCOMPLETER_V2_0} from './versions/reqcompleter-v2_0.ts';

export const TOOL = REQCOMPLETER_V2_0.toolName;
export const PACKAGE_VERSION = '0.2.3';
export const INPUT_SCHEMA = {
  type: 'object',
  properties: {
    software_intro: {type: 'string',
      description: '待补全的软件自然语言需求，非空且不超过 100000 字符；只传入本次任务明确需要的内容。'},
  },
  required: ['software_intro'],
  additionalProperties: false,
};
export interface Input {software_intro: string}
export interface Options {
  pythonPath: string;
  maxIterations: number;
  maxConcurrent: number;
  probeTimeoutMs: number;
  graceMs: number;
  maxProtocolBytes: number;
  maxLogBytes: number;
}
export class CompletionError extends Error {
  constructor(readonly code: string, message: string) {super(`${code}: ${message}`);}
}
export function errorCode(error: unknown): string {
  return error instanceof Error && 'code' in error && typeof error.code === 'string'
    && /^[A-Z][A-Z0-9_]{0,80}$/.test(error.code) ? error.code : 'EXECUTION_FAILED';
}
