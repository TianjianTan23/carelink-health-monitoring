import {afterEach,describe,it,expect,vi} from 'vitest';
import {MockDataService} from './MockDataService';
import {LiveApiService} from './LiveApiService';
import {defaultConfig,validateConfig} from './config';
import {AlertSchema,PatientSchema,PredictionSchema,SensorReadingSchema,type Alert} from './models';
import {createDataService} from './index';
import profiles from '../../shared/demo-patients.json';
import sessions from '../../shared/demo-sessions.json';
import {makeReading} from '../../dist/service.js';
import apiProfiles from '../../shared/api-examples/patients.json';
import apiPredictions from '../../shared/api-examples/predictions.json';
import apiAlerts from '../../shared/api-examples/alerts.json';
import apiAcknowledgement from '../../shared/api-examples/acknowledgement.json';
const liveConfig={...defaultConfig,mode:'live' as const,apiConfirmed:true,baseUrl:'https://backend.example'};
const patient=()=>({...structuredClone(profiles[3]),reading:{...makeReading('p004','normal')!,source:'device'}});
const alert=():Alert=>({id:'alert-1',patientId:'p004',type:'fall',severity:'red',occurredAt:new Date().toISOString(),updatedAt:new Date().toISOString(),status:'new',conditionActive:true,acknowledgedAt:null,acknowledgedBy:null,resolvedAt:null,summary:'Device-reported fall',source:'backend'});
afterEach(()=>vi.unstubAllGlobals());
function fake(routes:Record<string,unknown>,options:{status?:Record<string,number>;reject?:string[]}={}){
 return vi.fn(async(input:RequestInfo|URL,init?:RequestInit)=>{
  const url=String(input).replace('https://backend.example','');const key=`${init?.method??'GET'} ${url}`;
  if(options.reject?.includes(url))throw new Error('offline');
  const code=options.status?.[url]??200;
  if(code===204)return new Response(null,{status:204});
  return new Response(JSON.stringify(routes[key]??routes[url]??null),{status:code,headers:{'Content-Type':'application/json'}});
 });
}
describe('configuration and unified models',()=>{
 it('decodes the same proposed API fixtures compiled by the Swift core tests',()=>{
  expect(PatientSchema.array().parse(apiProfiles)).toHaveLength(8);
  expect(PredictionSchema.array().parse(apiPredictions)[0].confidence).toBeNull();
  expect(AlertSchema.array().parse(apiAlerts)[0].source).toBe('mock');
  expect(AlertSchema.parse(apiAcknowledgement).conditionActive).toBe(true);
 });
 it('uses explicit mock/live configuration; unconfirmed API cannot start',()=>{
  expect(createDataService(defaultConfig)).toBeInstanceOf(MockDataService);
  expect(()=>createDataService({...liveConfig,apiConfirmed:false})).toThrow(/not confirmed/);
  expect(()=>new LiveApiService(defaultConfig)).toThrow(/explicit live/);
  expect(()=>validateConfig({...liveConfig,baseUrl:'javascript:bad'})).toThrow();
 });
 it('mock and live snapshots satisfy identical Patient/SensorReading shapes; null never becomes zero',async()=>{
  const mock=new MockDataService();await mock.getSession('pro');const patients=await mock.refresh();expect(patients).toHaveLength(8);
  expect(patients.every(p=>PatientSchema.safeParse(p).success)).toBe(true);
  const apiPatient=patient();expect(PatientSchema.safeParse(apiPatient).success).toBe(true);
  mock.setScenario('p004','unavailable');const p=await mock.getPatient('p004');expect(p?.reading?.metrics.hr.value).toBeNull();expect(p?.reading?.metrics.hr.quality).toBe('unavailable');
  expect(SensorReadingSchema.safeParse({...apiPatient.reading,metrics:{...apiPatient.reading.metrics,hr:{value:'76',quality:'good'}}}).success).toBe(false);
 });
 it('mock enforces Basic scope and acknowledgement role; failures do not invent data',async()=>{
  const mock=new MockDataService();await mock.getSession('basic');expect((await mock.getPatients()).map(p=>p.id)).toEqual(['p004']);
  await expect(mock.getPatient('p001')).rejects.toMatchObject({code:'forbidden'});
  mock.setScenario('p004','fall');const [record]=await mock.getAlerts();await expect(mock.acknowledgeAlert(record.id)).rejects.toMatchObject({code:'forbidden'});
  await mock.getSession('pro');const acknowledged=await mock.acknowledgeAlert(record.id);expect(acknowledged.status).toBe('acknowledged');expect((await mock.getPatient('p004'))?.reading?.fall.active).toBe(true);
  expect((await mock.getAlerts()).filter(a=>a.id===record.id)).toHaveLength(1);
  mock.setNetworkFailure(true);await expect(mock.getPatients()).rejects.toMatchObject({code:'network'});await expect(mock.getReadings('p004')).rejects.toMatchObject({code:'network'});
 });
});
describe('LiveApiService proposed API requests',()=>{
 it('falls back to XMLHttpRequest when embedded-browser fetch is blocked',async()=>{
  class WorkingXHR {
   method='';url='';withCredentials=false;timeout=0;status=200;responseText=JSON.stringify(sessions.pro);
   onload:(()=>void)|null=null;onerror:(()=>void)|null=null;ontimeout:(()=>void)|null=null;onabort:(()=>void)|null=null;
   open(method:string,url:string){this.method=method;this.url=url;}
   setRequestHeader(){}
   send(){queueMicrotask(()=>this.onload?.());}
  }
  vi.stubGlobal('fetch',vi.fn().mockRejectedValue(new Error('embedded fetch blocked')));
  vi.stubGlobal('XMLHttpRequest',WorkingXHR);
  const api=new LiveApiService(liveConfig);
  await expect(api.getSession()).resolves.toMatchObject({userId:'wyn',role:'clinician'});
 });
 it('reads session, list, detail, ten-minute readings, predictions and alerts; preserves actual confidence',async()=>{
  const p=patient(),a=alert();const prediction={id:'pred-1',patientId:'p004',state:'available',predictedAt:new Date().toISOString(),inputsMeasuredAt:p.reading.measuredAt,model:'team-model',modelVersion:'0.1',result:{label:'team-defined'},confidence:0,confidenceMeaning:'Uncalibrated score; meaning to confirm',source:'backend',modelName:null};
  // model is part of the agreed draft shape; no guessed confidence scale or result.
  const transport=fake({'/api/session':sessions.pro,'/api/patients':[p],'/api/patients/p004':p,'/api/patients/p004/readings?minutes=1440':[p.reading],'/api/patients/p004/predictions':[prediction],'/api/alerts':[a]});
  const api=new LiveApiService(liveConfig,transport);await api.getSession('basic');expect((await api.getPatients())[0].reading?.source).toBe('device');expect((await api.getPatient('p004'))?.id).toBe('p004');expect(await api.getReadings('p004')).toHaveLength(1);expect((await api.getPredictions('p004'))[0].confidence).toBe(0);expect(AlertSchema.safeParse((await api.getAlerts())[0]).success).toBe(true);
  expect(transport.mock.calls.every(([,init])=>init?.credentials==='include')).toBe(true);
  expect(transport.mock.calls.every(([,init])=>init?.cache==='no-store')).toBe(true);
 });
 it('uses returned backend role, not requested demo mode',async()=>{
  const api=new LiveApiService(liveConfig,fake({'/api/session':sessions.basic,'/api/patients':[patient()]}));expect((await api.getSession('pro')).mode).toBe('basic');await expect(api.getPatient('p001')).rejects.toMatchObject({code:'forbidden'});await expect(api.acknowledgeAlert('any')).rejects.toMatchObject({code:'forbidden'});
 });
 it('handles []/204 lists and 404 detail as empty; other errors remain errors',async()=>{
  const api=new LiveApiService(liveConfig,fake({'/api/session':sessions.pro,'/api/patients':[],'/api/patients/p004':null},{status:{'/api/alerts':204,'/api/patients/p004':404,'/api/patients/p004/predictions':204,'/api/patients/p004/readings?minutes=1440':204}}));await api.getSession();expect(await api.getPatients()).toEqual([]);expect(await api.getAlerts()).toEqual([]);expect(await api.getReadings('p004')).toEqual([]);expect(await api.getPredictions('p004')).toEqual([]);expect(await api.getPatient('p004')).toBeNull();
 });
 it.each([401,403,500])('propagates HTTP %i without mock fallback',async code=>{
  const api=new LiveApiService(liveConfig,fake({'/api/session':sessions.pro},{status:{'/api/patients':code}}));await api.getSession();await expect(api.getPatients()).rejects.toMatchObject({status:code});
 });
 it('propagates network failure and rejects malformed/cross-patient data',async()=>{
  const network=new LiveApiService(liveConfig,fake({'/api/session':sessions.pro},{reject:['/api/patients']}));await network.getSession();await expect(network.getPatients()).rejects.toMatchObject({code:'network'});
  const invalid=new LiveApiService(liveConfig,fake({'/api/session':sessions.pro,'/api/patients':{items:[patient()]},'/api/patients/p004/readings?minutes=1440':[makeReading('p001')]}));await invalid.getSession();await expect(invalid.getPatients()).rejects.toMatchObject({code:'invalid_data'});await expect(invalid.getReadings('p004')).rejects.toMatchObject({code:'invalid_data'});
 });
 it('accepts acknowledgement only after POST response confirms requested alert',async()=>{
  const a=alert();const confirmed={...a,status:'acknowledged',acknowledgedAt:new Date().toISOString(),acknowledgedBy:'clinician-1'};
  const transport=fake({'/api/session':sessions.pro,'POST /api/alerts/alert-1/acknowledgement':confirmed});const api=new LiveApiService(liveConfig,transport);await api.getSession();expect((await api.acknowledgeAlert('alert-1')).acknowledgedAt).toBe(confirmed.acknowledgedAt);expect(transport.mock.calls.at(-1)?.[1]).toMatchObject({method:'POST',body:'{}'});
  const broken=new LiveApiService(liveConfig,fake({'/api/session':sessions.pro,'POST /api/alerts/alert-1/acknowledgement':a}));await broken.getSession();await expect(broken.acknowledgeAlert('alert-1')).rejects.toMatchObject({code:'invalid_data'});
 });
 it('keeps absent prediction fields null/undefined and never fabricates a result',()=>{
  const p=PredictionSchema.parse({state:'not_connected',model:null,result:null,confidence:null});expect(p.confidence).toBeNull();expect(p.predictedAt).toBeUndefined();expect(p.result).toBeNull();
 });
 it('keeps the API returned history without filling gaps',async()=>{
  const now=Date.now();const history=[makeReading('p004','normal',now-700000),makeReading('p004','normal',now-30000),makeReading('p004','normal',now+60000)];
  const api=new LiveApiService(liveConfig,fake({'/api/session':sessions.pro,'/api/patients/p004/readings?minutes=1440':history}));await api.getSession();const rows=await api.getReadings('p004');expect(rows).toHaveLength(3);expect(rows[0].measuredAt).toBe(history[2]!.measuredAt);
 });
});

describe('backend security compatibility',()=>{
 it('sends the CSRF header and JSON on login, acknowledgement and logout',async()=>{
  const transport=fake({'POST /api/login':sessions.pro,'POST /api/logout':{status:'signed_out'},'POST /api/alerts/alert-1/acknowledgement':{...alert(),status:'acknowledged',acknowledgedAt:new Date().toISOString()}});
  const api=new LiveApiService(liveConfig,transport);
  await api.authenticate('fixture','synthetic-test-password');
  await api.acknowledgeAlert('alert-1');await api.logout();
  for(const [,init] of transport.mock.calls){
   expect(new Headers(init?.headers).get('X-CareLink-CSRF')).toBe('1');
   expect(new Headers(init?.headers).get('Content-Type')).toBe('application/json');
  }
 });
 it('does not report successful server logout on HTTP denial or network failure',async()=>{
  for(const transport of [fake({}, {status:{'/api/logout':503}}),fake({}, {reject:['/api/logout']})]){
   await expect(new LiveApiService(liveConfig,transport).logout()).rejects.toBeInstanceOf(Error);
  }
 });
 it('forgets locally cached authorization immediately on HTTP 401',async()=>{
  const transport=fake({'/api/session':sessions.pro},{status:{'/api/patients':401}});
  const api=new LiveApiService(liveConfig,transport);await api.getSession();
  await expect(api.getPatients()).rejects.toMatchObject({status:401});
  const calls=transport.mock.calls.length;
  await expect(api.getPatient('p004')).rejects.toMatchObject({code:'forbidden'});
  expect(transport.mock.calls).toHaveLength(calls);
 });
 it('refuses plaintext API origins and insecure same-origin live pages',()=>{
  expect(()=>validateConfig({...liveConfig,baseUrl:'http://gateway.example'})).toThrow();
  expect(()=>validateConfig({...liveConfig,baseUrl:''})).toThrow();
 });
});

it('rotation uses actual backend endpoint, CSRF and revalidates the server session',async()=>{
 const transport=fake({'POST /api/session/rotate':{status:'rotated'},'/api/session':sessions.pro});
 const api=new LiveApiService(liveConfig,transport);await api.getSession();await api.rotateSession();
 expect(transport).toHaveBeenCalledWith(expect.stringContaining('/api/session/rotate'),expect.objectContaining({method:'POST',headers:expect.objectContaining({'X-CareLink-CSRF':'1'})}));
 expect(transport.mock.calls.at(-1)?.[0]).toBe('https://backend.example/api/session');
});
