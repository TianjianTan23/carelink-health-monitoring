// @vitest-environment node
import {createServer,request} from 'node:http';
import {once} from 'node:events';
import {randomBytes} from 'node:crypto';
import {it,expect} from 'vitest';
import {LiveApiService} from './LiveApiService';
import {defaultConfig} from './config';
import sessions from '../../shared/demo-sessions.json';
import patients from '../../shared/api-examples/patients.json';
it('executes HTTP and sends session CSRF token for mutations',async()=>{
 let state:'success'|'empty'|'failure'='success',csrfReceived=false;
 const csrfToken=randomBytes(32).toString('hex');
 const server=createServer((req,res)=>{
  res.setHeader('Content-Type','application/json');
  if(req.url==='/api/session'){res.end(JSON.stringify({...sessions.pro,csrfToken}));return;}
  if(req.url==='/api/logout'){csrfReceived=req.method==='POST'&&req.headers['x-csrf-token']===csrfToken;res.statusCode=csrfReceived?200:403;res.end('{}');return;}
  if(req.url==='/api/patients'){
   if(state==='failure'){res.statusCode=503;res.end('{"detail":"fixture failure"}');return;}
   res.end(JSON.stringify(state==='empty'?[]:patients));return;
  }
  res.statusCode=404;res.end('{}');
 });
 server.listen(0,'127.0.0.1');await once(server,'listening');
 try{
  const address=server.address();if(!address||typeof address==='string')throw new Error('Missing fixture address');
  const transport:typeof fetch=(input,options={})=>new Promise((resolve,reject)=>{
   const req=request(String(input),{method:options.method,headers:Object.fromEntries(new Headers(options.headers))},res=>{
    let body='';res.setEncoding('utf8');res.on('data',chunk=>body+=chunk);res.on('end',()=>resolve(new Response(body,{status:res.statusCode})));
   });req.on('error',reject);req.end(typeof options.body==='string'?options.body:undefined);
  });
  const api=new LiveApiService({...defaultConfig,mode:'live',apiConfirmed:true,baseUrl:`http://127.0.0.1:${address.port}`},transport);
  await api.getSession();expect(await api.getPatients()).toHaveLength(8);
  state='empty';expect(await api.getPatients()).toEqual([]);
  state='failure';await expect(api.getPatients()).rejects.toMatchObject({code:'http',status:503});
  await api.logout();expect(csrfReceived).toBe(true);
  expect(()=>new LiveApiService({...defaultConfig,mode:'live',apiConfirmed:true,baseUrl:`http://127.0.0.1:${address.port}`})).not.toThrow();
 }finally{await new Promise<void>((resolve,reject)=>server.close(error=>error?reject(error):resolve()));}
});
