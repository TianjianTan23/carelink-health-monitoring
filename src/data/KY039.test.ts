import {describe,it,expect,vi} from 'vitest';
import {HardwareBridgeService,HardwarePayloadSchema,validateHardwareConfig} from './HardwareBridgeService';
import {HardwareDataService} from './HardwareDataService';
import {hardwareConfig,hardwareFixture} from '../test/hardwareFixture';
import {SensorReadingSchema} from './models';
import {heartRateInfo,metricKeys,sampleUsable,status,value} from '../ui/presentation';
import {makeReading} from '../../dist/service.js';
import {triage} from '../../dist/rules.js';
import rules from '../../shared/demo-rules.json';
const anchor=Date.parse('2026-10-26T04:00:00Z');
function fixture(){const f=hardwareFixture(new Date(anchor).toISOString());Object.assign(f.data,{heart_rate_bpm:76,heart_rate_ok:true,heart_rate_sensor:'KY-039',heart_rate_connected:true,heart_rate_algorithm_validated:true,heart_rate_quality:'good',heart_rate_measured_at:new Date(anchor).toISOString()});return f;}
async function read(override:Record<string,unknown>={},confirmed=false){const f=fixture();Object.assign(f.data,override);const bridge=new HardwareBridgeService({...hardwareConfig,heartRateContractConfirmed:confirmed});vi.spyOn(bridge,'latest').mockResolvedValue(f);const service=new HardwareDataService(bridge,()=>anchor);await service.getSession();const [p]=await service.refresh();return {service,reading:p.reading!};}
describe('KY-039 is a computed, independently timestamped heart-rate channel',()=>{
 it('defaults to unvalidated even with a plausible BPM, good flag and connected wiring',async()=>{
  const {service,reading}=await read();expect(value(reading,'hr',service.rules,'en',anchor).text).toBe('—');expect(heartRateInfo(reading,service.rules,'en',anchor).state).toBe('Heart-rate calculation not yet validated');
  expect(validateHardwareConfig({...hardwareConfig,heartRateContractConfirmed:undefined}).heartRateContractConfirmed).toBe(false);
 });
 it('shows only explicitly confirmed computed BPM and preserves the heart sample timestamp',async()=>{
  const {service,reading}=await read({},true);expect(SensorReadingSchema.safeParse(reading).success).toBe(true);expect(value(reading,'hr',service.rules,'en',anchor).text).toBe('76');expect(reading.metrics.hr.measuredAt).toBe(new Date(anchor).toISOString());expect(status(reading,'hardware',service.rules,'en',anchor).level).toBe('unknown');expect(reading.fall.active).toBe(false);
 });
 it.each([
  {heart_rate_bpm:null},{heart_rate_bpm:0},{heart_rate_bpm:-10},{heart_rate_bpm:NaN},
  {heart_rate_ok:false},{heart_rate_connected:false},{heart_rate_connected:undefined},
  {heart_rate_sensor:'MAX30102'},{heart_rate_sensor:undefined},{heart_rate_algorithm_validated:false},
  {heart_rate_quality:'poor'},{heart_rate_quality:undefined},{heart_rate_measured_at:null},{heart_rate_measured_at:'invalid'},
  {heart_rate_measured_at:new Date(anchor-6000).toISOString()},{heart_rate_measured_at:new Date(anchor+6000).toISOString()},
 ])('rejects missing or invalid evidence without losing temperatures and motion: %j',async override=>{
  const {service,reading}=await read(override,true);expect(value(reading,'hr',service.rules,'en',anchor).text).toBe('—');expect(sampleUsable(reading,'hr',service.rules)).toBe(false);expect(value(reading,'temp',service.rules,'en',anchor).text).toBe('25.87');expect(value(reading,'motion',service.rules,'en',anchor).text).toBe('0.92');
 });
 it('keeps raw ADC separate, never estimates BPM, and waits when all heart fields are missing',async()=>{
  const {service,reading}=await read({heart_rate_bpm:undefined,heart_rate_measured_at:null,heart_rate_connected:undefined,heart_signal_raw:2262},true);
  expect(reading.hardware?.rawSignalAdc).toBe(2262);expect(reading.metrics.hr.value).toBeNull();expect(value(reading,'hr',service.rules,'en',anchor).text).toBe('—');
  const {reading:r}=await read({heart_rate_bpm:undefined,heart_rate_connected:undefined,heart_signal_raw:undefined,heart_rate_ok:undefined,heart_rate_sensor:undefined},false);expect(r.metrics.hr.state).toBe('waiting');
 });
 it('rejects string BPM and truthy validity flags at the transport boundary',()=>{
  expect(HardwarePayloadSchema.safeParse({...fixture().data,heart_rate_bpm:'76'}).success).toBe(false);expect(HardwarePayloadSchema.safeParse({...fixture().data,heart_rate_ok:'true'}).success).toBe(false);
 });
 it('ages the heart sample even if the overall report timestamp advances',async()=>{
  const {service,reading}=await read({},true);const updated={...reading,measuredAt:new Date(anchor+6000).toISOString(),receivedAt:new Date(anchor+6000).toISOString()};expect(value(updated,'hr',service.rules,'en',anchor+6000).text).toBe('—');expect(sampleUsable(updated,'hr',service.rules)).toBe(false);
 });
});
it('keeps optional retired wire fields compatible but outside product metrics and mock grading',()=>{
 expect(metricKeys).toEqual(['hr','temp']);const r=SensorReadingSchema.parse(makeReading('p004','normal',anchor));expect(r.metrics.spo2?.value).toBeNull();r.metrics.spo2={value:12,quality:'good'};expect(triage(r,rules,anchor).level).toBe('green');delete r.metrics.spo2;expect(SensorReadingSchema.safeParse(r).success).toBe(true);
});
