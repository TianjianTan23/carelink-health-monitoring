import type {MetricKey,SensorReading} from '../data/models';
export type ChartPoint={time:number;value:number|null;count:number};
export function chartSeries(readings:SensorReading[],metric:MetricKey,now:number,widthMs=5000):ChartPoint[]{
  const end=Math.floor(now/widthMs)*widthMs;
  const ordered=readings.slice().sort((a,b)=>Date.parse(a.measuredAt)-Date.parse(b.measuredAt));
  const buckets=new Map<number,number[]>(),seen=new Set<string>();
  let first=end;
  for(const r of ordered){
    const stamp=Date.parse(r.measuredAt),bucket=Math.floor(stamp/widthMs)*widthMs;
    if(!Number.isFinite(stamp)||stamp<end-600000||bucket>=end)continue;
    first=Math.min(first,bucket);
    const m=r.metrics[metric];
    if(m.value===null||!Number.isFinite(m.value)||m.quality!=='good'||m.available===false||m.held)continue;
    const key=m.sampleId??`${r.deviceId}:${stamp}`;
    if(seen.has(key))continue;seen.add(key);
    const values=buckets.get(bucket)??[];values.push(m.value);buckets.set(bucket,values);
  }
  const result:ChartPoint[]=[];
  for(let t=first;t<end;t+=widthMs){
    const values=(buckets.get(t)??[]).sort((a,b)=>a-b),middle=Math.floor(values.length/2);
    result.push({time:t,value:values.length?(values.length%2?values[middle]:(values[middle-1]+values[middle])/2):null,count:values.length});
  }
  return result;
}
