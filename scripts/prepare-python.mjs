/** Explicit deployment preparation; never executed by plugin enable or a business task. */
import {spawnSync} from 'node:child_process';
import {mkdirSync,existsSync} from 'node:fs';
import {dirname,join,isAbsolute,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const base=process.argv[2];
if(!base||!isAbsolute(base))throw new Error('Usage: node scripts/prepare-python.mjs <absolute Python 3.12 executable>');
const destination=process.argv[3]?resolve(process.argv[3]):join(root,'.venv');
const temporary=join(root,'.work-temp');mkdirSync(temporary,{recursive:true});
const env={...process.env,TMP:temporary,TEMP:temporary,PIP_CACHE_DIR:join(temporary,'pip-cache')};
function run(exe,args){const result=spawnSync(exe,args,{cwd:root,env,stdio:'inherit',windowsHide:true});if(result.error)throw result.error;if(result.status!==0)throw new Error(`Python environment preparation failed (${result.status}).`);}
const python=join(destination,process.platform==='win32'?'Scripts':'bin',process.platform==='win32'?'python.exe':'python');
if(!existsSync(python))run(base,['-m','venv',destination]);
run(python,['-m','ensurepip','--upgrade']);
run(python,['-m','pip','install','--disable-pip-version-check','--retries','1','--timeout','30','--index-url','https://pypi.org/simple','-r',join(root,'requirements','requirements-py312.lock.txt')]);
run(python,['-B',join(root,'python','worker.py'),'--probe']);
console.log(`Prepared independent environment: ${python}`);
