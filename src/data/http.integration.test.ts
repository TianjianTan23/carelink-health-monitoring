// @vitest-environment node
import {createServer} from 'node:http';
import {once} from 'node:events';
import {it,expect} from 'vitest';
import {LiveApiService} from './LiveApiService';
import {defaultConfig} from './config';
import sessions from '../../shared/demo-sessions.json';
import patients from '../../shared/api-examples/patients.json';
import {HardwareBridgeService} from './HardwareBridgeService';
import {hardwareConfig,hardwareFixture} from '../test/hardwareFixture';
it('executes real HTTP against an owned local fixture server: success, empty and failure',async()=>{
 let state:'success'|'empty'|'failure'='success';
 const server=createServer((req,res)=>{
  res.setHeader('Content-Type','application/json');
  if(req.url==='/api/session'){res.end(JSON.stringify(sessions.pro));return;}
  if(req.url==='/api/patients'){
   if(state==='failure'){res.statusCode=503;res.end('{"detail":"fixture failure"}');return;}
   res.end(JSON.stringify(state==='empty'?[]:patients));return;
  }
  res.statusCode=404;res.end('{}');
 });
 server.listen(0,'127.0.0.1');await once(server,'listening');
 try{
  const address=server.address();if(!address||typeof address==='string')throw new Error('Missing fixture address');
  const api=new LiveApiService({...defaultConfig,mode:'live',apiConfirmed:true,baseUrl:`http://127.0.0.1:${address.port}`});
  await api.getSession();expect(await api.getPatients()).toHaveLength(8);
  state='empty';expect(await api.getPatients()).toEqual([]);
  state='failure';await expect(api.getPatients()).rejects.toMatchObject({code:'http',status:503});
 }finally{await new Promise<void>((resolve,reject)=>server.close(error=>error?reject(error):resolve()));}
});
it('executes hardware HTTP requests, empty/restart responses, invalid data, timeout and cancellation',async()=>{
 let state:'ready'|'waiting'|'invalid'|'slow'='ready';
 const server=createServer((req,res)=>{
  if(req.url!=='/sensor-data/latest'){res.writeHead(404);res.end('{}');return;}
  res.setHeader('Content-Type','application/json');
  if(state==='slow')return;
  if(state==='waiting'){res.writeHead(503);res.end(JSON.stringify({detail:'No sensor data received yet'}));return;}
  res.end(JSON.stringify(state==='invalid'?{ok:true,data:{}}:hardwareFixture()));
 });
 server.listen(0,'127.0.0.1');await once(server,'listening');
 try{
  const address=server.address();if(!address||typeof address==='string')throw new Error('Missing fixture address');
  const bridge=new HardwareBridgeService({...hardwareConfig,baseUrl:`http://127.0.0.1:${address.port}`,requestTimeoutMs:500});
  expect((await bridge.latest()).data.accel_total_g).toBe(0.92);
  state='waiting';await expect(bridge.latest()).rejects.toMatchObject({code:'waiting'});
  state='invalid';await expect(bridge.latest()).rejects.toMatchObject({code:'invalid_data'});
  state='slow';await expect(bridge.latest()).rejects.toMatchObject({code:'network'});
  const controller=new AbortController();const request=bridge.latest(controller.signal);controller.abort();
  await expect(request).rejects.toMatchObject({code:'network'});
  state='ready';expect((await bridge.latest()).data.heart_rate_bpm).toBeNull();
 }finally{server.closeAllConnections();await new Promise<void>((resolve,reject)=>server.close(error=>error?reject(error):resolve()));}
});
