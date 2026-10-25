import {triage,lcdFrames} from '../../dist/rules.js';
import {translate} from '../../dist/i18n.js';
import type {DemoRules,Language,Level,MetricKey,Patient,SensorReading,ServiceMode} from '../data/models';
export const metricKeys:MetricKey[]=['hr','temp'];
export const units={hr:'BPM',temp:'°C',ambient:'°C',motion:'g'};
export const metricsFor=(service:{metricKeys?:MetricKey[]})=>service.metricKeys??metricKeys;
export const metricAt=(r:SensorReading,k:MetricKey)=>r.metrics[k]??{value:null,quality:'unavailable' as const,available:false};
export function metricUsable(r:SensorReading,k:MetricKey){
  const m=metricAt(r,k);
  return m.available!==false&&m.quality==='good'&&m.value!==null&&Number.isFinite(m.value)&&
    (k!=='hr'||m.value>0)&&m.connected!==false&&(!m.state||m.state==='valid')&&
    (m.sensor!=='KY-039'||m.calculationValidated===true);
}
export function metricUpdatedAt(r:SensorReading|null|undefined,k:MetricKey){
  if(!r)return null;return metricAt(r,k).measuredAt??(k==='hr'&&(r.hardware||metricAt(r,k).sensor==='KY-039')?null:r.measuredAt);
}
export function sampleUsable(r:SensorReading,k:MetricKey,rules:DemoRules){
  if(!metricUsable(r,k))return false;
  const date=metricUpdatedAt(r,k);if(!date)return false;
  const age=Date.parse(r.measuredAt)-Date.parse(date);return age>=-5000&&age<=rules.staleAfterSeconds*1000;
}
export function heartRateInfo(r:SensorReading|null|undefined,rules:DemoRules,l:Language,now=Date.now()){
  const t=(zh:string,en:string)=>l==='zh'?zh:en,m=r?metricAt(r,'hr'):null;
  const connection=r?.source==='mock'?t('模拟连接状态','Mock connection state'):!r?t('连接状态未提供','Connection not reported'):!fresh(r,rules,now)?t('连接中断或上报已过期','Connection lost or report stale'):m?.connected===false?t('心率传感器未连接','Heart-rate sensor disconnected'):m?.connected===true?t('传感器连接已上报','Sensor connection reported'):t('心率连接状态未提供','Heart-rate connection not reported');
  let state=!r?t('等待传感器数据','Waiting for sensor data'):!r.connected?t('连接失败','Connection failed'):!fresh(r,rules,now)?t('数据已过期','Stale reading'):m?.connected===false?t('传感器未连接','Sensor disconnected'):m?.state==='stale'?t('心率数据已过期','Heart-rate data stale'):m?.state==='waiting'?t('等待传感器数据','Waiting for sensor data'):m?.state==='unvalidated'||m?.sensor==='KY-039'&&m.calculationValidated!==true?t('心率计算尚未验证','Heart-rate calculation not yet validated'):m?.quality==='poor'?t('信号质量不足','Poor signal quality'):!sampleUsable(r,'hr',rules)?t('等待有效心率信号','Waiting for a valid heart-rate signal'):t('有效心率采样','Valid heart-rate sample');
  const updatedAt=metricUpdatedAt(r,'hr');
  if(r&&m&&updatedAt&&metricUsable(r,'hr')&&now-Date.parse(updatedAt)>rules.staleAfterSeconds*1000)state=t('心率数据已过期','Heart-rate data stale');
  if(r?.source==='mock'&&r.connected&&fresh(r,rules,now)&&sampleUsable(r,'hr',rules))state=t('模拟心率 · 非 KY-039 实测','Mock heart rate · Not a KY-039 measurement');
  return {state,connection,updatedAt};
}

export const metricName=(k:MetricKey,l:Language)=>({hr:l==='zh'?'心率':'Heart rate',temp:l==='zh'?'表面温度':'Surface temperature',ambient:l==='zh'?'环境温度':'Ambient temperature',motion:l==='zh'?'总加速度':'Acceleration'})[k];
export const levelName=(v:Level,l:Language)=>({red:l==='zh'?'优先查看':'Review urgently',yellow:l==='zh'?'需要关注':'Needs attention',green:l==='zh'?'未见异常':'No reported alerts',unknown:l==='zh'?'数据待确认':'Data unverified'})[v];
const englishNames:Record<string,string>={p001:'Lin Zhiqiu',p002:'Zhou Yuanshan',p003:'Chen Jinghe',p004:'Xu Wangshu',p005:'Shen Huaichuan',p006:'Lu Qinghe',p007:'Gu Yunzhou',p008:'Su Wanqing'};
export const patientName=(p:Patient,l:Language,mode:ServiceMode='mock')=>l==='en'&&mode==='mock'?englishNames[p.id]??p.name:p.name;
export const localized=(text:string,l:Language)=>l==='zh'?text:translate(text,'en');
export function time(date:string|number|null|undefined,l:Language){if(!date)return '—';const d=new Date(date);return Number.isFinite(d.getTime())?new Intl.DateTimeFormat(l==='zh'?'zh-CN':'en-GB',{hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false}).format(d):'—';}
export function fresh(r:SensorReading|null|undefined,rules:DemoRules,now=Date.now()){if(!r?.connected)return false;const age=now-Date.parse(r.measuredAt);return age>=-5000&&age<=rules.staleAfterSeconds*1000;}
export function value(r:SensorReading|null|undefined,k:MetricKey,rules:DemoRules,l:Language,now=Date.now()){
  const t=(zh:string,en:string)=>l==='zh'?zh:en;
  if(!r)return {text:'—',note:t('尚无数据','No data yet'),valid:false};
  if(!fresh(r,rules,now))return {text:'—',note:r.connected?t('数据已过期','Stale reading'):t('设备离线','Device offline'),valid:false};
  const m=metricAt(r,k);
  const updated=metricUpdatedAt(r,k);
  if(updated&&(now-Date.parse(updated)>rules.staleAfterSeconds*1000||Date.parse(updated)>now+5000))return {text:'—',note:t('数据已过期','Stale reading'),valid:false};
  if(!sampleUsable(r,k,rules))return {text:'—',note:k==='hr'?heartRateInfo(r,rules,l,now).state:m.quality==='poor'?t('测量不可靠','Unreliable measurement'):t('暂不可用','Unavailable'),valid:false};
  if(m.available===false||m.quality!=='good'||m.value===null||!Number.isFinite(m.value))return {text:'—',note:m.quality==='poor'?t('测量不可靠','Unreliable measurement'):t('暂不可用','Unavailable'),valid:false};
  return {text:k==='temp'||k==='ambient'?m.value.toFixed(r.hardware?2:1):k==='motion'?m.value.toFixed(2):String(Math.round(m.value)),note:k==='motion'?t('MPU6050 · 原始运动读数','MPU6050 · Raw motion reading'):k==='ambient'?t('MLX90614 · 环境测温','MLX90614 · Ambient reading'):k==='temp'?t('表面测温 · 待校准','Surface reading · Calibration pending'):r.source==='mock'?t('模拟读数','Mock reading'):r.source==='device'?t('来源：设备记录','Source: device record'):t('来源：后端记录','Source: backend record'),valid:true};
}
export function status(r:SensorReading|null|undefined,mode:ServiceMode,rules:DemoRules,l:Language,now=Date.now()):{level:Level;reasons:string[];incomplete:boolean;origin:string}{
  const t=(zh:string,en:string)=>l==='zh'?zh:en;
  if(mode==='hardware'){
    return {level:'unknown',reasons:[!r?t('等待 ESP32 首次上报','Waiting for the first ESP32 sample'):!fresh(r,rules,now)?t('设备离线或数据已过期','Device offline or data stale'):r.hardware?.motionConnected?t('运动已连接 · 跌倒分类尚未验证','Motion connected · Fall classification not yet validated'):t('运动传感器不可用 · 请检查连接','Motion sensor unavailable · Check connection')],incomplete:true,origin:t('连接状态 · 非健康判断','Connection status · No health assessment')};
  }
  if(mode==='mock'){
    // Normalize explicit channel availability before reusing the existing demo rules.
    const copy=r?structuredClone(r):null;
    if(copy)for(const k of metricKeys)if(metricAt(copy,k).available===false)metricAt(copy,k).quality='unavailable';
    const s=triage(copy,rules,now);return {...s,level:s.level as Level,reasons:s.reasons.map((v:string)=>localized(v,l)),origin:t('可配置演示规则','Configurable demo rules')};
  }
  const incomplete=!fresh(r,rules,now)||metricKeys.some(k=>!value(r,k,rules,l,now).valid)||r?.fall.quality!=='good';
  const assessment=r?.assessment;
  if(assessment){const stale=now-Date.parse(assessment.assessedAt)>rules.staleAfterSeconds*1000||Date.parse(assessment.assessedAt)>now+5000;return {level:(stale||incomplete)&&assessment.level==='green'?'unknown':assessment.level,reasons:[...assessment.reasons,...(stale?[t('后端判断已过期','Backend assessment is stale')]:[])],incomplete:incomplete||stale,origin:t('后端判断','Backend assessment')};}
  if(r?.fall.active)return {level:'red',reasons:[t('设备上报跌倒事件，待人工核实','Device-reported fall event; needs human review')],incomplete,origin:t('设备事件 · 非数值阈值推断','Device event · No numeric threshold inference')};
  return {level:'unknown',reasons:[!r?t('尚无读数','No readings yet'):t('后端尚未提供状态判断','Backend assessment not provided')],incomplete:true,origin:t('等待后端判断','Awaiting backend assessment')};
}
export function displayFrames(r:SensorReading|null,mode:ServiceMode,rules:DemoRules,now=Date.now()):string[][]{
  const copy=r?structuredClone(r):null;if(copy)for(const k of metricKeys)if(metricAt(copy,k).available===false)metricAt(copy,k).quality='unavailable';
  if(mode==='hardware'){
    const v=(k:MetricKey)=>value(r,k,rules,'en',now).text.replace('—','---');
    return [[`HR:${v('hr')} BPM`.slice(0,16).padEnd(16),`SURF:${v('temp')}C`.slice(0,16).padEnd(16)],[`ACC:${v('motion')}g`.slice(0,16).padEnd(16),'FALL:UNVALIDATED ']];
  }
  if(mode==='mock')return lcdFrames(copy,rules,now);
  const row=(a:string,b:string)=>[a.slice(0,16).padEnd(16,' '),b.slice(0,16).padEnd(16,' ')];
  if(r?.fall.active)return [row('! FALL DETECTED!','CHECK PERSON NOW')];
  if(!fresh(r,rules,now))return [row(r?.connected?'DATA STALE':'DEVICE OFFLINE','HR:--- BPM')];
  const v=(k:MetricKey)=>value(r,k,rules,'en',now).text.replace('—','---');
  const frames=[row(`HR:${v('hr')} BPM`,`SURF T:${v('temp')}C`)];
  if(r?.assessment?.level==='red')frames.unshift(row('! BACKEND ALERT','CHECK PERSON NOW'));
  return frames;
}
