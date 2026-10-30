import {z} from 'zod';
import {DataError} from './service';
export const defaultEndpoints={login:'/api/login',logout:'/api/logout',session:'/api/session',patients:'/api/patients',patient:'/api/patients/{id}',readings:'/api/patients/{id}/readings?minutes=1440',predictions:'/api/patients/{id}/predictions',alerts:'/api/alerts',acknowledge:'/api/alerts/{id}/acknowledgement'};
const endpoint=z.string().startsWith('/').refine(s=>!s.startsWith('//')&&!s.includes('://'),'Use an API path, not an external URL');
export const ConfigSchema=z.object({mode:z.enum(['mock','live']),baseUrl:z.string().default(''),apiConfirmed:z.boolean().default(false),staleAfterSeconds:z.number().positive().default(30),endpoints:z.object({login:endpoint,logout:endpoint,session:endpoint,patients:endpoint,patient:endpoint,readings:endpoint,predictions:endpoint,alerts:endpoint,acknowledge:endpoint}).default(defaultEndpoints)});
export type AppConfig=z.infer<typeof ConfigSchema>;
export const defaultConfig:AppConfig={mode:'mock',baseUrl:'',apiConfirmed:false,staleAfterSeconds:30,endpoints:defaultEndpoints};
export function validateConfig(input:unknown):AppConfig {
  const result=ConfigSchema.safeParse(input);
  if(!result.success)throw new DataError('configuration','Invalid carelink-config.json');
  const config=result.data;
  if(config.mode==='live'&&!config.apiConfirmed)throw new DataError('configuration','Proposed API is not confirmed. Confirm the contract and set apiConfirmed first.');
  if(config.baseUrl){try{const url=new URL(config.baseUrl);if(url.protocol!=='https:'||url.username||url.password||url.search||url.hash)throw new Error();}catch{throw new DataError('configuration','API baseUrl must be an HTTPS origin/path without credentials, query or fragment.');}}
  if(config.mode==='live'&&!config.baseUrl&&(typeof location==='undefined'||location.protocol!=='https:'))throw new DataError('configuration','Live same-origin API requires an HTTPS page.');
  return config;
}
export async function loadConfig():Promise<AppConfig>{
  let response:Response;
  try{response=await fetch('/carelink-config.json',{cache:'no-store'});}catch{throw new DataError('configuration','Unable to load carelink-config.json');}
  if(!response.ok)throw new DataError('configuration',`Configuration HTTP ${response.status}`);
  let config:unknown;try{config=await response.json();}catch{throw new DataError('configuration','Configuration is not JSON');}
  const parsed=ConfigSchema.safeParse(config);if(!parsed.success)throw new DataError('configuration','Invalid configuration');
  return validateConfig({...parsed.data,mode:import.meta.env.VITE_DATA_MODE||parsed.data.mode,baseUrl:import.meta.env.VITE_API_BASE_URL??parsed.data.baseUrl,apiConfirmed:import.meta.env.VITE_API_CONFIRMED?import.meta.env.VITE_API_CONFIRMED==='true':parsed.data.apiConfirmed});
}
