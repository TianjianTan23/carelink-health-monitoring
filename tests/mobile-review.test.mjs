import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFile} from 'node:fs/promises';
import {randomUUID} from 'node:crypto';

// Exercises authored UI state and rendered content without browser automation.
// This does not measure CSS layout or substitute for an iPhone build.
async function harness({blockedStorage=false,hasCrypto=true}={}){
 const html=await readFile(new URL('../work/carelink-iphone-review.html',import.meta.url),'utf8');
 const source=html.match(/<script>([\s\S]*)<\/script>/)[1];
 const events={},app={innerHTML:''},dialog={returnValue:'',querySelector:()=>({textContent:''}),showModal(){this.open=true;},addEventListener(type,handler){this[type]=handler;}};
 const fields={'#app':app,'#confirm':dialog,'#username':{value:'demo@carelink.example'},'#password':{value:'demo1234'},'#search':{value:''}};
 const context=vm.createContext({console,structuredClone,crypto:hasCrypto?{randomUUID}:{},localStorage:{getItem:()=>{if(blockedStorage)throw new Error('Storage blocked');return null;},setItem:()=>{if(blockedStorage)throw new Error('Storage blocked');}},document:{documentElement:{},body:{dataset:{}},querySelector:s=>fields[s],addEventListener:(name,handler)=>events[name]=handler}});
 await vm.runInContext(source,context);
 return {app,fields,dialog,eval:code=>vm.runInContext(code,context),
  click:async(action,extra={})=>events.click({target:{closest:()=>({dataset:{action,...extra},disabled:false})}}),
  submit:async id=>events.submit({preventDefault(){},target:{id}}),
  change:async(id,value,checked)=>events.change({target:{id,value,checked}})};
}

test('offline bundle: login validation, both modes, scoped navigation and languages',async()=>{
 const h=await harness();
 assert.match(h.app.innerHTML,/id="username"/);assert.match(h.app.innerHTML,/id="password"/);
 h.fields['#username'].value=' ';await h.submit('loginForm');assert.match(h.app.innerHTML,/请输入邮箱或用户名/);
 h.fields['#username'].value='demo';h.fields['#password'].value='bad';await h.submit('loginForm');assert.match(h.app.innerHTML,/登录失败（模拟）/);
 h.fields['#password'].value='demo1234';await h.click('loginmode',{value:'basic'});await h.submit('loginForm');
 assert.equal(h.eval('visible().length'),1);assert.equal(h.eval('visible()[0].id'),'p004');assert.match(h.app.innerHTML,/许望舒/);assert.doesNotMatch(h.app.innerHTML,/林知秋/);
 await h.click('patient',{id:'p001'});assert.equal(h.eval('state.page'),'home');
 await h.click('language');assert.match(h.app.innerHTML,/Last successful update/);assert.match(h.app.innerHTML,/Xu Wangshu/);
 await h.click('switchmode');assert.equal(h.eval('visible().length'),8);assert.match(h.app.innerHTML,/Lin Zhiqiu/);
 await h.click('patient',{id:'p001'});assert.match(h.app.innerHTML,/Last 10 minutes/);assert.match(h.app.innerHTML,/Raw sensor data/);assert.match(h.app.innerHTML,/AI predictions/);
});

test('offline bundle: unavailable, poor, stale and connection failure never invent fresh values',async()=>{
 const h=await harness();await h.click('loginmode',{value:'basic'});await h.submit('loginForm');
 await h.click('scenario',{value:'unavailable'});assert.equal(h.eval('displayMetric(patient("p004").reading,"hr",mock.rules).text'),'—');
 assert.equal(h.eval('displayMetric(patient("p004").reading,"spo2",mock.rules).text'),'—');assert.match(h.app.innerHTML,/暂不可用/);
 await h.click('scenario',{value:'poor'});await h.click('language');assert.match(h.app.innerHTML,/Unreliable signal/);assert.doesNotMatch(h.app.innerHTML,/148/);
 await h.click('scenario',{value:'stale'});assert.match(h.app.innerHTML,/Readings are stale/);assert.equal(h.eval('displayMetric(patient("p004").reading,"temp",mock.rules).text'),'—');
 const time=h.eval('state.lastUpdate');await h.change('fail',undefined,true);assert.equal(h.eval('state.lastUpdate'),time);assert.match(h.app.innerHTML,/Connection failed \(simulated\)/);
});

test('offline bundle: alert details, local confirmation, history and feed states',async()=>{
 const h=await harness();await h.submit('loginForm');await h.click('nav',{page:'alerts'});
 const id=h.eval('permittedAlerts().find(a=>a.patientID==="p001").id');await h.click('alert',{id});assert.match(h.app.innerHTML,/告警详情/);
 await h.click('ack');assert.equal(h.dialog.open,true);h.dialog.returnValue='confirm';await h.dialog.close({target:h.dialog});assert.ok(h.eval('permittedAlerts().find(a=>a.patientID==="p001").acknowledgedAt'));
 const count=h.eval('state.alerts.length');await h.click('refresh');assert.equal(h.eval('state.alerts.length'),count);assert.equal(h.eval('report(patient("p001")).level'),'red');
 await h.click('patient',{id:'p001'});await h.click('scenario',{value:'normal'});assert.ok(h.eval('state.alerts.find(a=>a.id===state.alertID).resolvedAt'));
 await h.click('nav',{page:'alerts'});await h.change('feed','failed');assert.match(h.app.innerHTML,/告警加载失败（模拟）/);
 await h.change('feed','empty');assert.match(h.app.innerHTML,/暂无告警记录（模拟）/);
 await h.change('feed','loading');assert.match(h.app.innerHTML,/正在加载（模拟）/);
 await h.click('feedlive');assert.match(h.app.innerHTML,/本地已确认/);
});


test('offline bundle: optional browser storage and UUID API may be unavailable',async()=>{
 const h=await harness({blockedStorage:true,hasCrypto:false});
 await h.submit('loginForm');assert.equal(h.eval('visible().length'),8);
 assert.ok(h.eval('state.alerts.length')>0);
 await h.click('language');assert.match(h.app.innerHTML,/Patients/);
});
