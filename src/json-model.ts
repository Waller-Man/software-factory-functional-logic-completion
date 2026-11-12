import type {ModelConnection, ModelMessage, ModelResponse} from '@software-factory/runtime-sdk';
import {CompletionError} from './contracts.ts';

export async function callJsonModel(connection: ModelConnection, messages: ModelMessage[], signal: AbortSignal): Promise<ModelResponse> {
  if (connection.protocol !== 'openai-completions') throw new CompletionError('MODEL_PROTOCOL_UNSUPPORTED', '功能树 JSON 模式需要 Chat Completions 连接。');
  signal.throwIfAborted();
  const response = await fetch(connection.baseUrl.replace(/\/$/, '') + '/chat/completions', {
    method: 'POST', signal, headers: {'content-type': 'application/json', authorization: `Bearer ${connection.apiKey}`},
    body: JSON.stringify({model: connection.model, messages, response_format: {type: 'json_object'}, stream: false}),
  });
  if (!response.ok) {
    await response.body?.cancel();
    throw new CompletionError('MODEL_JSON_REQUEST_FAILED', `Run JSON 模型请求失败（HTTP ${response.status}），请确认所选模型支持 JSON 模式。`);
  }
  const result = await response.json() as {choices?: Array<{finish_reason?: string; message?: {content?: unknown}}>};
  const choice = result.choices?.[0];
  if (choice?.finish_reason === 'length') throw new CompletionError('MODEL_OUTPUT_TRUNCATED', '功能树 JSON 响应达到模型输出长度上限。');
  const text = choice?.message?.content;
  if (typeof text !== 'string' || !text.trim()) throw new CompletionError('INVALID_MODEL_OUTPUT', 'JSON 模型没有返回可见文本。');
  return {text};
}
