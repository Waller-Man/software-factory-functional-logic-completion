import { spawnSync } from 'node:child_process';
import { prepareDependencies, requireHost, root } from './dependencies.mjs';
await prepareDependencies();
const result = spawnSync(process.execPath, [requireHost.resolve('typescript/bin/tsc'), '--noEmit'], { cwd: root, stdio: 'inherit' });
process.exitCode = result.status ?? 1;
