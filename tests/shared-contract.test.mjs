import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {DEMO_PATIENTS,DEMO_RULES,DEMO_SESSIONS} from '../dist/fixtures.js';
import {MockService} from '../dist/service.js';
import {triage,DEFAULT_RULES} from '../dist/rules.js';
const read=name=>JSON.parse(readFileSync(new URL(`../shared/${name}.json`,import.meta.url),'utf8'));

test('Web generated resources exactly match the JSON bundled by iOS',()=>{
  assert.deepEqual(DEMO_PATIENTS,read('demo-patients'));
  assert.deepEqual(DEMO_RULES,read('demo-rules'));
  assert.deepEqual(DEMO_SESSIONS,read('demo-sessions'));
  const schema=read('schema');
  for(const patient of DEMO_PATIENTS){
    for(const key of schema.$defs.Patient.required)assert(Object.hasOwn(patient,key),`${patient.id}: ${key}`);
    for(const key of schema.$defs.Reading.required)assert(Object.hasOwn(patient.reading,key),`reading: ${key}`);
    for(const metric of Object.values(patient.reading.metrics))assert(schema.$defs.Metric.properties.quality.enum.includes(metric.quality));
    assert.equal(patient.id,patient.reading.patientId);
  }
});
test('Web classifies the shared cross-language golden vectors consistently',()=>{
  for(const vector of read('triage-vectors'))assert.equal(triage(vector.reading,DEFAULT_RULES,Date.parse(vector.now)).level,vector.expected,vector.name);
});
test('Demo Pro and Basic sessions have distinct patient scopes and immutable fixtures',async()=>{
  const s=new MockService(),patients=await s.getPatients();
  const pro=await s.getSession('pro'),basic=await s.getSession('basic');
  assert.equal(pro.role,'clinician');assert.equal(pro.userId,'wyn');assert.equal(basic.role,'patient');assert.equal(basic.userId,'ttj');
  assert.equal(patients.filter(p=>pro.patientIds.includes(p.id)).length,8);
  assert.deepEqual(patients.filter(p=>basic.patientIds.includes(p.id)).map(p=>p.id),['p004']);
  basic.patientIds.push('p001');assert.deepEqual((await s.getSession('basic')).patientIds,['p004']);
});
