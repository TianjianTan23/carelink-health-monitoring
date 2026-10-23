import rules from '../../shared/demo-rules.json';
import type {Alert,AppMode,Metric,Patient,Prediction,SensorReading,Session} from './models';
import {DataError,type DataService} from './service';
import {HardwareBridgeError,HardwareBridgeService,type HardwareSnapshot} from './HardwareBridgeService';

const unavailable=():Metric=>({value:null,quality:'unavailable',available:false});
// A local device workspace, never a fabricated clinical identity or authenticated session.
export class HardwareDataService implements DataService {
  readonly mode='hardware' as const;
  readonly metricKeys=['temp','ambient','motion'] as ('temp'|'ambient'|'motion')[];
  readonly rules;
  readonly pollIntervalMs;
  private reading:SensorReading|null=null;
  private history:SensorReading[]=[];
  private events:Alert[]=[];
  private activeEvent:string|null=null;
  private session:Session|null=null;
  private id:string;
  constructor(readonly bridge:HardwareBridgeService,private clock=()=>Date.now()){
    this.id=bridge.config.deviceId??'local-device';
    this.rules={...rules,staleAfterSeconds:bridge.config.staleAfterMs/1000};
    this.pollIntervalMs=bridge.config.pollIntervalMs;
  }
  async getSession(mode:AppMode='pro'):Promise<Session>{
    this.session={userId:'local-workspace',role:mode==='pro'?'clinician':'family',mode,patientIds:[this.id]};
    return this.session;
  }
  private allowed(id=this.id){if(!this.session?.patientIds.includes(id))throw new DataError('forbidden','Outside local device scope');}
  private profile():Patient{return {id:this.id,name:this.reading?.deviceId??this.id,age:0,sex:'',bed:'',history:'',admittedAt:'',allergies:'',color:'mint',profileKind:'device',reading:this.reading};}
  async getPatients(){this.allowed();return [this.profile()];}
  async getPatient(id:string){this.allowed(id);return this.profile();}
  async getReadings(id:string){this.allowed(id);return this.history.filter(r=>Date.parse(r.receivedAt)>=this.clock()-600000).slice().reverse();}
  async getPredictions(id:string):Promise<Prediction[]>{this.allowed(id);return [{state:'not_connected',model:null,confidence:null,source:'device',patientId:this.id}];}
  async getAlerts(){this.allowed();return structuredClone(this.events).reverse();}
  async acknowledgeAlert(id:string){
    this.allowed();if(this.session?.mode!=='pro')throw new DataError('forbidden','Pro workspace required');
    const event=this.events.find(a=>a.id===id);
    if(!event||event.status!=='new')throw new DataError('not_found','No new local event');
    event.acknowledgedAt=new Date(this.clock()).toISOString();event.acknowledgedBy='local-workspace';event.status='acknowledged';
    return {...event};
  }
  private pending:Promise<Patient[]>|null=null;
  refresh():Promise<Patient[]>{
    if(this.pending)return this.pending;
    this.pending=this.receive().finally(()=>{this.pending=null;});return this.pending;
  }
  private async receive(){
    this.allowed();
    let snapshot:HardwareSnapshot;
    try{snapshot=await this.bridge.latest();}catch(error){
      if(error instanceof HardwareBridgeError&&error.code==='waiting'){this.reading=null;this.history=[];this.activeEvent=null;this.events=[];return this.getPatients();}
      if(this.reading)this.reading={...this.reading,connected:false};
      throw error;
    }
    const d=snapshot.data;
    if(this.reading?.receivedAt===snapshot.received_at){this.reading={...this.reading,connected:true};return this.getPatients();}
    const metric=(value:number|null|undefined,ok:boolean):Metric=>ok&&typeof value==='number'&&Number.isFinite(value)?{value,quality:'good',available:true}:unavailable();
    this.reading={patientId:this.id,deviceId:d.device_id,measuredAt:snapshot.received_at,receivedAt:snapshot.received_at,connected:true,
      metrics:{hr:unavailable(),spo2:unavailable(),temp:metric(d.object_temp_c,d.mlx90614_ok),ambient:metric(d.ambient_temp_c,d.mlx90614_ok),motion:metric(d.accel_total_g,d.mpu6050_ok)},
      fall:{active:false,quality:'unavailable'}, // Raw acceleration alarms are NOT validated fall classifications.
      raw:{accel_m_s2:null,gyro_deg_s:null,ir:null,red:null,object_temperature_c:d.object_temp_c??null,ambient_temperature_c:d.ambient_temp_c??null},
      hardware:{motionConnected:d.mpu6050_ok,temperatureConnected:d.mlx90614_ok,rawAlarm:d.alarm??null,
        accelG:[d.accel_x_g,d.accel_y_g,d.accel_z_g].every(v=>typeof v==='number')?{x:d.accel_x_g!,y:d.accel_y_g!,z:d.accel_z_g!}:null,
        peakG:d.accel_peak_g??null,uptimeMs:d.uptime_ms,timestampBasis:'bridge_received'},
      ai:{state:'not_connected',model:null,confidence:null},source:'device'};
    this.history.push(this.reading);
    this.history=this.history.filter(r=>Date.parse(r.receivedAt)>=this.clock()-600000).slice(-1200);
    const fresh=this.clock()-Date.parse(snapshot.received_at)<=this.bridge.config.staleAfterMs&&Date.parse(snapshot.received_at)<=this.clock()+5000;
    if(fresh&&d.alarm===true&&!this.activeEvent){
      const id=`motion-${snapshot.received_at}`;this.activeEvent=id;
      this.events.push({id,patientId:this.id,type:'raw_firmware_alarm',severity:'unknown',occurredAt:snapshot.received_at,updatedAt:snapshot.received_at,
        acknowledgedAt:null,acknowledgedBy:null,status:'new',conditionActive:true,resolvedAt:null,summary:'Raw firmware alarm · Not a validated fall',source:'device'});
    }else if(fresh&&d.alarm===false&&this.activeEvent){
      const event=this.events.find(a=>a.id===this.activeEvent);if(event){event.conditionActive=false;event.status='resolved';event.resolvedAt=snapshot.received_at;event.updatedAt=snapshot.received_at;}this.activeEvent=null;
    }else if(fresh&&this.activeEvent){const event=this.events.find(a=>a.id===this.activeEvent);if(event)event.updatedAt=snapshot.received_at;}
    this.events=this.events.slice(-200);
    return this.getPatients();
  }
}
