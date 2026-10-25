import test from 'node:test';
import assert from 'node:assert/strict';
import {translate,getLanguage,setLanguage,LANGUAGE_STORAGE_KEY} from '../dist/i18n.js';
import {MockService,makeReading,SCENARIOS} from '../dist/service.js';
import {triage,displayMetric,DEFAULT_RULES,lcdFrames} from '../dist/rules.js';

test('dynamic labels preserve counts, ages, IDs and measured units',()=>{
  assert.equal(translate('2 位患者需要优先查看','en'),'2 patients need urgent review');
  assert.equal(translate('女 · 76 岁 ｜ 201-01 床','en'),'Female · 76 years ｜ Bed 201-01');
  assert.equal(translate('查看林知秋详情，优先查看','en'),'View Lin Zhiqiu: Review urgently');
  assert.equal(translate('心率最近十分钟模拟趋势，最低 72.0，最高 74.0 bpm','en'),'Mock Heart rate trend over 10 minutes; minimum 72.0, maximum 74.0 bpm');
  assert.equal(translate('第 1 / 2 页 · 每 3 秒','en'),'Page 1 / 2 · Every 3 seconds');
  assert.equal(translate('KY-039 · 76 BPM · 36.6 °C · p004','en'),'KY-039 · 76 BPM · 36.6 °C · p004');
});

test('every mock profile and sensor-quality scene has English presentation text',async()=>{
  const service=new MockService();
  for(const p of await service.getPatients())for(const text of [p.name,p.sex,p.history,p.allergies])assert.doesNotMatch(translate(text,'en'),/[\u4e00-\u9fff]/,text);
  const now=Date.now();
  for(const scene of Object.keys(SCENARIOS)){
    const reading=makeReading('p001',scene,now);
    const messages=[SCENARIOS[scene],...triage(reading,DEFAULT_RULES,now).reasons,...['hr','temp'].map(k=>displayMetric(reading,k,DEFAULT_RULES,now).note)];
    for(const message of messages)assert.doesNotMatch(translate(message,'en'),/[\u4e00-\u9fff]/,`${scene}: ${message}`);
  }
});

test('switching language leaves sensor state, numeric classification and 1602 frames unchanged',()=>{
  const now=Date.now(),reading=makeReading('p001','fall',now),before=structuredClone(reading);
  const frames=lcdFrames(reading,DEFAULT_RULES,now);
  setLanguage('en');assert.equal(getLanguage(),'en');assert.equal(translate('设备离线'),'Device offline');
  assert.equal(triage(reading,DEFAULT_RULES,now).level,'red');assert.deepEqual(reading,before);assert.deepEqual(lcdFrames(reading,DEFAULT_RULES,now),frames);
  setLanguage('zh');assert.equal(translate('设备离线'),'设备离线');assert.equal(translate('未经翻译的用户内容'),'未经翻译的用户内容');
});

test('language preference persists when storage works and fails gracefully when blocked',()=>{
  const descriptor=Object.getOwnPropertyDescriptor(globalThis,'localStorage');
  const values=new Map();
  try{
    Object.defineProperty(globalThis,'localStorage',{configurable:true,value:{setItem:(k,v)=>values.set(k,v)}});
    setLanguage('en');assert.equal(values.get(LANGUAGE_STORAGE_KEY),'en');
    Object.defineProperty(globalThis,'localStorage',{configurable:true,get(){throw new Error('Storage blocked');}});
    assert.doesNotThrow(()=>setLanguage('zh'));assert.equal(getLanguage(),'zh');
  }finally{if(descriptor)Object.defineProperty(globalThis,'localStorage',descriptor);else delete globalThis.localStorage;setLanguage('zh');}
});
