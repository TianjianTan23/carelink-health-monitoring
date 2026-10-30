import React,{useEffect,useState} from 'react';
import {App} from './App';
import {MockDataService} from './data/MockDataService';
import {LiveApiService} from './data/LiveApiService';
import {defaultConfig} from './data/config';
import type {DataService} from './data/service';
import {androidTransport,apiOrigin,configureAndroid,isAndroid} from './data/android';

export function CourseworkShell(){
  const [startupMode]=useState(()=>{try{return localStorage.getItem('carelink-data-mode-v2')??import.meta.env.VITE_DEFAULT_MODE??'live';}catch{return 'live';}});
  const [service,setService]=useState<DataService|null>(()=>startupMode==='mock'?new MockDataService():null);
  const [origin,setOrigin]=useState(()=>{try{return localStorage.getItem('carelink-api-origin-v2')??(!isAndroid()&&location.protocol==='https:'?location.origin:'');}catch{return '';}});
  const [revision,setRevision]=useState(0);
  const [busy,setBusy]=useState(false),[error,setError]=useState('');
  async function connect(){
    setBusy(true);setError('');
    try{
      const target=apiOrigin(origin);
      if(isAndroid())await configureAndroid(target);
      try{localStorage.setItem('carelink-api-origin-v2',target);localStorage.setItem('carelink-data-mode-v2','live');}catch{/* Public endpoint preference only. */}
      setRevision(n=>n+1);
      setService(new LiveApiService({...defaultConfig,mode:'live',baseUrl:target,apiConfirmed:true},isAndroid()?androidTransport(target):undefined));
    }catch{setError('连接配置未完成。请输入带端口的 HTTPS Mac 地址，并信任其 CA；USB 可使用 https://127.0.0.1:19443（需 ADB 隧道）。 / Use a Mac HTTPS origin or the active ADB USB endpoint.');}
    finally{setBusy(false);}
  }
  useEffect(()=>{if(service===null&&origin)void connect();},[]);
  return <><section className="coursework-toolbar" aria-label="Coursework connection">
    <strong>{service?.mode==='mock'?'DEMO · 模拟数据 · 离线演示':'LIVE · Mac 网关 API · 记录来源独立标注'}</strong>
    <span>CareLink · Web + Android · 本地 Mac 网关</span>
    <div><button className="button" onClick={()=>{try{localStorage.setItem('carelink-data-mode-v2','mock');}catch{}setService(new MockDataService());setRevision(n=>n+1);setError('');}}>离线演示 / Offline demo</button>
      <label>Mac HTTPS API <input aria-label="Mac HTTPS API" value={origin} onChange={e=>setOrigin(e.target.value)} placeholder="https://<Mac LAN IP>:<Web API port>" autoCapitalize="none" spellCheck={false}/></label>
      <button className="button" onClick={connect} disabled={busy}>连接 HTTPS / Connect</button></div>
    {error&&<p role="alert">{error}</p>}
    {service?.mode==='live'&&<small>模拟后端也使用真实 API；这不代表已连接 ESP32。设备专用9443不是登录入口。 / API access alone does not verify hardware. USB: https://127.0.0.1:19443 requires an active ADB tunnel.</small>}
  </section>{service?<App key={revision} service={service}/>:<p role="status">请配置 Mac HTTPS API；尚未加载数据，不会回退 DEMO。 / Configure the gateway HTTPS API; no demo fallback.</p>}</>;
}
