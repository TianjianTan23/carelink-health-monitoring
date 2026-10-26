import React,{useCallback,useEffect,useState} from 'react';
import type {Language,Patient,Session} from './data/models';
import type {DataService} from './data/service';
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
  const [page,setPage]=useState<Page>('readings');
  const [selected,setSelected]=useState('');
  const [refreshVersion,setRefreshVersion]=useState(0);
  const [now,setNow]=useState(Date.now());
  const t=useCallback((zh:string,en:string)=>lang==='zh'?zh:en,[lang]);

  useEffect(()=>{document.documentElement.lang=lang==='zh'?'zh-CN':'en';remember('carelink-v3-language',lang);},[lang]);
  useEffect(()=>{document.documentElement.dataset.theme=theme;remember('carelink-v3-theme',theme);},[theme]);
  useEffect(()=>{const timer=window.setInterval(()=>setNow(Date.now()),1000);return()=>window.clearInterval(timer);},[]);
  useEffect(()=>{window.scrollTo({top:0,left:0,behavior:'instant'});},[page,selected]);

  const load=useCallback(()=>service.refresh(),[service,session?.userId]);
  const [patients,reload]=useResource(load,[] as Patient[],rows=>rows.length===0,session!==null,session?.userId??'signed-out');
  const authorized=patients.data.filter(patient=>session?.patientIds.includes(patient.id));

  useEffect(()=>{
    if(!session)return;
    const timer=window.setInterval(()=>{void reload();setRefreshVersion(version=>version+1);},3000);
    return()=>window.clearInterval(timer);
  },[session,reload]);
  useEffect(()=>{if(authorized.length&&!authorized.some(patient=>patient.id===selected))setSelected(authorized[0].id);},[authorized,selected]);

  const signedIn=(next:Session)=>{setSession(next);setSelected(next.patientIds[0]??'');setPage('readings');setRefreshVersion(version=>version+1);};
  const signOut=async()=>{await service.logout?.();setSession(null);setSelected('');setPage('readings');};
  const refresh=()=>{void reload();setRefreshVersion(version=>version+1);setNow(Date.now());};
  const toggleLanguage=()=>setLang(value=>value==='zh'?'en':'zh');
  const toggleTheme=()=>setTheme(value=>value==='light'?'dark':'light');
  const openPatient=(id:string)=>{setSelected(id);setPage('readings');};
  const context={lang,t,service,now,refreshVersion};

  if(!session)return <UIContext.Provider value={context}><Login onSignIn={signedIn} language={toggleLanguage} theme={toggleTheme}/></UIContext.Provider>;

  const navigation:Array<[Page,string,string,string]>=[
    ['readings','读数','Readings','heart'],
    ['history','历史记录','History','patients'],
    ['charts','图表','Charts','lcd'],
    ['classifications','分类与置信度','Classifications','shield'],
    ['alerts','告警历史','Alert history','alert'],
    ['settings','设置','Settings','settings'],
  ];
  const shared={patients:authorized,selectedId:selected,select:setSelected,session};
  const content=page==='readings'?<ReadingsPage {...shared}/>
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
        <header className="topbar"><div className="breadcrumbs">CareLink <span>/</span> {t(navigation.find(item=>item[0]===page)?.[1]??'',navigation.find(item=>item[0]===page)?.[2]??'')}</div><div className="top-actions"><span className={`source-chip ${service.mode}`}>{service.mode==='mock'?'DEMO':'LIVE API'}</span><button className="button quiet" onClick={refresh}><Icon name="refresh" size={16}/>{t('刷新','Refresh')}</button><button className="button quiet" onClick={toggleLanguage}>{lang==='zh'?'English':'中文'}</button><button className="icon-button" aria-label={theme==='light'?t('切换深色','Switch to dark'):t('切换浅色','Switch to light')} onClick={toggleTheme}><Icon name={theme==='light'?'moon':'sun'}/></button><span className="user-chip" title={session.userId}>{session.role==='clinician'?'N':'P'}</span></div></header>
        <main id="main" tabIndex={-1}><SourceNotice/><ResourceNotice resource={patients} retry={refresh} emptyLabel={t('暂无授权患者','No authorized patients')}/>{content}<footer>CareLink · {t('健康监测课程项目','Health monitoring coursework')}<span>{t('心率 · 体温 · 跌倒','Heart rate · Temperature · Fall')}</span></footer></main>
      </div>
    </div>
  </UIContext.Provider>;
}

function Login({onSignIn,language,theme}:{onSignIn:(session:Session)=>void;language:()=>void;theme:()=>void}){
  const [username,setUsername]=useState('');
  const [password,setPassword]=useState('');
  const [showPassword,setShowPassword]=useState(false);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const {service,t,lang}=React.useContext(UIContext)!;
  const signIn=async(event:React.FormEvent)=>{
    event.preventDefault();setError('');
    if(!username.trim()||!password){setError(t('请输入用户 ID 和密码。','Enter a user ID and password.'));return;}
    setBusy(true);
    try{onSignIn(await service.authenticate(username,password));}
    catch(requestError){setError(requestError instanceof Error?requestError.message:t('登录失败','Sign-in failed'));}
    finally{setBusy(false);}
  };
  return <div className="login-screen"><div className="login-controls"><button className="button" onClick={language}>{lang==='zh'?'English':'中文'}</button><button className="icon-button" onClick={theme} aria-label={t('切换外观','Switch appearance')}><Icon name="sun"/></button></div><div className="login-window"><section className="login-story"><div className="brand"><span className="brand-icon"><Icon name="heart" size={26}/></span><div>CareLink<small>{t('安护','Health monitoring')}</small></div></div><span className="eyebrow">HEART RATE · TEMPERATURE · FALL</span><h1>{t('一个账号，\n一个清晰的照护视角。','One account.\nThe right care view.')}</h1><p>{t('模型给出综合分类与置信度，规则模块说明异常来自哪里。','The model provides the overall label and confidence; rules explain which inputs are abnormal.')}</p><div className="story-art"><span className="care-orbit"><Icon name="heart" size={60}/></span><svg className="care-wave" viewBox="0 0 400 100" aria-hidden="true"><path d="M0 52H95L120 52L139 30L157 77L178 15L203 63L220 52H400"/></svg><span>{t('数据、算法与照护界面相连','Sensors, model and care UI connected')}</span></div></section><section className="login-form-area"><div className="window-dots" aria-hidden="true"><i/><i/><i/></div><span className="eyebrow">ROLE-BASED ACCESS</span><h2>{t('登录 CareLink','Sign in to CareLink')}</h2><p className="muted">{t('角色由用户 ID 决定，无需手动选择。','Your user ID determines the role automatically.')}</p><form onSubmit={signIn} noValidate><label htmlFor="login-user">{t('用户 ID','User ID')}</label><input id="login-user" value={username} onChange={event=>setUsername(event.target.value)} autoComplete="username"/><label htmlFor="login-password">{t('密码','Password')}</label><div className="password-field"><input id="login-password" type={showPassword?'text':'password'} value={password} onChange={event=>setPassword(event.target.value)} autoComplete="current-password"/><button type="button" onClick={()=>setShowPassword(value=>!value)}>{showPassword?t('隐藏','Hide'):t('显示','Show')}</button></div>{error&&<div className="form-error" role="alert">{error}</div>}<button className="button primary full" disabled={busy}>{busy?t('登录中…','Signing in…'):t('登录','Sign in')}<Icon name="arrow"/></button></form><div className="demo-accounts"><button type="button" onClick={()=>{setUsername('ttj');setPassword('041003');}}><Icon name="heart"/><span><strong>{t('病人账号','Patient')}</strong><code>ttj / 041003</code></span></button><button type="button" onClick={()=>{setUsername('wyn');setPassword('050403');}}><Icon name="patients"/><span><strong>{t('护士账号','Nurse')}</strong><code>wyn / 050403</code></span></button></div><small className="caption">{t('课程演示凭据；部署前必须改为安全认证和加密密码。','Coursework credentials only; replace with secure authentication and hashed passwords before deployment.')}</small></section></div></div>;
}
