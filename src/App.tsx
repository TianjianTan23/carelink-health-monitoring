import React,{useCallback,useEffect,useRef,useState} from 'react';
import type {Language,Patient,Session} from './data/models';
import {DataError,type DataService} from './data/service';
import {UIContext} from './ui/context';
import {Icon} from './ui/Icons';
import {ResourceNotice,SourceNotice} from './ui/components';
import {AlertsPage} from './ui/pages';
import {ChartsPage,ClassificationsPage,HistoryPage,ReadingsPage,SettingsPage} from './ui/monitoring-pages';
import {useResource} from './ui/useResource';

type Page='readings'|'history'|'charts'|'classifications'|'alerts'|'settings';

function stored(key:string,fallback:string){try{return localStorage.getItem(key)||fallback;}catch{return fallback;}}
function remember(key:string,value:string){try{localStorage.setItem(key,value);}catch{/* Preferences are optional. */}}

export function App({service}:{service:DataService}){
  const [lang,setLang]=useState<Language>(stored('carelink-v3-language','en')==='zh'?'zh':'en');
  const [theme,setTheme]=useState(stored('carelink-v3-theme','light')==='dark'?'dark':'light');
  const [session,setSession]=useState<Session|null>(null);
  const [logoutUnconfirmed,setLogoutUnconfirmed]=useState(false);
  const [page,setPage]=useState<Page>('readings');
  const [selected,setSelected]=useState('');
  const [refreshVersion,setRefreshVersion]=useState(0);
  const [now,setNow]=useState(Date.now());
  const lastHearts=useRef<Record<string,{value:number;measuredAt:string}>>({});
  const t=useCallback((zh:string,en:string)=>lang==='zh'?zh:en,[lang]);

  useEffect(()=>{document.documentElement.lang=lang==='zh'?'zh-CN':'en';remember('carelink-v3-language',lang);},[lang]);
  useEffect(()=>{document.documentElement.dataset.theme=theme;remember('carelink-v3-theme',theme);},[theme]);
  useEffect(()=>{const timer=window.setInterval(()=>setNow(Date.now()),1000);return()=>window.clearInterval(timer);},[]);
  useEffect(()=>{window.scrollTo({top:0,left:0,behavior:'instant'});},[page,selected]);

  const load=useCallback(async()=>{try{return await service.refresh();}catch(error){if(error instanceof DataError&&error.status===401){setSession(null);setSelected('');}throw error;}},[service,session?.userId]);
  const [patients,reload]=useResource(load,[] as Patient[],rows=>rows.length===0,session!==null,session?.userId??'signed-out');
  const authorized=patients.data.filter(patient=>session?.patientIds.includes(patient.id));
  for(const patient of authorized){
    const reading=patient.reading,heart=reading?.metrics.hr;
    const age=reading?now-Date.parse(reading.measuredAt):Infinity;
    if(reading?.source==='device'&&reading.connected&&age>=0&&age<6000&&heart?.quality==='good'&&heart.available!==false&&heart.value!==null&&Number.isFinite(heart.value))lastHearts.current[patient.id]={value:heart.value,measuredAt:reading.measuredAt};
  }

  useEffect(()=>{
    if(!session)return;
    const current=window.setInterval(()=>{void reload();},1000);
    const history=window.setInterval(()=>setRefreshVersion(version=>version+1),30000);
    return()=>{window.clearInterval(current);window.clearInterval(history);};
  },[session,reload]);
  useEffect(()=>{if(authorized.length&&!authorized.some(patient=>patient.id===selected))setSelected(authorized[0].id);},[authorized,selected]);

  const signedIn=(next:Session)=>{lastHearts.current={};setLogoutUnconfirmed(false);setSession(next);setSelected(next.patientIds[0]??'');setPage('readings');setRefreshVersion(version=>version+1);};
  useEffect(()=>{
    let cancelled=false;
    if(service.mode==='live')void service.getSession().then(next=>{if(!cancelled)signedIn(next);}).catch(()=>{/* Login remains available; no cached identity grants access. */});
    return()=>{cancelled=true;};
  },[service]);
  const signOut=async()=>{lastHearts.current={};try{await service.logout?.();setLogoutUnconfirmed(false);}catch{setLogoutUnconfirmed(true);}finally{setSession(null);setSelected('');setPage('readings');}};
  const refresh=()=>{void reload();setRefreshVersion(version=>version+1);setNow(Date.now());};
  const toggleLanguage=()=>setLang(value=>value==='zh'?'en':'zh');
  const toggleTheme=()=>setTheme(value=>value==='light'?'dark':'light');
  const openPatient=(id:string)=>{setSelected(id);setPage('readings');};
  const context={lang,t,service,now,refreshVersion};

  if(!session)return <UIContext.Provider value={context}><Login onSignIn={signedIn} language={toggleLanguage} theme={toggleTheme} logoutUnconfirmed={logoutUnconfirmed}/></UIContext.Provider>;

  const navigation:Array<[Page,string,string,string]>=[
    ['readings','读数','Readings','heart'],
    ['history','历史记录','History','patients'],
    ['charts','图表','Charts','lcd'],
    ['classifications','分类与置信度','Classifications','shield'],
    ['alerts','告警历史','Alert history','alert'],
    ['settings','设置','Settings','settings'],
  ];
  const shared={patients:authorized,selectedId:selected,select:setSelected,session};
  const content=page==='readings'?<ReadingsPage {...shared} lastHeart={lastHearts.current[selected]??null}/>
    :page==='history'?<HistoryPage {...shared}/>
    :page==='charts'?<ChartsPage {...shared}/>
    :page==='classifications'?<ClassificationsPage {...shared}/>
    :page==='alerts'?<AlertsPage session={session} patients={authorized} openPatient={openPatient}/>
    :<SettingsPage session={session} language={toggleLanguage} theme={toggleTheme} currentTheme={theme}/>;

  return <UIContext.Provider value={context}>
    <a className="skip" href="#main">{t('跳到主内容','Skip to content')}</a>
    <div className={`desktop ${session.mode}`}>
      <aside className="sidebar">
        <div className="brand"><span className="brand-icon"><Icon name="heart" size={25}/></span><div>CareLink<small>{t('安护健康监测','Health monitoring')}</small></div></div>
        <span className="workspace-name">{session.role==='clinician'?t('护士工作台','NURSE WORKSPACE'):t('病人视图','PATIENT VIEW')}</span>
        <nav aria-label={t('主导航','Main navigation')}>{navigation.map(([key,zh,en,icon])=><button key={key} className={page===key?'active':''} aria-current={page===key?'page':undefined} onClick={()=>setPage(key)}><Icon name={icon}/>{t(zh,en)}</button>)}</nav>
        <div className="sidebar-bottom">
          <div className="privacy-card"><Icon name="shield"/><small>{session.role==='clinician'?t('护士可查看患者数据并确认告警。','Nurse access: view patient data and acknowledge alerts.'):t('病人账号只可查看自己的数据。','Patient access: own data only.')}</small></div>
          <button className="sidebar-control" onClick={signOut}><Icon name="logout" size={16}/>{t('退出登录','Sign out')}</button>
        </div>
      </aside>
      <div className="workspace">
        <header className="topbar"><div className="breadcrumbs">CareLink <span>/</span> {t(navigation.find(item=>item[0]===page)?.[1]??'',navigation.find(item=>item[0]===page)?.[2]??'')}</div><div className="top-actions"><span className={`source-chip ${service.mode}`}>{service.mode==='mock'?'DEMO':t('实时 API · 1秒','LIVE API · 1s')}</span><button className="button quiet" onClick={refresh}><Icon name="refresh" size={16}/>{t('刷新','Refresh')}</button><button className="button quiet" onClick={toggleLanguage}>{lang==='zh'?'English':'中文'}</button><button className="icon-button" aria-label={theme==='light'?t('切换深色','Switch to dark'):t('切换浅色','Switch to light')} onClick={toggleTheme}><Icon name={theme==='light'?'moon':'sun'}/></button><span className="user-chip" title={session.userId}>{session.role==='clinician'?'N':'P'}</span></div></header>
        <main id="main" tabIndex={-1}><SourceNotice/><ResourceNotice resource={patients} retry={refresh} emptyLabel={t('暂无授权患者','No authorized patients')}/>{content}<footer>CareLink · {t('健康监测课程项目','Health monitoring coursework')}<span>{t('心率 · 体温 · 跌倒','Heart rate · Temperature · Fall')}</span></footer></main>
      </div>
    </div>
  </UIContext.Provider>;
}

function Login({onSignIn,language,theme,logoutUnconfirmed}:{onSignIn:(session:Session)=>void;language:()=>void;theme:()=>void;logoutUnconfirmed:boolean}){
  const [username,setUsername]=useState('');
  const [password,setPassword]=useState('');
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const {service,t,lang}=React.useContext(UIContext)!;
  const signIn=async(event:React.FormEvent)=>{
    event.preventDefault();setError('');
    if(!username.trim()||!password){setError(t('请输入用户 ID 和密码。','Enter a user ID and password.'));return;}
    setBusy(true);
    try{onSignIn(await service.authenticate(username,password));}
    catch(requestError){setError(requestError instanceof Error?requestError.message:t('登录失败','Sign-in failed'));}
    finally{setPassword('');setBusy(false);}
  };
  return <div className="login-screen"><div className="login-controls"><button className="button" onClick={language}>{lang==='zh'?'English':'中文'}</button><button className="icon-button" onClick={theme} aria-label={t('切换外观','Switch appearance')}><Icon name="sun"/></button></div><div className="login-window"><section className="login-story"><div className="brand"><span className="brand-icon"><Icon name="heart" size={26}/></span><div>CareLink<small>{t('安护','Health monitoring')}</small></div></div><span className="eyebrow">HEART RATE · TEMPERATURE · FALL</span><h1>{t('一个账号，\n一个清晰的照护视角。','One account.\nThe right care view.')}</h1><p>{t('模型给出综合分类与置信度，规则模块说明异常来自哪里。','The model provides the overall label and confidence; rules explain which inputs are abnormal.')}</p><div className="story-art"><span className="care-orbit"><Icon name="heart" size={60}/></span><svg className="care-wave" viewBox="0 0 400 100" aria-hidden="true"><path d="M0 52H95L120 52L139 30L157 77L178 15L203 63L220 52H400"/></svg><span>{t('数据、算法与照护界面相连','Sensors, model and care UI connected')}</span></div></section><section className="login-form-area"><div className="window-dots" aria-hidden="true"><i/><i/><i/></div><span className="eyebrow">ROLE-BASED ACCESS</span><h2>{t('登录 CareLink','Sign in to CareLink')}</h2><p className="muted">{t('角色由用户 ID 决定；账号和密码不会显示在页面上。','Your user ID determines the role; account credentials are never displayed on this page.')}</p>{logoutUnconfirmed&&<div className="form-error" role="alert">{t('已退出本机视图，但未能确认服务器会话撤销。请恢复连接后重试。','Local view signed out. Server session revocation could not be confirmed; reconnect and retry.')}</div>}{service.mode==='mock'&&<div className="demo-entry"><p>{t('离线模拟演示：不是正式账号登录，不连接传感器。','Offline simulated demo: not server authentication or hardware data.')}</p><button className="button" type="button" onClick={()=>void service.getSession('basic').then(onSignIn).catch(()=>setError(t('模拟服务不可用','Demo unavailable')))}>{t('打开病人演示','Open patient demo')}</button><button className="button" type="button" onClick={()=>void service.getSession('pro').then(onSignIn).catch(()=>setError(t('模拟服务不可用','Demo unavailable')))}>{t('打开护士演示','Open nurse demo')}</button></div>}<form onSubmit={signIn} noValidate><label htmlFor="login-user">{t('用户 ID','User ID')}</label><input id="login-user" value={username} onChange={event=>setUsername(event.target.value)} autoComplete="off" autoCapitalize="none" spellCheck={false}/><label htmlFor="login-password">{t('密码','Password')}</label><div className="password-field"><input id="login-password" type="password" value={password} onChange={event=>setPassword(event.target.value)} autoComplete="new-password"/></div>{error&&<div className="form-error" role="alert">{error}</div>}<button className="button primary full" disabled={busy}>{busy?t('登录中…','Signing in…'):t('登录','Sign in')}<Icon name="arrow"/></button></form><small className="caption"><Icon name="shield" size={14}/>{t('密码始终以掩码输入，服务端仅保存加盐哈希。','Passwords remain masked; the server stores salted hashes only.')}</small></section></div></div>;
}
