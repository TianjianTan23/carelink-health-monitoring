import {describe,it,expect} from 'vitest';
import {chartSeries} from './chart-series';
import {SensorReadingSchema} from '../data/models';
import {makeReading} from '../../dist/service.js';
const end=Date.parse('2026-10-29T00:01:00Z');
function sample(seconds:number,bpm:number|null,id?:string){
 const r=SensorReadingSchema.parse(makeReading('p004','normal'));
 r.measuredAt=new Date(end-seconds*1000).toISOString();
 r.metrics.hr={value:bpm,quality:bpm===null?'unavailable':'good',sampleId:id};return r;
}
describe('5-second trend aggregation',()=>{
 it('emits one median per completed interval and excludes the open interval',()=>{
  const points=chartSeries([sample(9,70),sample(8,80),sample(7,150),sample(2,99)],'hr',end-1000);
  expect(points).toEqual([{time:end-10000,value:80,count:3}]);
 });
 it('keeps missing intervals as gaps and never uses held values',()=>{
  const held=sample(8,null);held.metrics.hr.displayValue=76;held.metrics.hr.held=true;
  const p=chartSeries([sample(19,72),held,sample(4,80)],'hr',end);
  expect(p.map(x=>x.value)).toEqual([72,null,null,80]);
 });
 it('does not count repeated uploads of the same accepted beat twice',()=>{
  const p=chartSeries([sample(9,70,'beat-1'),sample(8,70,'beat-1'),sample(7,90,'beat-2')],'hr',end);
  expect(p[0]).toMatchObject({value:80,count:2});
 });
 it('preserves valid historical measurements when the device later goes offline',()=>{
  const r=sample(9,74);r.connected=false;
  expect(chartSeries([r],'hr',end)[0].value).toBe(74);
 });
 it('excludes poor quality and out-of-window records',()=>{
  const r=sample(9,130);r.metrics.hr.quality='poor';
  expect(chartSeries([r,sample(700,88)],'hr',end).every(p=>p.value===null)).toBe(true);
 });
});
