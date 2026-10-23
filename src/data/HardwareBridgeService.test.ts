import {describe,it,expect,vi} from 'vitest';
import {HardwareBridgeService,hardwareFresh,loadHardwareConfig,validateHardwareConfig} from './HardwareBridgeService';
import {defaultConfig,validateConfig} from './config';
import {hardwareConfig,hardwareFixture} from '../test/hardwareFixture';

describe('independent hardware configuration and bridge transport',()=>{
 it('leaves default mock and generic live contracts intact',()=>{
  expect(defaultConfig.mode).toBe('mock');
  expect(()=>validateConfig({...defaultConfig,mode:'hardware'})).toThrow();
  expect(()=>validateConfig({...defaultConfig,mode:'live'})).toThrow(/not confirmed/);
  expect(validateHardwareConfig(hardwareConfig).mode).toBe('hardware');
  for(const baseUrl of ['//other.example','javascript:alert(1)','http://user:pass@localhost:8000','/bridge?x=1','/\\other.example'])
    expect(()=>validateHardwareConfig({...hardwareConfig,baseUrl})).toThrow();
  expect(()=>validateHardwareConfig({...hardwareConfig,pollIntervalMs:0})).toThrow();
 });
 it('loads the separate runtime config and reports missing/invalid configuration',async()=>{
  const transport=vi.fn().mockResolvedValueOnce(new Response(JSON.stringify(hardwareConfig))).mockResolvedValueOnce(new Response('{}',{status:404})).mockResolvedValueOnce(new Response('{}'));
  vi.stubGlobal('fetch',transport);
  try{expect(await loadHardwareConfig()).toEqual(hardwareConfig);await expect(loadHardwareConfig()).rejects.toThrow(/404/);await expect(loadHardwareConfig()).rejects.toThrow(/Invalid/);}finally{vi.unstubAllGlobals();}
 });
 it('uses only latest, omits credentials, disables cache and preserves g/°C/uptime/raw fields',async()=>{
  const fixture=hardwareFixture(),transport=vi.fn(async()=>new Response(JSON.stringify(fixture)));
  const bridge=new HardwareBridgeService(hardwareConfig,transport);
  const result=await bridge.latest();
  expect(result).toEqual(fixture);expect(result.data.heart_rate_bpm).toBeNull();
  expect(result.data.accel_x_g).toBe(-0.56);expect(result.data.object_temp_c).toBe(25.87);
  expect(result.data.alarm).toBe(true);expect(result.data.lcd_line_2).toBe('Body:25.8 C');
  expect(result.received_at).toBe(fixture.received_at);
  expect(transport).toHaveBeenCalledWith('/hardware-bridge/sensor-data/latest',expect.objectContaining({credentials:'omit',cache:'no-store',signal:expect.any(AbortSignal)}));
 });
 it('invokes the browser default fetch without binding it to the service instance',async()=>{
  const transport=vi.fn(function(this:unknown){
    if(this instanceof HardwareBridgeService)throw new TypeError('Illegal invocation');
    return Promise.resolve(new Response(JSON.stringify(hardwareFixture())));
  });
  vi.stubGlobal('fetch',transport);
  try{expect((await new HardwareBridgeService(hardwareConfig).latest()).data.device_id).toBe('esp32-01');}finally{vi.unstubAllGlobals();}
 });
 it('distinguishes the documented initial 503 from other HTTP failures',async()=>{
  const transport=vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({detail:'No sensor data received yet'}),{status:503})).mockResolvedValueOnce(new Response('{"detail":"upstream failed"}',{status:503})).mockResolvedValueOnce(new Response('{}',{status:500}));
  const bridge=new HardwareBridgeService(hardwareConfig,transport);
  await expect(bridge.latest()).rejects.toMatchObject({code:'waiting',status:503});
  await expect(bridge.latest()).rejects.toMatchObject({code:'http',status:503});
  await expect(bridge.latest()).rejects.toMatchObject({code:'http',status:500});
 });
 it.each([
  {ok:false}, {received_at:'2301685'}, {received_at:'not-a-date'},
  {data:{...hardwareFixture().data,mpu6050_ok:'true'}},
  {data:{...hardwareFixture().data,object_temp_c:'25.87'}},
  {data:{...hardwareFixture().data,device_id:'another-device'}},
 ])('rejects malformed, ambiguous or unexpected-device records: %j',async override=>{
  const bridge=new HardwareBridgeService(hardwareConfig,async()=>new Response(JSON.stringify({...hardwareFixture(),...override})));
  await expect(bridge.latest()).rejects.toMatchObject({code:'invalid_data'});
 });
 it('does not fill missing measurements or coerce null to zero',async()=>{
  const fixture=hardwareFixture();delete fixture.data.accel_x_g;fixture.data.object_temp_c=null;
  const bridge=new HardwareBridgeService(hardwareConfig,async()=>new Response(JSON.stringify(fixture)));
  const result=await bridge.latest();expect(result.data.accel_x_g).toBeUndefined();expect(result.data.object_temp_c).toBeNull();
 });
 it('propagates network and JSON failures without mock fallback',async()=>{
  await expect(new HardwareBridgeService(hardwareConfig,async()=>{throw new TypeError('offline');}).latest()).rejects.toMatchObject({code:'network'});
  await expect(new HardwareBridgeService(hardwareConfig,async()=>new Response('<html>bad gateway</html>')).latest()).rejects.toMatchObject({code:'invalid_data'});
 });
 it('uses bridge receive time for freshness and detects stopped/future samples',()=>{
  const now=Date.now(),snapshot=hardwareFixture(new Date(now-5000).toISOString());
  expect(hardwareFresh(snapshot,5000,now)).toBe(true);
  expect(hardwareFresh(snapshot,5000,now+1)).toBe(false);
  expect(hardwareFresh({...snapshot,received_at:new Date(now+6000).toISOString()},5000,now)).toBe(false);
  expect(hardwareFresh(null,5000,now)).toBe(false);
 });
});
