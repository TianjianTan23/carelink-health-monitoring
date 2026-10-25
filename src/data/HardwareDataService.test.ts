import {describe,it,expect,vi} from 'vitest';
import {HardwareDataService} from './HardwareDataService';
import {HardwareBridgeService,HardwareBridgeError} from './HardwareBridgeService';
import {hardwareConfig,hardwareFixture} from '../test/hardwareFixture';
import {SensorReadingSchema} from './models';
import {displayFrames,status,value} from '../ui/presentation';
function setup(){let now=Date.now();const bridge=new HardwareBridgeService(hardwareConfig);const latest=vi.spyOn(bridge,'latest').mockResolvedValue(hardwareFixture(new Date(now).toISOString()));const data=new HardwareDataService(bridge,()=>now);return {bridge,latest,data,advance:(ms:number)=>{now+=ms;return now;}};}
describe('hardware adapter within the full DataService contract',()=>{
 it('maps temperatures and g without invented vitals, a fall classifier or a patient identity',async()=>{
  const {data}=setup();await data.getSession();const [p]=await data.refresh();const r=SensorReadingSchema.parse(p.reading);
  expect(p.profileKind).toBe('device');expect(data.metricKeys).toEqual(['hr','temp','ambient','motion']);expect(r.metrics.temp.value).toBe(25.87);expect(r.metrics.ambient?.value).toBe(25.89);expect(r.metrics.motion?.value).toBe(0.92);
  expect(r.metrics.hr).toMatchObject({value:null,quality:'unavailable'});expect(r.metrics.spo2).toBeUndefined();expect(r.fall).toEqual({active:false,quality:'unavailable'});
  expect(r.hardware?.accelG).toEqual({x:-0.56,y:-0.24,z:0.68});expect(r.raw?.accel_m_s2).toBeNull();expect(r.hardware?.timestampBasis).toBe('bridge_received');
  expect(status(r,'hardware',data.rules,'en').level).toBe('unknown');expect(status(r,'hardware',data.rules,'en').reasons.join()).toContain('not yet validated');
  const frames=displayFrames(r,'hardware',data.rules).flat().join();expect(frames).not.toMatch(/O2|FALL DETECTED/);
 });
 it('ignores legacy HR even if the bridge reports it as valid and hides channels with bad validity flags',async()=>{
  const {data,latest}=setup();const fixture=hardwareFixture();fixture.data.heart_rate_ok=true;fixture.data.heart_rate_bpm=72;fixture.data.mpu6050_ok=false;fixture.data.mlx90614_ok=false;latest.mockResolvedValue(fixture);
  await data.getSession();const [p]=await data.refresh();for(const key of ['temp','ambient','motion','hr'] as const)expect(value(p.reading,key,data.rules,'en').text).toBe('—');
 });
 it('retains only unique actual session samples, ages unchanged bridge responses, and never invents a trend',async()=>{
  const {data,advance,latest}=setup();await data.getSession();const [p]=await data.refresh();await data.refresh();expect(await data.getReadings(p.id)).toHaveLength(1);
  advance(6000);await data.refresh();expect(value((await data.getPatient(p.id))!.reading,'temp',data.rules,'en',Date.parse(p.reading!.receivedAt)+6000).text).toBe('—');
  latest.mockResolvedValue(hardwareFixture(new Date(advance(1000)).toISOString()));await data.refresh();expect(await data.getReadings(p.id)).toHaveLength(2);
  advance(600001);expect(await data.getReadings(p.id)).toHaveLength(0);
 });
 it('marks raw alarm episodes as unvalidated motion, deduplicates them and scopes local review to Pro',async()=>{
  const {data,latest,advance}=setup();await data.getSession();const [p]=await data.refresh();await data.refresh();const [event]=await data.getAlerts();expect(event.type).toBe('raw_firmware_alarm');expect(event.severity).toBe('unknown');expect(await data.getAlerts()).toHaveLength(1);
  await data.getSession('basic');await expect(data.acknowledgeAlert(event.id)).rejects.toMatchObject({code:'forbidden'});await data.getSession('pro');expect((await data.acknowledgeAlert(event.id)).conditionActive).toBe(true);
  const f=hardwareFixture(new Date(advance(1000)).toISOString());f.data.alarm=false;latest.mockResolvedValue(f);await data.refresh();expect((await data.getAlerts())[0].status).toBe('resolved');expect((await data.getPatient(p.id))?.reading?.fall.active).toBe(false);
  latest.mockResolvedValue(hardwareFixture(new Date(advance(1000)).toISOString()));await data.refresh();expect(await data.getAlerts()).toHaveLength(2);expect((await data.getAlerts())[0].acknowledgedAt).toBeNull();
 });
 it('preserves original sample on network failure and clears it on documented bridge restart',async()=>{
  const {data,latest}=setup();await data.getSession();const [p]=await data.refresh();latest.mockRejectedValue(new HardwareBridgeError('network','offline'));await expect(data.refresh()).rejects.toThrow('offline');expect((await data.getPatient(p.id))?.reading?.receivedAt).toBe(p.reading?.receivedAt);expect(value((await data.getPatient(p.id))?.reading,'temp',data.rules,'en').text).toBe('—');
  latest.mockRejectedValue(new HardwareBridgeError('waiting','waiting',503));expect((await data.refresh())[0].reading).toBeNull();expect(await data.getReadings(p.id)).toHaveLength(0);expect((await data.getPredictions(p.id))[0]).toMatchObject({state:'not_connected',model:null,confidence:null});
 });
 it('requires a local workspace and rejects access outside the configured device scope',async()=>{
  const {data}=setup();await expect(data.refresh()).rejects.toMatchObject({code:'forbidden'});await data.getSession();await expect(data.getPatient('p001')).rejects.toMatchObject({code:'forbidden'});
 });
 it('shares one pending request between overlapping refreshes',async()=>{
  const {data,latest}=setup();await data.getSession();let resolve!:(v:ReturnType<typeof hardwareFixture>)=>void;latest.mockImplementation(()=>new Promise(r=>{resolve=r;}));const a=data.refresh(),b=data.refresh();expect(latest).toHaveBeenCalledTimes(1);resolve(hardwareFixture());await Promise.all([a,b]);
 });
});

it('keeps absent channels and alarm unknown instead of inventing zero or no-alarm readings',async()=>{
 const {data,latest}=setup();const f=hardwareFixture();delete f.data.alarm;delete f.data.accel_total_g;f.data.object_temp_c=null;delete f.data.ambient_temp_c;latest.mockResolvedValue(f);await data.getSession();const [p]=await data.refresh();expect(p.reading?.hardware?.rawAlarm).toBeNull();for(const key of ['temp','ambient','motion'] as const)expect(value(p.reading,key,data.rules,'en').text).toBe('—');expect(await data.getAlerts()).toHaveLength(0);
});
