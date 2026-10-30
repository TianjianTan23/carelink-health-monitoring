import {it,expect} from 'vitest';
import {displayFrames,retainedHeart,status,value} from './presentation';
import {makeReading} from '../../dist/service.js';
import {SensorReadingSchema} from '../data/models';
import rules from '../../shared/demo-rules.json';
it('live data does not inherit demo numeric triage; backend assessment is explicit',()=>{
 const r=SensorReadingSchema.parse({...makeReading('p004','severe'),source:'device'});
 expect(status(r,'mock',rules,'en').level).toBe('red');expect(status(r,'live',rules,'en').level).toBe('unknown');
 r.assessment={origin:'backend',level:'yellow',reasons:['Team-defined alert'],assessedAt:new Date().toISOString(),ruleSetId:'team-1'};
 expect(status(r,'live',rules,'en')).toMatchObject({level:'yellow',origin:'Backend assessment'});
});
it('live LCD display never applies the demo vital thresholds',()=>{
 const r=SensorReadingSchema.parse({...makeReading('p004','severe'),source:'device'});
 expect(displayFrames(r,'live',rules).flat().join(' ')).not.toContain('VALUE ALERT');
 expect(displayFrames(r,'mock',rules).flat().join(' ')).toContain('VALUE ALERT');
 expect(displayFrames(r,'live',rules).every(frame=>frame.length===2&&frame.every(row=>row.length===16))).toBe(true);
});
it('unavailable, poor, null, offline, stale and explicit availability=false never show numeric current readings',()=>{
 for(const scene of ['poor','unavailable','offline','stale','noData']){const raw=makeReading('p004',scene);const r=raw?SensorReadingSchema.parse(raw):null;expect(value(r,'hr',rules,'en').text).toBe('—');}
 const r=SensorReadingSchema.parse(makeReading('p004','normal'));r.metrics.hr.available=false;expect(value(r,'hr',rules,'en').text).toBe('—');
 r.metrics.hr.value=null;r.metrics.hr.available=true;expect(value(r,'hr',rules,'en').text).toBe('—');
});

it('optional SpO2 displays supplied values and never coerces absent or invalid readings to zero',()=>{
 const r=SensorReadingSchema.parse({...makeReading('p004','normal'),source:'device'});
 delete r.metrics.spo2;expect(value(r,'spo2',rules,'en').valid).toBe(false);
 r.metrics.spo2={value:null,quality:'unavailable',available:false};expect(value(r,'spo2',rules,'en').text).toBe('—');
 r.metrics.spo2={value:97,quality:'good',available:true};expect(value(r,'spo2',rules,'en').text).toBe('97');
 r.metrics.spo2.quality='poor';expect(value(r,'spo2',rules,'en').text).toBe('—');
 r.metrics.spo2.quality='good';r.measuredAt=new Date(Date.now()-120000).toISOString();expect(value(r,'spo2',rules,'en').text).toBe('—');
});

it('retains a real pulse for under six seconds with finger contact, then shows no held value',()=>{
 const now=Date.now(),reading=SensorReadingSchema.parse({...makeReading('p004','normal'),source:'device'});
 reading.connected=true;reading.raw={accel_m_s2:null,gyro_deg_s:null,ir:2100,red:null,object_temperature_c:null,ambient_temperature_c:null};
 const last={value:76,measuredAt:new Date(now-5000).toISOString()};
 expect(retainedHeart(last,reading,now)).toEqual(last);
 expect(retainedHeart(last,reading,now+1000)).toBeNull();
 reading.raw.ir=100;expect(retainedHeart(last,reading,now)).toBeNull();
});
