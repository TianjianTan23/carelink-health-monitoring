import {writeFileSync} from 'node:fs';
import {makeReading} from '../dist/service.js';
import {DEFAULT_RULES,triage} from '../dist/rules.js';
const now=Date.parse('2026-10-20T03:30:00.000Z');
const vectors=[];
function add(name,reading,time=now){vectors.push({name,now:new Date(time).toISOString(),reading,expected:triage(reading,DEFAULT_RULES,time).level});}
for(const scene of ['normal','mild','warm','severe','fall','poor','unavailable','offline','stale','noData'])add(scene,makeReading('p001',scene,now));
for(const key of ['hr','spo2','temp']){
  const values=key==='hr'?[44.9,45,60,100,130,130.1]:key==='spo2'?[89.9,90,95,98]:[33.9,34,35.5,37.5,39,39.1];
  for(const value of values){const r=makeReading('p001','normal',now);r.metrics[key].value=value;add(`${key}-${value}`,r);}
}
const fallOffline=makeReading('p001','fall',now);fallOffline.connected=false;add('unresolved-fall-offline',fallOffline);
const partial=makeReading('p001','mild',now);partial.metrics.spo2={value:null,quality:'unavailable'};add('known-mild-with-missing-data',partial);
add('reading-timeout',makeReading('p001','normal',now),now+30001);
writeFileSync(new URL('../shared/triage-vectors.json',import.meta.url),JSON.stringify(vectors,null,2)+'\n');
