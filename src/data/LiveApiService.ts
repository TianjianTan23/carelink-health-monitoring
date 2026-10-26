import {z} from 'zod';
import {AlertSchema,PatientSchema,PredictionSchema,SensorReadingSchema,SessionSchema,type AppMode,type DemoRules} from './models';
import {DataError,type DataService} from './service';
import {validateConfig,type AppConfig} from './config';
import demoRules from '../../shared/demo-rules.json';

function timeoutSignal(milliseconds:number):AbortSignal|undefined{
  return typeof AbortSignal!=='undefined'&&typeof AbortSignal.timeout==='function'
    ? AbortSignal.timeout(milliseconds)
    : undefined;
}

function xhrTransport(input:RequestInfo|URL,options:RequestInit={}):Promise<Response>{
  return new Promise((resolve,reject)=>{
    if(typeof XMLHttpRequest==='undefined'){reject(new Error('No browser HTTP transport is available'));return;}
    const request=new XMLHttpRequest();
    request.open(options.method??'GET',String(input),true);
    request.withCredentials=options.credentials==='include';
    request.timeout=8000;
    const headers=options.headers;
    if(Array.isArray(headers))for(const [name,value] of headers)request.setRequestHeader(name,value);
    else if(typeof Headers!=='undefined'&&headers instanceof Headers)headers.forEach((value,name)=>request.setRequestHeader(name,value));
    else if(headers)for(const [name,value] of Object.entries(headers))if(value!==undefined)request.setRequestHeader(name,String(value));
    request.onload=()=>resolve({
      status:request.status,
      ok:request.status>=200&&request.status<300,
      json:async()=>JSON.parse(request.responseText),
    } as Response);
    request.onerror=()=>reject(new Error('XMLHttpRequest failed'));
    request.ontimeout=()=>reject(new Error('XMLHttpRequest timed out'));
    request.onabort=()=>reject(new Error('XMLHttpRequest was aborted'));
    request.send(typeof options.body==='string'?options.body:null);
  });
}

async function browserTransport(input:RequestInfo|URL,options?:RequestInit):Promise<Response>{
  if(typeof fetch==='function'){
    try{return await fetch(input,options);}catch(error){if(typeof XMLHttpRequest==='undefined')throw error;}
  }
  return xhrTransport(input,options);
}

export class LiveApiService implements DataService {
  readonly mode='live' as const;
  readonly rules:DemoRules;
  private session:z.infer<typeof SessionSchema>|null=null;
  private readonly config:AppConfig;
  private readonly transport:typeof fetch;
  constructor(config:AppConfig,transport?:typeof fetch){this.transport=transport??browserTransport;this.config=validateConfig(config);if(config.mode!=='live')throw new DataError('configuration','LiveApiService requires explicit live configuration');this.rules={...structuredClone(demoRules),staleAfterSeconds:config.staleAfterSeconds};}
  private path(key:keyof AppConfig['endpoints'],id?:string){return this.config.endpoints[key].replace('{id}',encodeURIComponent(id??''));}
  private async request<T>(path:string,schema:z.ZodType<T>,options:RequestInit={},empty?:T):Promise<T>{
    let response:Response;
    try{response=await this.transport(this.config.baseUrl.replace(/\/$/,'')+path,{...options,cache:'no-store',credentials:'include',headers:{Accept:'application/json',...(options.body?{'Content-Type':'application/json'}:{}),...options.headers},signal:timeoutSignal(8000)});}
    catch{throw new DataError('network','Network request failed or timed out');}
    if(response.status===204&&empty!==undefined)return empty;
    if(!response.ok)throw new DataError(response.status===403?'forbidden':'http',`API HTTP ${response.status}`,response.status);
    let data:unknown;try{data=await response.json();}catch{throw new DataError('invalid_data','API did not return JSON');}
    const result=schema.safeParse(data);if(!result.success)throw new DataError('invalid_data','Response does not match the proposed CareLink JSON contract');
    return result.data;
  }
  private allowed(id:string){if(!this.session?.patientIds.includes(id))throw new DataError('forbidden','Patient is outside authenticated session scope');}
  async authenticate(username:string,password:string){this.session=await this.request(this.path('login'),SessionSchema,{method:'POST',body:JSON.stringify({username,password})});return structuredClone(this.session);}
  async logout(){try{await this.transport(this.config.baseUrl.replace(/\/$/,'')+this.path('logout'),{method:'POST',cache:'no-store',credentials:'include',headers:{Accept:'application/json'},signal:timeoutSignal(8000)});}catch{/* Local sign-out still clears the UI session. */}this.session=null;}
  async getSession(_mode?:AppMode){this.session=await this.request(this.path('session'),SessionSchema);return structuredClone(this.session);}
  async getPatients(){if(!this.session)throw new DataError('forbidden','Load authenticated session first');const list=await this.request(this.path('patients'),z.array(PatientSchema),{},[]);if(!this.session)throw new DataError('forbidden','Load authenticated session first');if(list.some(p=>!this.session!.patientIds.includes(p.id)))throw new DataError('forbidden','API returned a patient outside authenticated session scope');return list;}
  async getPatient(id:string){this.allowed(id);try{const p=await this.request(this.path('patient',id),PatientSchema);if(p.id!==id)throw new DataError('invalid_data','Patient ID mismatch');return p;}catch(e){if(e instanceof DataError&&e.status===404)return null;throw e;}}
  async getReadings(id:string){this.allowed(id);const list=await this.request(this.path('readings',id),z.array(SensorReadingSchema),{},[]);if(list.some(r=>r.patientId!==id))throw new DataError('invalid_data','Reading patient ID mismatch');return list.sort((a,b)=>Date.parse(b.measuredAt)-Date.parse(a.measuredAt));}
  async getPredictions(id:string){this.allowed(id);const list=await this.request(this.path('predictions',id),z.array(PredictionSchema),{},[]);if(list.some(p=>p.patientId!==id))throw new DataError('invalid_data','Prediction patient ID mismatch');return list;}
  async getAlerts(){if(!this.session)throw new DataError('forbidden','Load authenticated session first');const list=await this.request(this.path('alerts'),z.array(AlertSchema),{},[]);if(list.some(a=>!this.session!.patientIds.includes(a.patientId)))throw new DataError('forbidden','API returned an alert outside authenticated session scope');return list;}
  async acknowledgeAlert(id:string){if(this.session?.mode!=='pro')throw new DataError('forbidden','Clinician session required');const a=await this.request(this.path('acknowledge',id),AlertSchema,{method:'POST',body:'{}'});this.allowed(a.patientId);if(a.id!==id||a.status==='new'||!a.acknowledgedAt)throw new DataError('invalid_data','Acknowledgement response does not confirm the requested alert');return a;}
  async refresh(){return this.getPatients();}
}
