// @vitest-environment node
import {createServer} from 'node:https';
import {request} from 'node:https';
import {execFileSync} from 'node:child_process';
import {mkdtempSync,readFileSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {once} from 'node:events';
import {it,expect} from 'vitest';
import {LiveApiService} from './LiveApiService';
import {defaultConfig} from './config';
import sessions from '../../shared/demo-sessions.json';
import patients from '../../shared/api-examples/patients.json';
it('executes verified TLS against an owned local fixture: success, empty and failure',async()=>{
 const directory=mkdtempSync(join(tmpdir(),'carelink-web-tls-'));
 let server:ReturnType<typeof createServer>|undefined;
 try{
  const key=join(directory,'fixture.key'),certificate=join(directory,'fixture.pem');
  execFileSync('openssl',['req','-x509','-newkey','rsa:2048','-nodes','-days','1','-subj','/CN=localhost','-addext','subjectAltName=DNS:localhost','-keyout',key,'-out',certificate],{stdio:'ignore',timeout:15000});
  const cert=readFileSync(certificate);
  let state:'success'|'empty'|'failure'='success';
  server=createServer({key:readFileSync(key),cert},(req,res)=>{
   res.setHeader('Content-Type','application/json');
   if(req.url==='/api/session'){res.end(JSON.stringify(sessions.pro));return;}
   if(req.url==='/api/patients'){
    if(state==='failure'){res.statusCode=503;res.end('{"detail":"fixture failure"}');return;}
    res.end(JSON.stringify(state==='empty'?[]:patients));return;
   }
   res.statusCode=404;res.end('{}');
  });
  server.listen(0,'127.0.0.1');await once(server,'listening');
  const address=server.address();if(!address||typeof address==='string')throw new Error('Missing fixture address');
  const transport:typeof fetch=async(input,init={})=>new Promise((resolve,reject)=>{
   const req=request(String(input),{ca:cert,rejectUnauthorized:true,family:4,method:init.method,headers:Object.fromEntries(new Headers(init.headers))},res=>{
    const chunks:Buffer[]=[];res.on('data',c=>chunks.push(c));res.on('end',()=>resolve(new Response(Buffer.concat(chunks),{status:res.statusCode})));
   });
   req.setTimeout(3000,()=>req.destroy(new Error('fixture timeout')));
   req.on('error',reject);req.end(typeof init.body==='string'?init.body:undefined);
  });
  const api=new LiveApiService({...defaultConfig,mode:'live',apiConfirmed:true,baseUrl:`https://localhost:${address.port}`},transport);
  await api.getSession();expect(await api.getPatients()).toHaveLength(8);
  state='empty';expect(await api.getPatients()).toEqual([]);
  state='failure';await expect(api.getPatients()).rejects.toMatchObject({code:'http',status:503});
  await expect(transport(`https://127.0.0.1:${address.port}/api/session`)).rejects.toBeInstanceOf(Error);
 }finally{
  if(server?.listening){server.closeAllConnections();await new Promise<void>((resolve,reject)=>server!.close(error=>error?reject(error):resolve()));}
  rmSync(directory,{recursive:true,force:true});
 }
});
