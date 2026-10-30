/** Bounded UTF-8 JSONL transport; stdout is never interpreted as a text answer. */
import {StringDecoder} from 'node:string_decoder';
import type {Readable,Writable} from 'node:stream';
import {CompletionError} from './contracts.ts';
import type {ModelMessage} from '@software-factory/runtime-sdk';

export interface WorkerFinal {iterations:number;converged:boolean;reached_iteration_limit:boolean;docx_path:string;[key:string]:unknown}
export type WorkerEvent =
  |{type:'model_request';id:string;runId:string;stage:string;module:string;messages:ModelMessage[]}
  |{type:'step';runId:string;step:string;status:string;[key:string]:unknown}
  |{type:'artifact';runId:string;path:string;kind:string;[key:string]:unknown}
  |{type:'error';runId:string;error:{code:string;message:string};[key:string]:unknown}
  |{type:'final';runId:string;result:WorkerFinal};

/** Decode one process message and reject invalid discriminators and values. */
export function workerEvent(raw:string,id:string):WorkerEvent{
  const value:unknown=JSON.parse(raw);
  if(!value||typeof value!=='object'||!('type'in value)||!('runId'in value)||value.runId!==id)throw new CompletionError('PROTOCOL_ERROR','Worker response has no matching task identifier.');
  const v=value as Record<string,unknown>;
  if(v.protocolVersion!==1)throw new CompletionError('PROTOCOL_VERSION','Worker protocol version does not match.');
  if(v.type==='model_request'){
    if(typeof v.id!=='string'||!/^[A-Za-z0-9_.:-]{1,160}$/.test(v.id)||typeof v.stage!=='string'||typeof v.module!=='string'||v.stage.length>200||v.module.length>200||!Array.isArray(v.messages)||v.messages.length!==2)throw new CompletionError('PROTOCOL_ERROR','Invalid model request.');
    for(const [i,m]of v.messages.entries())if(!m||typeof m!=='object'||m.role!==(i===0?'system':'user')||typeof m.content!=='string')throw new CompletionError('PROTOCOL_ERROR','The worker may send only its current system instruction and user prompt.');
  }else if(v.type==='step'){
    if(typeof v.step!=='string'||typeof v.status!=='string')throw new CompletionError('PROTOCOL_ERROR','Invalid step notification.');
  }else if(v.type==='artifact'){
    if(typeof v.path!=='string'||typeof v.kind!=='string')throw new CompletionError('PROTOCOL_ERROR','Invalid artifact notification.');
  }else if(v.type==='error'){
    const error=v.error;
    if(!error||typeof error!=='object'||!('code'in error)||typeof error.code!=='string'||!/^[A-Z][A-Z0-9_]{0,80}$/.test(error.code)||!('message'in error)||typeof error.message!=='string')throw new CompletionError('PROTOCOL_ERROR','Invalid worker failure.');
  }else if(v.type==='final'){
    const r=v.result;
    if(!r||typeof r!=='object'||!('iterations'in r)||!Number.isInteger(r.iterations)||typeof r.iterations!=='number'||r.iterations<0||!('converged'in r)||typeof r.converged!=='boolean'||!('reached_iteration_limit'in r)||typeof r.reached_iteration_limit!=='boolean'||!('docx_path'in r)||typeof r.docx_path!=='string')throw new CompletionError('PROTOCOL_ERROR','Invalid final worker result.');
  }else throw new CompletionError('PROTOCOL_ERROR','Unknown worker message.');
  return value as WorkerEvent;
}

/** Read complete lines without allowing an unbounded readline buffer. */
export async function* jsonLines(stream:Readable,maxBytes:number):AsyncGenerator<string>{
  const decoder=new StringDecoder('utf8');let buffer='';
  for await(const chunk of stream){
    buffer+=decoder.write(Buffer.isBuffer(chunk)?chunk:Buffer.from(chunk));
    let end:number;
    while((end=buffer.indexOf('\n'))>=0){
      const line=buffer.slice(0,end).replace(/\r$/,'');buffer=buffer.slice(end+1);
      if(Buffer.byteLength(line)>maxBytes)throw new CompletionError('PROTOCOL_LIMIT','Worker protocol line exceeds its limit.');
      if(line)yield line;
    }
    if(Buffer.byteLength(buffer)>maxBytes)throw new CompletionError('PROTOCOL_LIMIT','Worker protocol line exceeds its limit.');
  }
  buffer+=decoder.end();if(buffer.trim())throw new CompletionError('PROTOCOL_EOF','Worker stdout ended with an incomplete JSONL record.');
}

/** Await the write callback so protocol writes apply backpressure and surface broken pipes. */
export async function send(stream:Writable,value:unknown,maxBytes:number):Promise<void>{
  const line=JSON.stringify(value)+'\n';if(Buffer.byteLength(line)>maxBytes)throw new CompletionError('PROTOCOL_LIMIT','Bridge message exceeds its limit.');
  await new Promise<void>((resolve,reject)=>stream.write(line,'utf8',error=>error?reject(error):resolve()));
}
