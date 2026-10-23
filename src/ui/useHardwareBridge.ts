import {useCallback,useEffect,useRef,useState} from 'react';
import {HardwareBridgeError,type HardwareBridgeService,type HardwareSnapshot} from '../data/HardwareBridgeService';

export function useHardwareBridge(service:HardwareBridgeService){
  const [snapshot,setSnapshot]=useState<HardwareSnapshot|null>(null);
  const [state,setState]=useState<'loading'|'ready'|'waiting'|'error'>('loading');
  const [error,setError]=useState<string|null>(null),[now,setNow]=useState(Date.now());
  const request=useRef<(()=>void)|null>(null);
  const refresh=useCallback(()=>request.current?.(),[]);
  useEffect(()=>{
    let disposed=false,busy=false,timer:ReturnType<typeof setTimeout>|undefined;
    const controller=new AbortController();
    setSnapshot(null);setState('loading');setError(null);
    const poll=async()=>{
      if(disposed||busy)return;
      clearTimeout(timer);busy=true;
      try{
        const next=await service.latest(controller.signal);
        if(!disposed){setSnapshot(next);setState('ready');setError(null);}
      }catch(e){
        if(!disposed){
          const waiting=e instanceof HardwareBridgeError&&e.code==='waiting';
          setState(waiting?'waiting':'error');setError(e instanceof Error?e.message:'Bridge request failed');
          if(waiting)setSnapshot(null); // An empty bridge after restart invalidates its old in-memory record.
        }
      }finally{
        busy=false;
        if(!disposed){setNow(Date.now());timer=setTimeout(()=>void poll(),service.config.pollIntervalMs);}
      }
    };
    request.current=()=>void poll();
    void poll();
    const clock=setInterval(()=>setNow(Date.now()),1000);
    return()=>{disposed=true;controller.abort();clearTimeout(timer);clearInterval(clock);request.current=null;};
  },[service]);
  return {snapshot,state,error,now,refresh};
}
