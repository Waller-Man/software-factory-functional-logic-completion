import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp, mkdir, readFile, writeFile} from 'node:fs/promises';
import {join, resolve} from 'node:path';
import {tmpdir} from 'node:os';
import {createRequire} from 'node:module';
import {runInNewContext} from 'node:vm';
import {boot, initProfile, readProfilePatches} from '@deepseek-ai/dsh-app-boot';
import Editor from '@deepseek-ai/dsh-config-editor';
import Settings from '@deepseek-ai/dsh-settings';
import {Config, snapshotOptions} from '../src/config.ts';

test('native settings persist; accepted edits do not alter an existing task snapshot', async () => {
  const home = await mkdtemp(join(tmpdir(), 'req-settings-')), dir = join(home, 'profile');
  initProfile(dir, ['req-settings-test']);
  const bundle = join(dir, 'node_modules/req-settings-test'); await mkdir(bundle, {recursive: true});
  await writeFile(join(home, 'package.json'), '{"name":"req-settings-check"}');
  await writeFile(join(bundle, 'package.json'), JSON.stringify({name: 'req-settings-test', version: '1.0.0', dsh: {bundle: {patch: './cordis.patch.yml'}}}));
  await writeFile(join(bundle, 'cordis.patch.yml'), JSON.stringify([{insert: [
    {id: 'config-editor', name: 'cordis:editor'}, {id: 'settings', name: 'cordis:settings'}, {id: 'req-settings', name: 'cordis:req'},
  ]}]));
  await writeFile(join(dir, 'cordis.yml'), '[]\n');
  const profile = {name: 'test', startedBundles: ['req-settings-test'], dir, patchPath: join(dir, 'cordis.patch.yml'), installAnchor: join(home, 'package.json'), cwd: home, home, overlays: []};
  const start = () => boot('dsh', join(dir, 'cordis.yml'), readProfilePatches('dsh', profile as never), async ctx => {
    ctx.provide('profileContext', profile as never);
    ctx.provide('appReady', {onReady: listener => {listener(); return () => {};}} as never);
    Object.assign(ctx.loader.builtins, {editor: Editor, settings: Settings, req: {Config, inject: ['settings'], apply(scope: any) {scope.effect(() => scope.settings.configure({auto: false}));}}});
  });
  const ctx = await start();
  try {
    const entry = [...ctx.loader.entries()].find(row => row.options.id === 'req-settings')!, fiber = entry.fiber!;
    const before = snapshotOptions(fiber.config as never), descriptor = ctx.settings.describe().find(row => row.ns === 'req-settings')!;
    assert.equal(before.maxIterations, 5); assert.equal(before.pythonPath, '');
    await ctx.settings.mutate('req-settings', [{op: 'set', path: ['pythonPath'], value: 'C:/runtime/python.exe'}, {op: 'set', path: ['maxIterations'], value: 3}], descriptor.revision);
    assert.equal(entry.fiber, fiber);
    assert.equal(snapshotOptions(fiber.config as never).maxIterations, 3);
    assert.equal(before.maxIterations, 5); assert.equal(before.pythonPath, '');
    assert.match(await readFile(profile.patchPath, 'utf8'), /C:\/runtime\/python.exe/);
    await assert.rejects(ctx.settings.mutate('req-settings', [{op: 'set', path: ['maxIterations'], value: 0}]));
  } finally {await ctx.fiber.dispose();}
  const restarted = await start();
  try {assert.equal(restarted.settings.describe().find(row => row.ns === 'req-settings')!.value.maxIterations, 3);}
  finally {await restarted.fiber.dispose();}
});

test('web form uses the correct row; saves via configForms and validates numeric limits', async () => {
  const host = resolve(process.env.DSH_SOURCE ?? '../DSH-Softwarefactory');
  const hostRequire = createRequire(join(host, 'package.json')), uiRequire = createRequire(join(host, 'packages/client/ui-primitives/package.json'));
  const {JSDOM} = hostRequire('jsdom'), dom = new JSDOM('<!doctype html><div id="root"></div>');
  const previous = new Map<string, PropertyDescriptor | undefined>();
  for (const [key, value] of Object.entries({window: dom.window, document: dom.window.document, HTMLElement: dom.window.HTMLElement, IS_REACT_ACT_ENVIRONMENT: true})) {
    previous.set(key, Object.getOwnPropertyDescriptor(globalThis, key)); Object.defineProperty(globalThis, key, {configurable: true, writable: true, value});
  }
  const React = uiRequire('react'), {createRoot} = uiRequire('react-dom/client'), root = createRoot(dom.window.document.getElementById('root'));
  const pkg = JSON.parse(await readFile('package.json', 'utf8')), row = pkg.name.endsWith('v2-1') ? 'functional-logic-completion-v2-1' : 'functional-logic-completion';
  let state = {status: 'ready', writable: true, revision: 1, value: {pythonPath: '', javaPath: 'java', plantumlJarPath: '', maxIterations: 5, maxConcurrent: 1}};
  const listeners = new Set<() => void>(); let artifact: any, component: any, registration: any, words: any, saves = 0;
  const scope = {getSnapshot: () => state, subscribe: (fn: () => void) => {listeners.add(fn); return () => listeners.delete(fn);},
    async mutate(ops: any[], revision: number) {assert.equal(revision, state.revision); saves++; const value = {...state.value}; for (const op of ops) value[op.path[0] as keyof typeof value] = op.value; state = {...state, revision: revision + 1, value}; listeners.forEach(fn => fn()); return true;}};
  try {
    runInNewContext(await readFile('client.js', 'utf8'), {window: {__ModuleLoader__: {load: (item: any) => {artifact = item;}}}});
    assert.equal(artifact.id, pkg.name);
    artifact.factory(uiRequire).apply({effect: (fn: Function) => fn(), locale: {register: (_ns: string, data: any) => {words = data;}},
      configForms: {get: (id: string) => {assert.equal(id, row); return scope;}},
      slots: {inject: (_ns: string, fn: Function) => fn(), register: (options: any, view: any) => {registration = options; component = view;}}});
    assert.equal(registration.key, pkg.name + '#' + row);
    await React.act(async () => root.render(React.createElement(component, {scope, t: (key: string) => words.zh[key]})));
    const input = (name: string) => dom.window.document.querySelector(`input[name="${name}"]`);
    const edit = async (name: string, value: string) => React.act(async () => {Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype, 'value')!.set!.call(input(name), value); input(name).dispatchEvent(new dom.window.Event('input', {bubbles: true}));});
    assert.equal(input('pythonPath').value, '');
    await edit('pythonPath', 'C:/venv/python.exe');
    await React.act(async () => dom.window.document.querySelector('form').dispatchEvent(new dom.window.Event('submit', {bubbles: true, cancelable: true})));
    assert.equal(saves, 1); assert.equal(state.value.pythonPath, 'C:/venv/python.exe'); assert.match(dom.window.document.body.textContent, /无需重启/);
    await edit('maxIterations', '0');
    await React.act(async () => dom.window.document.querySelector('form').dispatchEvent(new dom.window.Event('submit', {bubbles: true, cancelable: true})));
    assert.equal(saves, 1);
    assert.equal(input('functionTreeJsonMode'), null, 'JSON output is mandatory and has no user switch');
  } finally {
    await React.act(async () => root.unmount()); dom.window.close();
    for (const [key, descriptor] of previous) {if (descriptor) Object.defineProperty(globalThis, key, descriptor); else Reflect.deleteProperty(globalThis, key);}
  }
});
