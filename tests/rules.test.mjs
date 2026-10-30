import test from 'node:test';
import assert from 'node:assert/strict';
import {DEFAULT_RULES,triage,displayMetric,severity,lcdFrames} from '../dist/rules.js';
import {makeReading,MockService,ApiService} from '../dist/service.js';
const now=Date.now();
test('triage covers all demo scenes and distinguishes invalid data from healthy data',()=>{
  const expected={normal:'green',mild:'yellow',warm:'yellow',severe:'red',fall:'red',poor:'unknown',unavailable:'unknown',offline:'unknown',stale:'unknown',noData:'unknown'};
  for(const [scene,level] of Object.entries(expected))assert.equal(triage(makeReading('p001',scene,now),DEFAULT_RULES,now).level,level,scene);
});
test('fall stays red even when sensor is offline; known abnormalities survive incomplete data',()=>{
  const r=makeReading('p001','fall',now);r.connected=false;assert.equal(triage(r,DEFAULT_RULES,now).level,'red');assert.equal(triage(r,DEFAULT_RULES,now).incomplete,true);
  const a=makeReading('p001','mild',now);a.metrics.spo2={value:null,quality:'unavailable'};assert.equal(triage(a,DEFAULT_RULES,now).level,'yellow');
});
test('poor/absent/expired measurements never show as valid current numbers',()=>{
  for(const scene of ['poor','unavailable','offline','stale','noData'])assert.equal(displayMetric(makeReading('p001',scene,now),'hr',DEFAULT_RULES,now).text,'—',scene);
  const bad=makeReading('p001','normal',now);bad.metrics.hr.value=NaN;assert.equal(displayMetric(bad,'hr',DEFAULT_RULES,now).text,'—');assert.equal(triage(bad,DEFAULT_RULES,now).level,'unknown');
});
test('configurable bounds and exact boundary behavior',()=>{
  assert.equal(severity('hr',45),'yellow');assert.equal(severity('hr',44.9),'red');assert.equal(severity('hr',60),'green');assert.equal(severity('hr',100),'green');assert.equal(severity('hr',130),'yellow');assert.equal(severity('hr',131),'red');
  assert.equal(severity('spo2',90),'yellow');assert.equal(severity('spo2',95),'green');
  const rules=structuredClone(DEFAULT_RULES);rules.hr.mildHigh=70;assert.equal(triage(makeReading('p001','normal',now),rules,now).level,'yellow');
});
test('stale after timeout, future/missing timestamp is not green',()=>{
  const r=makeReading('p001','normal',now);assert.equal(triage(r,DEFAULT_RULES,now+30001).level,'unknown');r.measuredAt='invalid';assert.equal(triage(r,DEFAULT_RULES,now).level,'unknown');r.measuredAt=new Date(now+60000).toISOString();assert.equal(triage(r,DEFAULT_RULES,now).level,'unknown');
});
test('1602 frames always have exactly two ASCII rows of 16 characters; alarm takes priority',()=>{
  for(const scene of ['normal','mild','severe','fall','poor','unavailable','offline','stale','noData'])for(const frame of lcdFrames(makeReading('p001',scene,now),DEFAULT_RULES,now)){assert.equal(frame.length,2);for(const row of frame){assert.equal(row.length,16);assert.match(row,/^[\x20-\x7e]{16}$/);}}
  assert.match(lcdFrames(makeReading('p001','fall',now),DEFAULT_RULES,now)[0][0],/FALL DETECTED/);
  const a=lcdFrames(makeReading('p001','unavailable',now),DEFAULT_RULES,now);assert.match(a[0][0],/HR:--- BPM/);
});
test('patient-scoped scenarios, history windows, no fake AI and reset',async()=>{
  const s=new MockService();const all=await s.getPatients();assert.equal(all.length,8);assert.equal(new Set(all.map(p=>p.id)).size,8);
  s.setScenario('p004','unavailable');assert.equal((await s.getPatient('p004')).reading.metrics.hr.value,null);assert.equal((await s.getPatient('p005')).reading.scenario,'normal');
  for(const scene of ['normal','stale','noData']){s.setScenario('p004',scene);const h=await s.getHistory('p004');assert.equal(h.length,scene==='normal'?21:scene==='noData'?0:15);assert(h.every(r=>Date.parse(r.measuredAt)>=s.anchor-600000&&Date.parse(r.measuredAt)<=s.anchor));assert(h.every(r=>r.ai.result===null&&r.source==='mock'));}
  s.reset();assert.equal((await s.getPatient('p004')).reading.scenario,'normal');assert.deepEqual(await s.getHistory('missing'),[]);
});
test('API adapter propagates failures, never replaces errors with fake data',async()=>{
  const old=global.fetch;global.fetch=async()=>({ok:false,status:503});try{await assert.rejects(new ApiService().getPatients(),/API 503/);}finally{global.fetch=old;}
});

test('valid optional SpO2 remains safety-relevant without becoming a required sensor',()=>{
 const r=makeReading('p001','normal',now);r.metrics.spo2={value:89.9,quality:'good'};
 assert.equal(triage(r,DEFAULT_RULES,now).level,'red','valid severe SpO2 cannot be ignored by the display metric list');
 delete r.metrics.spo2;assert.equal(triage(r,DEFAULT_RULES,now).level,'green','missing optional sensor does not invent a requirement');
 r.metrics.spo2={value:80,quality:'good',available:false};assert.equal(triage(r,DEFAULT_RULES,now).level,'green','explicitly absent optional sensor is not a valid measurement');
});
