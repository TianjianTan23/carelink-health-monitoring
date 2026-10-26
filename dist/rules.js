import {DEMO_RULES} from './fixtures.js';
// ONLY interaction/demo rules. Not validated clinical decision criteria.
export const DEFAULT_RULES = Object.freeze(DEMO_RULES);
export const METRICS = {
  hr:{name:'心率',unit:'bpm',sensor:'MAX30102',icon:'heart'},
  temp:{name:'温度',unit:'°C',sensor:'MLX90614 · 表面测温',icon:'temp'}
};
export const STATUS = {
  green:{label:'未见演示异常',short:'平稳',family:'目前数据平稳',icon:'check'},
  yellow:{label:'需要关注',short:'关注',family:'有一项数据需要关注',icon:'alert'},
  red:{label:'优先查看',short:'警报',family:'请尽快查看家人情况',icon:'alert'},
  unknown:{label:'数据待确认',short:'待确认',family:'暂时无法确认完整状态',icon:'wifi-off'}
};
export function isFresh(reading, rules=DEFAULT_RULES, now=Date.now()) {
  const age = now - Date.parse(reading?.measuredAt);
  return reading?.connected === true && Number.isFinite(age) && age >= -5000 && age <= rules.staleAfterSeconds * 1000;
}
export function usable(metric) { return metric?.quality === 'good' && typeof metric.value === 'number' && Number.isFinite(metric.value); }
export function severity(key,value,rules=DEFAULT_RULES) {
  const r=rules[key];
  if(key==='spo2') return value<r.severeLow?'red':value<r.mildLow?'yellow':'green';
  return value<r.severeLow || value>r.severeHigh ? 'red' : value<r.mildLow || value>r.mildHigh ? 'yellow' : 'green';
}
export function triage(reading,rules=DEFAULT_RULES,now=Date.now()) {
  if(!reading) return {level:'unknown',reasons:['尚无读数'],incomplete:true};
  const fresh=isFresh(reading,rules,now);
  const reasons=[]; const levels=[];
  // An unresolved fall event stays visible even when the device disconnects.
  if(reading.fall?.active===true) { levels.push('red'); reasons.push('检测到跌倒事件 · 待人工核实'); }
  let incomplete=!fresh || reading.fall?.quality!=='good';
  if(!fresh) reasons.push(reading.connected?'数据已过期':'设备离线');
  for(const key of Object.keys(METRICS)) {
    const m=reading.metrics?.[key];
    if(!fresh || !usable(m)) { incomplete=true; if(fresh) reasons.push(`${METRICS[key].name}${m?.quality==='poor'?'信号不稳':'暂不可用'}`); continue; }
    const level=severity(key,m.value,rules);levels.push(level);
    if(level!=='green') reasons.push(`${METRICS[key].name}${level==='red'?'超出演示严重范围':'超出演示平稳范围'}`);
  }
  if(reading.fall?.quality!=='good' && reading.fall?.active!==true) reasons.push('跌倒监测暂不可用');
  const level=levels.includes('red')?'red':levels.includes('yellow')?'yellow':incomplete?'unknown':'green';
  return {level,reasons:reasons.length?reasons:['各项数据处于演示平稳范围'],incomplete};
}
export function displayMetric(reading,key,rules=DEFAULT_RULES,now=Date.now()) {
  const m=reading?.metrics?.[key];
  if(!reading) return {text:'—',note:'尚无数据',level:'unknown'};
  if(!isFresh(reading,rules,now)) return {text:'—',note:reading?.connected?'数据已过期':'设备离线',level:'unknown'};
  if(!usable(m)) return {text:'—',note:m?.quality==='poor'?'信号不稳 · 请重新采集':'暂不可用',level:'unknown'};
  return {text:key==='temp'?m.value.toFixed(1):String(Math.round(m.value)),note:'模拟读数',level:severity(key,m.value,rules)};
}
export function lcdFrames(reading,rules=DEFAULT_RULES,now=Date.now()) {
  const fit=s=>s.slice(0,16).padEnd(16,' ');
  const row=(a,b)=>[fit(a),fit(b)];
  if(reading?.fall?.active) return [row('! FALL DETECTED!','CHECK PERSON NOW')];
  if(!isFresh(reading,rules,now)) return [row(reading?.connected?'DATA STALE':'DEVICE OFFLINE','HR:--- T:---')];
  const t=triage(reading,rules,now);
  const v=k=>displayMetric(reading,k,rules,now).text.replace('—','---');
  const frames=[row(`HR:${v('hr')} BPM`,`TEMP:${v('temp')} C`),row(`FALL:${reading.fall?.quality==='good'?'NONE':'UNKNOWN'}`,t.incomplete?'SENSOR CHECK':'DEMO / SIMULATED')];
  if(t.level==='red') frames.unshift(row('! VALUE ALERT !','CHECK PERSON NOW'));
  else if(t.level==='yellow') frames.unshift(row('VALUE ATTENTION','PLEASE CHECK'));
  return frames;
}
