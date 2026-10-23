import React,{useState} from 'react';
import {createRoot} from 'react-dom/client';
import {App} from './App';
import {loadConfig} from './data/config';
import {createDataService} from './data';
import {HardwareBridgeService,loadHardwareConfig} from './data/HardwareBridgeService';
import {HardwareDataService} from './data/HardwareDataService';
import {MockDataService} from './data/MockDataService';
import type {DataService} from './data/service';
import type {ServiceMode} from './data/models';
import './styles.css';
import './product.css';
async function source(mode?:ServiceMode):Promise<DataService>{
  if((mode??import.meta.env.VITE_DATA_MODE)==='hardware')return new HardwareDataService(new HardwareBridgeService(await loadHardwareConfig()));
  if(mode==='mock')return new MockDataService();
  const config=await loadConfig();return createDataService(mode==='live'?{...config,mode:'live'}:config);
}
function Workspace({initial}:{initial:DataService}){
  const [service,setService]=useState(initial),[error,setError]=useState(''),[busy,setBusy]=useState(false);
  const change=async(mode:ServiceMode)=>{setBusy(true);setError('');try{setService(await source(mode));}catch(e){setError(e instanceof Error?e.message:String(e));}finally{setBusy(false);}};
  return <>{error&&<div className="source-error" role="alert">{error}<button className="button" onClick={()=>setError('')}>关闭 / Dismiss</button></div>}<App key={service.mode} service={service} changeSource={change} sourceBusy={busy}/></>;
}
const root=createRoot(document.getElementById('root')!);
root.render(<div className="boot" role="status">CareLink · 正在加载 / Loading…</div>);
source().then(initial=>root.render(<Workspace initial={initial}/>)).catch(error=>root.render(<main className="boot"><h1>CareLink</h1><p role="alert">配置加载失败 / Configuration could not load</p><pre>{String(error)}</pre><button className="button" onClick={()=>location.reload()}>重试 / Retry</button></main>));
