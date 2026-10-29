import {it,expect} from 'vitest';
import {displayFrames,status,value} from './presentation';
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
 for(const scene of ['poor','unavailable','stale','noData']){const raw=makeReading('p004',scene);const r=raw?SensorReadingSchema.parse(raw):null;expect(value(r,'hr',rules,'en').text).toBe('—');}
 const r=SensorReadingSchema.parse(makeReading('p004','normal'));r.metrics.hr.available=false;expect(value(r,'hr',rules,'en').text).toBe('—');
 r.metrics.hr.value=null;r.metrics.hr.available=true;expect(value(r,'hr',rules,'en').text).toBe('—');
});

it('retains a labelled last valid heart rate for 30 seconds without claiming validity',()=>{
 const now=Date.now(),r=SensorReadingSchema.parse(makeReading('p004','normal'));
 r.connected=false;r.measuredAt=new Date(now-5000).toISOString();r.metrics.hr.displayValue=75;r.metrics.hr.lastValidAt=r.measuredAt;
 expect(value(r,'hr',rules,'en',now)).toMatchObject({text:'75',valid:false});
 expect(value(r,'hr',rules,'en',now).note).toContain('Last valid value');
 expect(value(r,'hr',rules,'en',now+31000).text).toBe('—');
 expect(status(r,'live',rules,'en',now).level).toBe('unknown');
});
