import type {Alert,AppMode,DemoRules,Patient,Prediction,SensorReading,ServiceMode,Session} from './models';
export type Scenario='normal'|'mild'|'severe'|'fall'|'poor'|'unavailable'|'offline'|'stale'|'noData';
export interface DataService {
  readonly mode:ServiceMode;
  readonly rules:DemoRules;
  authenticate(username:string,password:string):Promise<Session>;
  logout?():Promise<void>;
  rotateSession?():Promise<void>;
  getSession(mode?:AppMode):Promise<Session>;
  getPatients():Promise<Patient[]>;
  getPatient(id:string):Promise<Patient|null>;
  getReadings(id:string):Promise<SensorReading[]>;
  getPredictions(id:string):Promise<Prediction[]>;
  getAlerts():Promise<Alert[]>;
  acknowledgeAlert(id:string):Promise<Alert>;
  refresh():Promise<Patient[]>;
  setScenario?(id:string,scene:Scenario):void;
  updateDemoRules?(rules:DemoRules):void;
  reset?():void;
  setNetworkFailure?(enabled:boolean):void;
}
export class DataError extends Error {
  constructor(public readonly code:'configuration'|'network'|'http'|'invalid_data'|'not_found'|'forbidden',message:string,public readonly status?:number){super(message);this.name='DataError';}
}
