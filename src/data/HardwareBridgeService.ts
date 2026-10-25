import {z} from 'zod';
import {DataError} from './service';

const baseUrl=z.string().refine(value=>{
  if(value.startsWith('/'))return !value.startsWith('//')&&!/[?#\\]/.test(value)&&!value.includes('://');
  try{const url=new URL(value);return ['http:','https:'].includes(url.protocol)&&!url.username&&!url.password&&!url.search&&!url.hash;}catch{return false;}
},'Use a same-origin path or an http(s) URL without credentials, query or fragment');
export const HardwareConfigSchema=z.object({
  mode:z.literal('hardware'),baseUrl,
  pollIntervalMs:z.number().int().min(500).max(60000),
  staleAfterMs:z.number().int().min(1000).max(300000),
  requestTimeoutMs:z.number().int().min(500).max(30000),
  deviceId:z.string().min(1).optional(),
  // Enable only after the hardware team has confirmed the KY-039 algorithm and payload contract.
  heartRateContractConfirmed:z.boolean().default(false),
});
export type HardwareConfig=z.infer<typeof HardwareConfigSchema>;
const number=z.number().finite().nullable().optional();
export const HardwarePayloadSchema=z.object({
  device_id:z.string().min(1),uptime_ms:z.number().int().nonnegative(),
  accel_x_g:number,accel_y_g:number,accel_z_g:number,accel_total_g:number,accel_peak_g:number,
  ambient_temp_c:number,object_temp_c:number,
  mpu6050_ok:z.boolean(),mlx90614_ok:z.boolean(),alarm:z.boolean().optional(),
  heart_rate_bpm:number,heart_rate_ok:z.boolean().optional(),heart_signal_raw:number,
  heart_rate_sensor:z.string().optional(),heart_rate_connected:z.boolean().optional(),
  heart_rate_algorithm_validated:z.boolean().optional(),heart_rate_quality:z.enum(['good','poor','unavailable','unknown']).optional(),
  heart_rate_measured_at:z.string().nullable().optional(),
}).passthrough();
export const HardwareSnapshotSchema=z.object({
  ok:z.literal(true),received_at:z.string().datetime({offset:true}),data:HardwarePayloadSchema,
});
export type HardwareSnapshot=z.infer<typeof HardwareSnapshotSchema>;
export class HardwareBridgeError extends Error {
  constructor(public readonly code:'waiting'|'network'|'http'|'invalid_data',message:string,public readonly status?:number){super(message);this.name='HardwareBridgeError';}
}
export function validateHardwareConfig(input:unknown):HardwareConfig {
  const result=HardwareConfigSchema.safeParse(input);
  if(!result.success)throw new DataError('configuration','Invalid hardware-bridge-config.json');
  return result.data;
}
export async function loadHardwareConfig():Promise<HardwareConfig>{
  const response=await fetch('/hardware-bridge-config.json',{cache:'no-store',credentials:'omit'});
  if(!response.ok)throw new DataError('configuration',`Hardware configuration HTTP ${response.status}`);
  const input=await response.json();
  return validateHardwareConfig({...input,baseUrl:import.meta.env.VITE_HARDWARE_BASE_URL??input.baseUrl});
}

// Deliberately independent of DataService: the bridge has no patients, sessions,
// clinical assessments, alert acknowledgement, history or prediction endpoints.
export class HardwareBridgeService {
  readonly mode='hardware' as const;
  readonly config:HardwareConfig;
  constructor(config:HardwareConfig,private readonly transport:typeof fetch=(...args)=>fetch(...args)){this.config=validateHardwareConfig(config);}
  async latest(signal?:AbortSignal):Promise<HardwareSnapshot>{
    const controller=new AbortController();
    const abort=()=>controller.abort();
    if(signal?.aborted)abort();else signal?.addEventListener('abort',abort,{once:true});
    const timer=setTimeout(abort,this.config.requestTimeoutMs);
    try{return await this.request(controller.signal);}finally{clearTimeout(timer);signal?.removeEventListener('abort',abort);}
  }
  private async request(signal:AbortSignal):Promise<HardwareSnapshot>{
    let response:Response;
    try{
      response=await this.transport(this.config.baseUrl.replace(/\/$/,'')+'/sensor-data/latest',{
        credentials:'omit',cache:'no-store',headers:{Accept:'application/json'},
        signal,
      });
    }catch(error){throw new HardwareBridgeError('network',`Bridge unreachable or request timed out${error instanceof Error?`: ${error.message}`:''}`);}
    if(response.status===503){
      // Only the bridge's documented empty-state response means "waiting".
      let body:unknown;try{body=await response.json();}catch{/* Other 503s are errors. */}
      if(typeof body==='object'&&body!==null&&'detail' in body&&body.detail==='No sensor data received yet')
        throw new HardwareBridgeError('waiting','Bridge is running; waiting for ESP32 data',503);
    }
    if(!response.ok)throw new HardwareBridgeError('http',`Bridge HTTP ${response.status}`,response.status);
    let body:unknown;
    try{body=await response.json();}catch{throw new HardwareBridgeError('invalid_data','Bridge response is not JSON');}
    const parsed=HardwareSnapshotSchema.safeParse(body);
    if(!parsed.success)throw new HardwareBridgeError('invalid_data','Invalid bridge payload; check sensor fields, validity flags and received_at');
    if(this.config.deviceId&&parsed.data.data.device_id!==this.config.deviceId)
      throw new HardwareBridgeError('invalid_data',`Unexpected device: ${parsed.data.data.device_id}`);
    return parsed.data;
  }
}
export function hardwareFresh(snapshot:HardwareSnapshot|null,staleAfterMs:number,now=Date.now()){
  if(!snapshot)return false;
  const age=now-Date.parse(snapshot.received_at);
  return age>=-5000&&age<=staleAfterMs;
}
