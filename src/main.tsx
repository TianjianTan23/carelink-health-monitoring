import React from 'react';
import {createRoot} from 'react-dom/client';
import {App} from './App';
import {loadConfig} from './data/config';
import {createDataService} from './data';
import './styles.css';
const root=createRoot(document.getElementById('root')!);
root.render(<div className="boot" role="status">CareLink · 正在加载 / Loading…</div>);
loadConfig().then(config=>root.render(<App service={createDataService(config)}/>)).catch(error=>root.render(<main className="boot"><h1>CareLink</h1><p role="alert">配置加载失败 / Configuration could not load</p><pre>{error instanceof Error?error.message:String(error)}</pre><button className="button" onClick={()=>location.reload()}>重试 / Retry</button></main>));
