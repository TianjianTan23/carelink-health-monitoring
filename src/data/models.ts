import {z} from 'zod';

const timestamp=z.string().datetime({offset:true});
export const QualitySchema=z.enum(['good','poor','unavailable','unknown']);
export const LevelSchema=z.enum(['red','yellow','green','unknown']);
const source=z.enum(['mock','device','backend']);
export const MetricSchema=z.object({value:z.number().finite().nullable(),quality:QualitySchema,available:z.boolean().optional(),displayValue:z.number().finite().nullable().optional(),held:z.boolean().optional(),lastValidAt:timestamp.nullable().optional(),sampleId:z.string().optional(),signalState:z.string().optional(),signalQuality:z.number().nullable().optional(),sampleCount:z.number().nullable().optional(),gapCount:z.number().nullable().optional()});
export const PredictionSchema=z.object({
  state:z.enum(['not_connected','pending','available','failed','unavailable']),
  id:z.string().nullable().optional(),patientId:z.string().nullable().optional(),
  predictedAt:timestamp.nullable().optional(),inputsMeasuredAt:timestamp.nullable().optional(),
  model:z.string().nullable(),modelVersion:z.string().nullable().optional(),
  result:z.unknown().optional(),confidence:z.number().finite().min(0).max(1).nullable(),
  confidenceMeaning:z.string().nullable().optional(),source:source.optional(),
});
const vector=z.object({x:z.number().finite(),y:z.number().finite(),z:z.number().finite()});
export const AssessmentSchema=z.object({level:LevelSchema,reasons:z.array(z.string()),assessedAt:timestamp,ruleSetId:z.string().nullable(),origin:z.literal('backend')});
export const SensorReadingSchema=z.object({
  patientId:z.string().min(1),deviceId:z.string().min(1),measuredAt:timestamp,receivedAt:timestamp,
  connected:z.boolean(),metrics:z.object({hr:MetricSchema,temp:MetricSchema,spo2:MetricSchema.optional()}),
  fall:z.object({active:z.boolean(),quality:QualitySchema,eventAt:timestamp.nullable().optional()}),
  raw:z.object({accel_m_s2:vector.nullable(),gyro_deg_s:vector.nullable(),ir:z.number().nullable(),red:z.number().nullable(),object_temperature_c:z.number().nullable(),ambient_temperature_c:z.number().nullable()}).nullable(),
  ai:PredictionSchema,source,scenario:z.string().optional(),assessment:AssessmentSchema.nullable().optional(),
});
export const PatientSchema=z.object({
  id:z.string().min(1),name:z.string().min(1),age:z.number().int().min(0),sex:z.string(),
  history:z.string(),bed:z.string(),color:z.string(),admittedAt:z.string(),allergies:z.string(),
  scenario:z.string().optional(),reading:SensorReadingSchema.nullable(),
}).superRefine((p,c)=>{if(p.reading&&p.reading.patientId!==p.id)c.addIssue({code:'custom',message:'Reading patientId does not match profile'});});
export const AlertSchema=z.object({
  id:z.string().min(1),patientId:z.string().min(1),type:z.string().min(1),severity:LevelSchema,
  occurredAt:timestamp,updatedAt:timestamp,acknowledgedAt:timestamp.nullable(),acknowledgedBy:z.string().nullable(),
  status:z.enum(['new','acknowledged','resolved']),conditionActive:z.boolean(),
  resolvedAt:timestamp.nullable(),summary:z.string(),source,
}).superRefine((a,c)=>{
  if(a.status==='acknowledged'&&!a.acknowledgedAt)c.addIssue({code:'custom',message:'Acknowledged alert requires acknowledgedAt'});
  if(a.status==='resolved'&&(!a.resolvedAt||a.conditionActive))c.addIssue({code:'custom',message:'Resolved alert requires resolvedAt and inactive condition'});
});
export const SessionSchema=z.object({simulation:z.boolean().optional(),csrfToken:z.string().optional(),userId:z.string(),role:z.enum(['clinician','patient','family']),mode:z.enum(['pro','basic']),patientIds:z.array(z.string())}).superRefine((s,c)=>{
  if(s.mode==='pro'&&s.role!=='clinician')c.addIssue({code:'custom',message:'Pro requires clinician role'});
});
export type Patient=z.infer<typeof PatientSchema>;
export type SensorReading=z.infer<typeof SensorReadingSchema>;
export type Prediction=z.infer<typeof PredictionSchema>;
export type Alert=z.infer<typeof AlertSchema>;
export type Session=z.infer<typeof SessionSchema>;
export type Quality=z.infer<typeof QualitySchema>;
export type Level=z.infer<typeof LevelSchema>;
export type MetricKey='hr'|'temp';
export type AppMode='pro'|'basic';
export type Language='zh'|'en';
export type ServiceMode='mock'|'live';
export type Resource<T>={state:'idle'|'loading'|'ready'|'empty'|'error';data:T;error:string|null;updatedAt:number|null};
export const initialResource=<T>(data:T):Resource<T>=>({state:'idle',data,error:null,updatedAt:null});
export type DemoRules={hr:{severeLow:number;mildLow:number;mildHigh:number;severeHigh:number};spo2:{severeLow:number;mildLow:number};temp:{severeLow:number;mildLow:number;mildHigh:number;severeHigh:number};staleAfterSeconds:number};
