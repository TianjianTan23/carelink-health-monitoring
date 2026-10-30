import {MockService} from '../../dist/service.js';
import {triage} from '../../dist/rules.js';
import {AlertSchema,PatientSchema,SensorReadingSchema,SessionSchema,type Alert,type AppMode,type DemoRules} from './models';
import {DataError,type DataService,type Scenario} from './service';

// Public demo credentials only; these never authenticate to the Python API.
export class MockDataService implements DataService {
  readonly mode='mock' as const;
  private legacy=new MockService();
  private records:Alert[]=[];
  private failing=false;
  setNetworkFailure(enabled:boolean){this.failing=enabled;}
  private checkNetwork(){if(this.failing)throw new DataError('network','Simulated connection failure');}
  private userId='demo-clinician';
  private session:ReturnType<typeof SessionSchema.parse>|null=null;
  get rules(){return this.legacy.rules as DemoRules;}
  async authenticate(username:string,password:string){
    this.checkNetwork();
    const account=username.trim().toLowerCase();
    if(account==='demo-patient'&&password==='coursework-demo')return this.getSession('basic');
    if(account==='demo-clinician'&&password==='coursework-demo')return this.getSession('pro');
    throw new DataError('forbidden','Invalid user ID or password',401);
  }
  async logout(){this.session=null;}
  async getSession(mode:AppMode='pro'){this.checkNetwork();
    this.session=SessionSchema.parse(await this.legacy.getSession(mode));this.userId=this.session.userId;return structuredClone(this.session);
  }
  private allowed(id:string){return this.session?.patientIds.includes(id)===true;}
  private reconcile(patients:ReturnType<typeof PatientSchema.parse>[]){
    const time=new Date().toISOString();
    for(const p of patients){const r=triage(p.reading,this.rules);const summary=r.reasons.join(' · ');const active=this.records.find(a=>a.patientId===p.id&&a.conditionActive);
      if(active?.summary===summary&&active.severity===r.level){active.updatedAt=time;continue;}
      if(active){active.conditionActive=false;active.status='resolved';active.resolvedAt=time;active.updatedAt=time;}
      if(r.level!=='green')this.records.push(AlertSchema.parse({id:globalThis.crypto?.randomUUID?.()??`demo-${Date.now()}-${this.records.length}`,patientId:p.id,type:p.reading?.fall.active?'fall':r.level==='unknown'?'data_quality':'vital',severity:r.level,occurredAt:time,updatedAt:time,acknowledgedAt:null,acknowledgedBy:null,status:'new',conditionActive:true,resolvedAt:null,summary,source:'mock'}));
    }
  }
  async getPatients(){this.checkNetwork();const patients=PatientSchema.array().parse(await this.legacy.getPatients());this.reconcile(patients);return patients.filter(p=>this.allowed(p.id));}
  async getPatient(id:string){if(!this.allowed(id))throw new DataError('forbidden','Patient is outside session scope');return (await this.getPatients()).find(p=>p.id===id)??null;}
  async getReadings(id:string){this.checkNetwork();if(!this.allowed(id))throw new DataError('forbidden','Patient is outside session scope');return SensorReadingSchema.array().parse(await this.legacy.getHistory(id));}
  async getPredictions(id:string){this.checkNetwork();if(!this.allowed(id))throw new DataError('forbidden','Patient is outside session scope');return [];}
  async getAlerts(){await this.getPatients();return structuredClone(this.records.filter(a=>this.allowed(a.patientId))).reverse();}
  async acknowledgeAlert(id:string){this.checkNetwork();const a=this.records.find(a=>a.id===id&&this.allowed(a.patientId));if(this.session?.mode!=='pro'||!a)throw new DataError('forbidden','Clinician session required');if(a.status==='resolved')throw new DataError('http','Alert already resolved',409);if(!a.acknowledgedAt){a.acknowledgedAt=new Date().toISOString();a.acknowledgedBy=this.userId;a.status='acknowledged';a.updatedAt=a.acknowledgedAt;}return structuredClone(a);}
  async refresh(){await this.legacy.refresh();return this.getPatients();}
  setScenario(id:string,scene:Scenario){if(!this.allowed(id))throw new DataError('forbidden','Patient is outside session scope');this.legacy.setScenario(id,scene);}
  updateDemoRules(rules:DemoRules){this.legacy.rules=structuredClone(rules);}
  reset(){this.failing=false;this.legacy.reset();this.records=[];}
}
