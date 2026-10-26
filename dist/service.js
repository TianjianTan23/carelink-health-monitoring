import {DEMO_PATIENTS,DEMO_SESSIONS} from './fixtures.js';
import {DEFAULT_RULES} from './rules.js';
// Replace createService() with ApiService after agreeing the contract in INTEGRATION.md.
// Every identity below is fictional. No real patient or family information.
export const SCENARIOS={normal:'数据平稳',mild:'轻度异常',severe:'严重异常',fall:'跌倒警报',poor:'MAX 信号不稳',unavailable:'KY-005 备用模式',offline:'设备离线',stale:'数据过期',noData:'尚无数据'};
const good=value=>({value,quality:'good'});
export function makeReading(patientId,scenario='normal',now=Date.now(),offset=0) {
  const index=Number(patientId.slice(1)) || 1;
  const r={patientId,deviceId:`esp32-${String(index).padStart(2,'0')}`,measuredAt:new Date(now).toISOString(),receivedAt:new Date(now+100).toISOString(),connected:true,
    metrics:{hr:good(72+index+offset),spo2:good(98),temp:good(Number((36.4+index*.04).toFixed(1)))},
    fall:{active:false,quality:'good',eventAt:null},
    raw:{accel_m_s2:{x:.12,y:.08,z:9.79},gyro_deg_s:{x:.1,y:.2,z:.1},ir:82000,red:69000,object_temperature_c:36.6,ambient_temperature_c:24.1},
    ai:{state:'not_connected',model:null,result:null,confidence:null},source:'mock',scenario};
  if(scenario==='mild') r.metrics.hr=good(108+offset);
  if(scenario==='warm') r.metrics.temp=good(38.1);
  if(scenario==='severe') {r.metrics.hr=good(142+offset);r.metrics.spo2=good(87);}
  if(scenario==='fall') { r.fall={active:true,quality:'good',eventAt:new Date(now-45000).toISOString()};r.raw.accel_m_s2={x:3.4,y:9.6,z:1.2}; }
  if(scenario==='poor') {r.metrics.hr={value:148,quality:'poor'};r.metrics.spo2={value:82,quality:'poor'};}
  if(scenario==='unavailable') {r.metrics.hr={value:null,quality:'unavailable'};r.metrics.spo2={value:null,quality:'unavailable'};r.raw.ir=null;r.raw.red=null;}
  if(scenario==='offline') r.connected=false;
  if(scenario==='stale') r.measuredAt=new Date(now-180000).toISOString();
  if(scenario==='noData') return null;
  r.raw.object_temperature_c=r.metrics.temp.value;
  return r;
}
export class MockService {
  constructor(){this.overrides={};this.anchor=Date.now();this.rules=structuredClone(DEFAULT_RULES);}
  async getPatients(){return DEMO_PATIENTS.map(p=>({...structuredClone(p),reading:makeReading(p.id,this.overrides[p.id]||p.scenario,this.anchor)}));}
  async getSession(mode='pro'){return structuredClone(DEMO_SESSIONS[mode]);}
  async getPatient(id){return (await this.getPatients()).find(p=>p.id===id)||null;}
  async getHistory(id){const p=await this.getPatient(id);if(!p)return [];const scenario=this.overrides[id]||p.scenario;
    if(scenario==='noData')return [];
    // 21 samples, 30 seconds apart, strictly within [anchor - 10 min, anchor].
    return Array.from({length:21},(_,i)=>makeReading(id,i<3?scenario:(['offline','stale'].includes(scenario)?scenario:'normal'),this.anchor-i*30000,i===0?0:i%3-1)).filter(r=>Date.parse(r.measuredAt)>=this.anchor-600000);}
  async refresh(){this.anchor=Date.now();return this.getPatients();}
  setScenario(id,scenario){if(!Object.hasOwn(SCENARIOS,scenario))throw new Error('Unknown scenario');this.overrides[id]=scenario;this.anchor=Date.now();}
  reset(){this.overrides={};this.rules=structuredClone(DEFAULT_RULES);this.anchor=Date.now();}
}
// Proposed normalized API; never silently substitutes mock data on API failure.
export class ApiService {
  constructor(baseUrl=''){this.baseUrl=baseUrl;this.rules=structuredClone(DEFAULT_RULES);}
  async request(path){const res=await fetch(this.baseUrl+path,{signal:AbortSignal.timeout(8000),credentials:'same-origin'});if(!res.ok)throw new Error(`API ${res.status}`);return res.json();}
  async getPatients(){return this.request('/api/patients');}
  async getSession(){return this.request('/api/session');}
  async getPatient(id){return this.request(`/api/patients/${encodeURIComponent(id)}`);}
  async getHistory(id){return this.request(`/api/patients/${encodeURIComponent(id)}/readings?minutes=10`);}
  async refresh(){return this.getPatients();}
}
export function createService(){return new MockService();}
