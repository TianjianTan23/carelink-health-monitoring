import {useCallback,useEffect,useRef,useState} from 'react';
import {initialResource,type Resource} from '../data/models';

// Coalesce polling while a request is in flight. A slow response must still be
// rendered; changing patient/role or unmounting invalidates older requests.
export function useResource<T>(load:()=>Promise<T>,initial:T,empty:(v:T)=>boolean,enabled=true,identity='resource'){
  const [resource,setResource]=useState<Resource<T>>(()=>initialResource(initial));
  const generation=useRef(0),loadRef=useRef(load),emptyRef=useRef(empty);
  const inFlight=useRef<{version:number;promise:Promise<void>}|null>(null);
  loadRef.current=load;emptyRef.current=empty;
  const run=useCallback(()=>{
    if(!enabled)return Promise.resolve();
    if(inFlight.current)return inFlight.current.promise;
    const version=++generation.current;
    setResource(previous=>previous.state==='idle'?{...previous,state:'loading',error:null}:{...previous,error:null});
    const promise=(async()=>{
      try{
        const data=await loadRef.current();
        if(version===generation.current)setResource({state:emptyRef.current(data)?'empty':'ready',data,error:null,updatedAt:Date.now()});
      }catch(e){
        if(version===generation.current)setResource(previous=>({...previous,state:'error',error:e instanceof Error?e.message:'Unknown request error'}));
      }finally{if(inFlight.current?.version===version)inFlight.current=null;}
    })();
    inFlight.current={version,promise};
    return promise;
  },[enabled,identity]);
  useEffect(()=>{
    generation.current++;inFlight.current=null;
    setResource(initialResource(initial));
    return()=>{generation.current++;inFlight.current=null;};
  },[enabled,identity]);
  useEffect(()=>{if(enabled)void run();},[load,run,enabled]);
  return [resource,run] as const;
}
