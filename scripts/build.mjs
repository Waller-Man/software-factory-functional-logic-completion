/** Bundle the supplied SDK into a Host-only plugin; no frontend or Remote build. */
import {writeFile, readFile} from 'node:fs/promises';
import {join} from 'node:path';
import {pathToFileURL} from 'node:url';
import {root, host, requireHost, prepareDependencies} from './dependencies.mjs';
await prepareDependencies();
const {build} = await import(pathToFileURL(requireHost.resolve('tsdown')));
await build({config: false, entry: {index: join(root, 'src/index.ts')}, outDir: join(root, 'lib'),
  platform: 'node', format: 'esm', clean: true, dts: false,
  deps: {neverBundle: [/^@deepseek-ai\//], alwaysBundle: ['@software-factory/runtime-sdk']},
  outputOptions: {entryFileNames: '[name].js'}});
await writeFile(join(root, 'THIRD_PARTY_NOTICES.md'),
  '# Third-party notices\n\nDSH and its dependencies are provided by the host.\n\n## DSH\n\n'
  + await readFile(join(host, 'LICENSE'), 'utf8')
  + '\n## Software factory Runtime SDK 0.1.0\n\nBundled from vendor/software-factory-runtime-sdk-0.1.0.tgz, supplied by the software factory project.\n');
console.log('Built Host-only ReqCompleter Run plugin. SDK bundled; no profile changes.');
