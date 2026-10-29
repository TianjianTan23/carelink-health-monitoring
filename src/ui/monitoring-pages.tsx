import React,{useCallback,useEffect,useRef,useState} from 'react';
import type {Language,MetricKey,Patient,Prediction,SensorReading,Session} from '../data/models';
import {MetricGrid,ResourceNotice,StatusPanel} from './components';
import {Icon} from './Icons';
import {metricName,patientName,time,units} from './presentation';
import {useUI} from './context';
import {useResource} from './useResource';
import {chartSeries} from './chart-series';

type SharedProps={
  patients:Patient[];
  selectedId:string;
  select:(id:string)=>void;
  session:Session;
};

function SubjectHeader({patients,selectedId,select,title,subtitle}:{patients:Patient[];selectedId:string;select:(id:string)=>void;title:string;subtitle:string}){
  const {service,lang,t}=useUI();
  const selected=patients.find(patient=>patient.id===selectedId)??patients[0];
  return <div className="page-heading monitoring-heading"><div><span className="eyebrow">CARELINK · SENSOR MONITORING</span><h1>{title}</h1><p>{subtitle}</p></div>{patients.length>1?<label className="patient-switcher">{t('患者','Patient')}<select value={selected?.id??''} onChange={event=>select(event.target.value)}>{patients.map(patient=><option key={patient.id} value={patient.id}>{patientName(patient,lang,service.mode)} · {patient.id}</option>)}</select></label>:selected?<div className="subject-chip"><span>{patientName(selected,lang,service.mode)}</span><small>{selected.id}</small></div>:null}</div>;
}

function currentPatient(patients:Patient[],selectedId:string){return patients.find(patient=>patient.id===selectedId)??patients[0];}

export function ReadingsPage(props:SharedProps){
  const {t,lang}=useUI();
  const patient=currentPatient(props.patients,props.selectedId);
  return <><SubjectHeader {...props} title={t('实时读数','Readings')} subtitle={t('仅展示心率、体温和跌倒检测。','Heart rate, temperature and fall detection only.')}/>{patient?<><StatusPanel reading={patient.reading} prominent={props.session.role==='clinician'}/><MetricGrid reading={patient.reading}/><section className="panel reading-meta"><h2>{t('本次采集','Current snapshot')}</h2><dl><div><dt>{t('采集时间','Measured at')}</dt><dd>{time(patient.reading?.measuredAt,lang)}</dd></div><div><dt>{t('接收时间','Received at')}</dt><dd>{time(patient.reading?.receivedAt,lang)}</dd></div><div><dt>{t('设备','Device')}</dt><dd>{patient.reading?.deviceId??'—'}</dd></div><div><dt>{t('连接状态','Connection')}</dt><dd>{patient.reading?.connected?t('在线','Online'):t('离线或过期','Offline or stale')}</dd></div></dl></section></>:<div className="empty">{t('暂无授权患者','No authorized patient')}</div>}</>;
}

function useHistory(patientId:string,refreshVersion:number,minutes=1440){
  const {service}=useUI();
  const load=useCallback(()=>service.getReadings(patientId,minutes),[service,patientId,refreshVersion,minutes]);
  return useResource(load,[] as SensorReading[],rows=>rows.length===0,Boolean(patientId),`${patientId}:full-history`);
}

export function HistoryPage(props:SharedProps){
  const {service,t,lang,refreshVersion}=useUI();
  const patient=currentPatient(props.patients,props.selectedId);
  const [history,reload]=useHistory(patient?.id??'',refreshVersion);
  const subtitle=service.mode==='live'?t('最近24小时内最多2000条采样记录。','Up to 2,000 recent records within the last 24 hours.'):t('演示历史时间序列。','Demonstration history time series.');
  return <><SubjectHeader {...props} title={t('历史记录','History')} subtitle={subtitle}/><ResourceNotice resource={history} retry={reload} emptyLabel={t('还没有历史读数','No historical readings yet')}/>{history.data.length>0&&<section className="panel"><div className="section-heading"><h2>{t('读数明细','Reading records')}</h2><span className="count-pill">{history.data.length}</span></div><div className="table-wrap history-table"><table><thead><tr><th>{t('时间','Time')}</th><th>{t('心率','Heart rate')}</th><th>{t('体温','Temperature')}</th><th>{t('跌倒','Fall')}</th><th>{t('分类','Classification')}</th></tr></thead><tbody>{history.data.map((reading,index)=><tr key={`${reading.measuredAt}-${index}`}><td>{time(reading.measuredAt,lang)}</td><td>{displayMetric(reading,'hr')} bpm</td><td>{displayMetric(reading,'temp')} °C</td><td>{reading.fall.quality==='good'?(reading.fall.active?t('是','Yes'):t('否','No')):'—'}</td><td><ClassificationPill label={predictionLabel(reading.ai)}/></td></tr>)}</tbody></table></div></section>}</>;
}

function displayMetric(reading:SensorReading,key:MetricKey){
  const metric=reading.metrics[key];
  // Historical measurements remain valid records after the live device becomes stale.
  if(metric.available===false||metric.quality!=='good'||metric.value===null)return '—';
  return key==='temp'?metric.value.toFixed(1):String(Math.round(metric.value));
}

export function ChartsPage(props:SharedProps){
  const {t,refreshVersion}=useUI();
  const patient=currentPatient(props.patients,props.selectedId);
  const [history,reload]=useHistory(patient?.id??'',refreshVersion,10);
  return <><SubjectHeader {...props} title={t('图表','Charts')} subtitle={t('心率和体温历史折线图；缺失或无效数据不会被伪造补齐。','Heart-rate and temperature trends; missing or invalid samples remain gaps.')}/><ResourceNotice resource={history} retry={reload} emptyLabel={t('暂无可绘制的数据','No chart data yet')}/>{history.data.length>0&&<div className="chart-grid"><HistoryChart readings={history.data} metric="hr"/><HistoryChart readings={history.data} metric="temp"/></div>}</>;
}

export function HistoryChart({readings,metric}:{readings:SensorReading[];metric:MetricKey}){
  const {t,lang,now}=useUI();
  const chartRef=useRef<HTMLElement>(null);
  const [chartWidth,setChartWidth]=useState(360);
  useEffect(()=>{if(!chartRef.current||typeof ResizeObserver==='undefined')return;const observer=new ResizeObserver(entries=>{if(entries[0])setChartWidth(Math.max(220,entries[0].contentRect.width));});observer.observe(chartRef.current);return()=>observer.disconnect();},[]);
  const right=chartWidth-14,plotWidth=right-46;
  const points=chartSeries(readings,metric,now);
  const values=points.flatMap(p=>p.value===null?[]:[p.value]);
  const low=values.length?Math.min(...values):0,high=values.length?Math.max(...values):0;
  const padding=metric==='temp'?.4:5,minimum=low-padding,maximum=high+padding;
  const first=points[0]?.time??now,last=points.at(-1)?.time??now,span=Math.max(5000,last-first);
  const segments:string[][]=[];let segment:string[]=[];
  for(const p of points){if(p.value!==null)segment.push(`${46+(p.time-first)/span*plotWidth},${178-(p.value-minimum)/(maximum-minimum)*138}`);else if(segment.length){segments.push(segment);segment=[];}}
  if(segment.length)segments.push(segment);
  return <section ref={chartRef} className="panel chart-card"><div className="section-heading"><h2>{metricName(metric,lang)}</h2><strong>{t('每5秒一个点','One point / 5s')}</strong></div>
    {values.length?<svg className="history-chart" viewBox={`0 0 ${chartWidth} 220`} role="img" aria-label={`${metricName(metric,lang)} ${t('最近10分钟，5秒中位数','Last 10 minutes, 5-second medians')}`}>
      {[40,86,132,178].map((y,i)=><g key={y}><line x1="46" x2={right} y1={y} y2={y}/><text x="4" y={y+4}>{(maximum-(maximum-minimum)*i/3).toFixed(metric==='temp'?1:0)}</text></g>)}
      {segments.map((ps,i)=><g key={i}><polyline points={ps.join(' ')}/>{ps.map((v,j)=>{const [cx,cy]=v.split(',');return <circle key={j} cx={cx} cy={cy} r="1.8"/>;})}</g>)}
      <text x="46" y="214">{time(first,lang)}</text><text x={right} y="214" textAnchor="end">{time(last,lang)}</text>
    </svg>:<div className="trend-empty">{t('持续等待有效采样；首次采集后完成5秒区间即可绘图。','Waiting for valid samples; a completed 5-second interval creates the first point.')}</div>}
    <p className="caption">{t('最近10分钟 · 每5秒汇总有效读数的中位数 · 缺测留空 · 保留旧值不入图。','Last 10 minutes · Median of valid readings per 5 seconds · Missing intervals remain gaps · Held values are excluded.')}</p>
  </section>;
}

function predictionLabel(prediction:Prediction):string|null{
  const result=prediction.result;
  return result&&typeof result==='object'&&'label' in result&&typeof result.label==='string'?result.label:null;
}

function abnormalParams(prediction:Prediction):Array<Record<string,unknown>>{
  const result=prediction.result;
  if(!result||typeof result!=='object'||!('abnormal_params' in result)||!Array.isArray(result.abnormal_params))return [];
  return result.abnormal_params.filter((item):item is Record<string,unknown>=>Boolean(item)&&typeof item==='object');
}

function ClassificationPill({label}:{label:string|null}){return <span className={`classification-pill ${label??'unavailable'}`}>{label??'unavailable'}</span>;}

export function ClassificationsPage(props:SharedProps){
  const {service,t,lang,refreshVersion}=useUI();
  const patient=currentPatient(props.patients,props.selectedId);
  const load=useCallback(()=>service.getPredictions(patient?.id??''),[service,patient?.id,refreshVersion]);
  const [predictions,reload]=useResource(load,[] as Prediction[],items=>items.length===0,Boolean(patient),`${patient?.id??''}:classifications`);
  return <><SubjectHeader {...props} title={t('分类结果与置信度','Classifications & confidence')} subtitle={t('分类结合 LR、CNN 和安全规则；分数含义见各条记录。','Classification combines LR, CNN and safety rules; each record explains its score.')}/><ResourceNotice resource={predictions} retry={reload} emptyLabel={t('暂无分类结果','No classifications yet')}/><div className="classification-list">{predictions.data.map((prediction,index)=>{const label=predictionLabel(prediction),abnormal=abnormalParams(prediction);return <article className="panel classification-record" key={prediction.id??index}><div className="classification-record-head"><div><ClassificationPill label={label}/><h2>{label?t('综合分类','Overall classification'):t('无法分类','Classification unavailable')}</h2><p>{time(prediction.predictedAt,lang)} · {prediction.model??'—'} / {prediction.modelVersion??'—'}</p></div><div className="confidence"><strong>{prediction.confidence===null?'—':`${(prediction.confidence*100).toFixed(1)}%`}</strong><span>{t('返回分数','Returned score')}</span></div></div><p className="caption">{prediction.confidenceMeaning}</p><div className="attribution"><h3>{t('异常参数归因','Abnormal parameter attribution')}</h3>{abnormal.length?<ul>{abnormal.map((item,itemIndex)=><li key={itemIndex}><strong>{String(item.parameter??'unknown')}</strong><span>{String(item.reason??'')}</span>{item.value!==undefined&&<code>{String(item.value)}</code>}</li>)}</ul>:<p className="muted">{label==='normal'?t('规则未发现异常参数。','No abnormal parameter was identified by the rules.'):t('没有可用的归因信息。','No attribution is available.')}</p>}</div></article>;})}</div></>;
}

export function SettingsPage({session,language,theme,currentTheme}:{session:Session;language:()=>void;theme:()=>void;currentTheme:string}){
  const {service,t,lang}=useUI();
  return <><div className="page-heading"><div><span className="eyebrow">ACCOUNT · ROLE · DISPLAY</span><h1>{t('设置','Settings')}</h1><p>{t('账号权限和本机显示偏好。','Account scope and local display preferences.')}</p></div></div><div className="settings-grid"><section className="panel"><h2>{t('当前账号','Current account')}</h2><dl className="settings-list"><div><dt>{t('用户 ID','User ID')}</dt><dd>{session.userId}</dd></div><div><dt>{t('角色','Role')}</dt><dd>{session.role==='clinician'?t('护士','Nurse'):t('病人','Patient')}</dd></div><div><dt>{t('视图','View')}</dt><dd>{session.mode==='pro'?t('护士工作台','Nurse workspace'):t('病人视图','Patient view')}</dd></div><div><dt>{t('授权患者','Authorized patients')}</dt><dd>{session.patientIds.join(', ')}</dd></div><div><dt>{t('数据模式','Data mode')}</dt><dd>{service.mode.toUpperCase()}</dd></div></dl></section><section className="panel"><h2>{t('显示偏好','Display preferences')}</h2><div className="settings-actions"><button className="button" onClick={language}><Icon name="unknown"/>{lang==='zh'?'English':'中文'}</button><button className="button" onClick={theme}><Icon name={currentTheme==='light'?'moon':'sun'}/>{currentTheme==='light'?t('深色模式','Dark mode'):t('浅色模式','Light mode')}</button></div><p className="caption">{t('偏好只保存在这台电脑的浏览器中。','Preferences are stored only in this browser.')}</p></section><section className="panel settings-security"><Icon name="shield" size={28}/><div><h2>{t('角色权限','Role permissions')}</h2><p>{session.role==='clinician'?t('护士可以查看患者数据并确认告警。','Nurses can view patient data and acknowledge alerts.'):t('病人只能查看自己的读数、历史、图表、分类和告警，不能确认告警。','Patients can view only their own readings, history, charts, classifications and alerts; they cannot acknowledge alerts.')}</p></div></section></div></>;
}
