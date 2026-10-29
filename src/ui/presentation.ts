import {triage,lcdFrames} from '../../dist/rules.js';
import {translate} from '../../dist/i18n.js';
import type {DemoRules,Language,Level,MetricKey,Patient,SensorReading,ServiceMode} from '../data/models';
export const metricKeys:MetricKey[]=['hr','temp'];
export const units={hr:'bpm',temp:'°C'};
export const metricName=(k:MetricKey,l:Language)=>({hr:l==='zh'?'心率':'Heart rate',temp:l==='zh'?'体温':'Temperature'})[k];
export const levelName=(v:Level,l:Language)=>({red:l==='zh'?'CRITICAL · 严重':'CRITICAL',yellow:l==='zh'?'WARNING · 警告':'WARNING',green:l==='zh'?'NORMAL · 正常':'NORMAL',unknown:l==='zh'?'数据待确认':'Data unverified'})[v];
const englishNames:Record<string,string>={p001:'Lin Zhiqiu',p002:'Zhou Yuanshan',p003:'Chen Jinghe',p004:'Xu Wangshu',p005:'Shen Huaichuan',p006:'Lu Qinghe',p007:'Gu Yunzhou',p008:'Su Wanqing'};
export const patientName=(p:Patient,l:Language,mode:ServiceMode='mock')=>l==='en'&&mode==='mock'?englishNames[p.id]??p.name:p.name;
export const localized=(text:string,l:Language)=>l==='zh'?text:translate(text,'en');
export function time(date:string|number|null|undefined,l:Language){if(!date)return '—';const d=new Date(date);return Number.isFinite(d.getTime())?new Intl.DateTimeFormat(l==='zh'?'zh-CN':'en-GB',{hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false}).format(d):'—';}
export function fresh(r:SensorReading|null|undefined,rules:DemoRules,now=Date.now()){if(!r?.connected)return false;const age=now-Date.parse(r.measuredAt);return age>=-5000&&age<=rules.staleAfterSeconds*1000;}
export function value(r:SensorReading|null|undefined,k:MetricKey,rules:DemoRules,l:Language,now=Date.now()){
  const t=(zh:string,en:string)=>l==='zh'?zh:en;
  if(!r)return {text:'—',note:t('正在等待首次有效采样','Waiting for the first valid sample'),valid:false};
  const m=r.metrics[k],isFresh=fresh(r,rules,now);
  const valid=isFresh&&m.available!==false&&m.quality==='good'&&m.value!==null&&Number.isFinite(m.value);
  if(valid)return {text:k==='temp'?m.value!.toFixed(1):String(Math.round(m.value!)),note:r.source==='backend'?t('合成测试读数','Synthetic test reading'):k==='temp'?t('表面测温 · 待校准','Surface reading · Calibration pending'):t('持续采集中 · 每次有效脉搏更新','Sampling continuously · Updated on accepted beats'),valid:true};
  const lastAt=m.lastValidAt??r.measuredAt,age=Math.max(0,(now-Date.parse(lastAt))/1000);
  const held=m.displayValue??(!isFresh&&m.quality==='good'&&m.available!==false?m.value:null);
  if(k==='hr'&&held!==null&&held!==undefined&&Number.isFinite(held)&&age<=30){
    return {text:String(Math.round(held)),note:t(`上次有效值 · ${Math.floor(age)}秒前 · 不参与当前分类`,`Last valid value · ${Math.floor(age)}s ago · Not a current measurement`),valid:false};
  }
  return {text:'—',note:!isFresh?t('连接中断或数据过期','Connection lost or data stale'):t('持续采集中 · 等待可靠脉搏','Sampling continuously · Waiting for a reliable pulse'),valid:false};
}
export function status(r:SensorReading|null|undefined,mode:ServiceMode,rules:DemoRules,l:Language,now=Date.now()):{level:Level;reasons:string[];incomplete:boolean;origin:string}{
  const t=(zh:string,en:string)=>l==='zh'?zh:en;
  if(mode==='mock'){
    // Normalize explicit channel availability before reusing the existing demo rules.
    const copy=r?structuredClone(r):null;
    if(copy)for(const k of metricKeys)if(copy.metrics[k].available===false)copy.metrics[k].quality='unavailable';
    const s=triage(copy,rules,now);return {...s,level:s.level as Level,reasons:s.reasons.map((v:string)=>localized(v,l)),origin:t('可配置演示规则','Configurable demo rules')};
  }
  const incomplete=!fresh(r,rules,now)||metricKeys.some(k=>!value(r,k,rules,l,now).valid)||r?.fall.quality!=='good';
  const assessment=r?.assessment;
  if(assessment){const stale=now-Date.parse(assessment.assessedAt)>rules.staleAfterSeconds*1000||Date.parse(assessment.assessedAt)>now+5000;return {level:(stale||incomplete)&&assessment.level==='green'?'unknown':assessment.level,reasons:[...assessment.reasons,...(stale?[t('后端判断已过期','Backend assessment is stale')]:[])],incomplete:incomplete||stale,origin:t('后端判断','Backend assessment')};}
  if(r?.fall.active)return {level:'red',reasons:[t('设备上报跌倒事件，待人工核实','Device-reported fall event; needs human review')],incomplete,origin:t('设备事件 · 非数值阈值推断','Device event · No numeric threshold inference')};
  return {level:'unknown',reasons:[!r?t('尚无读数','No readings yet'):t('后端尚未提供状态判断','Backend assessment not provided')],incomplete:true,origin:t('等待后端判断','Awaiting backend assessment')};
}
export function displayFrames(r:SensorReading|null,mode:ServiceMode,rules:DemoRules,now=Date.now()):string[][]{
  const copy=r?structuredClone(r):null;if(copy)for(const k of metricKeys)if(copy.metrics[k].available===false)copy.metrics[k].quality='unavailable';
  if(mode==='mock')return lcdFrames(copy,rules,now);
  const row=(a:string,b:string)=>[a.slice(0,16).padEnd(16,' '),b.slice(0,16).padEnd(16,' ')];
  if(r?.fall.active)return [row('! FALL DETECTED!','CHECK PERSON NOW')];
  if(!fresh(r,rules,now))return [row(r?.connected?'DATA STALE':'DEVICE OFFLINE','HR:--- T:---')];
  const v=(k:MetricKey)=>value(r,k,rules,'en',now).text.replace('—','---');
  const frames=[row(`HR:${v('hr')} BPM`,`TEMP:${v('temp')} C`)];
  if(r?.assessment?.level==='red')frames.unshift(row('! BACKEND ALERT','CHECK PERSON NOW'));
  return frames;
}
