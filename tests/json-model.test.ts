import test from 'node:test';
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {callJsonModel} from '../src/json-model.ts';
import type {ModelConnection} from '@software-factory/runtime-sdk';

test('JSON request goes only to the task gateway and propagates cancellation/errors', async () => {
  const received: any[] = [];
  const server = createServer(async (req, res) => {
    let raw = ''; for await (const chunk of req) raw += chunk;
    const body = JSON.parse(raw); received.push(body);
    assert.equal(req.url, '/v1/chat/completions'); assert.equal(req.headers.authorization, 'Bearer synthetic-task-token');
    assert.deepEqual(body.response_format, {type: 'json_object'}); assert.equal(body.model, 'fixed-model');
    assert.equal(body.reasoning_effort, undefined);
    const content = body.messages[1].content;
    if (content === 'http-error') {res.writeHead(400).end('unsupported'); return;}
    res.setHeader('content-type', 'application/json');
    res.end(JSON.stringify({choices: [{finish_reason: content === 'too-long' ? 'length' : 'stop', message: {content: '{"systemName":"mock"}'}}]}));
  });
  await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve));
  const address = server.address(); assert.ok(address && typeof address !== 'string');
  const connection: ModelConnection = {baseUrl: `http://127.0.0.1:${address.port}/v1`, apiKey: 'synthetic-task-token', model: 'fixed-model', protocol: 'openai-completions'};
  const messages = (text: string) => [{role: 'system' as const, content: 'Return JSON'}, {role: 'user' as const, content: text}];
  try {
    assert.equal((await callJsonModel(connection, messages('normal'), new AbortController().signal)).text, '{"systemName":"mock"}');
    await assert.rejects(callJsonModel(connection, messages('http-error'), new AbortController().signal), /MODEL_JSON_REQUEST_FAILED/);
    await assert.rejects(callJsonModel(connection, messages('too-long'), new AbortController().signal), /MODEL_OUTPUT_TRUNCATED/);
    const controller = new AbortController(); controller.abort(new Error('synthetic cancellation'));
    await assert.rejects(callJsonModel(connection, messages('cancel'), controller.signal), /synthetic cancellation/);
    await assert.rejects(callJsonModel({...connection, protocol: 'anthropic-messages'}, messages('wrong-protocol'), new AbortController().signal), /MODEL_PROTOCOL_UNSUPPORTED/);
    assert.equal(received.length, 3);
  } finally {server.closeAllConnections(); await new Promise<void>(resolve => server.close(() => resolve()));}
});
