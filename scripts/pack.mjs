/** Package a built backend and stage a directory suitable for DSH installation. */
import {spawnSync, execFileSync} from 'node:child_process';
import {mkdir, readFile, writeFile} from 'node:fs/promises';
import {join} from 'node:path';
import {root} from './dependencies.mjs';
await readFile(join(root, 'lib/index.js'));
const artifacts = join(root, 'artifacts'); await mkdir(artifacts, {recursive: true});
const executable = process.platform === 'win32' ? (process.env.ComSpec ?? 'cmd.exe') : 'npm';
const args = process.platform === 'win32'
  ? ['/d', '/s', '/c', 'npm.cmd pack --ignore-scripts --json --pack-destination artifacts']
  : ['pack', '--ignore-scripts', '--json', '--pack-destination', 'artifacts'];
const result = spawnSync(executable, args, {cwd: root, encoding: 'utf8', windowsHide: true,
  env: {...process.env, npm_config_cache: join(root, '.work-temp/npm-cache')}});
if (result.status !== 0) throw new Error(result.stderr || 'npm pack failed');
const meta = JSON.parse(result.stdout)[0];
const files = meta.files.map(file => file.path);
for (const required of ['lib/index.js', 'package.json', 'cordis.patch.yml', 'icon.svg', 'locale/zh.json',
  'README.md', 'python/worker.py', 'python/reqcompleter_v2_0/pipeline.py', 'requirements/requirements-py312.lock.txt']) {
  if (!files.includes(required)) throw new Error('Package is missing ' + required);
}
if (files.some(file => /(^|\/)(node_modules|__pycache__|\.venv|tests|src)(\/|$)|\.pyc$|(^|\/)\.env/.test(file)
  || /^lib\/(client|wire|typert)/.test(file))) throw new Error('Unexpected development or legacy file in package');
const stage = join(artifacts, 'release/dsh-functional-logic-completion');
await mkdir(stage, {recursive: true});
execFileSync('tar', ['-xf', join(artifacts, meta.filename), '--strip-components', '1', '-C', stage], {windowsHide: true});
await writeFile(join(artifacts, 'package-check.json'), JSON.stringify({version: meta.version,
  tgz: meta.filename, installDirectory: stage, frontendIncluded: false, files}, null, 2) + '\n');
console.log(JSON.stringify({tgz: join(artifacts, meta.filename), installDirectory: stage, fileCount: files.length}));
