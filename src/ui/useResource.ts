import {useCallback,useEffect,useRef,useState} from 'react';
import {initialResource,type Resource} from '../data/models';
export function useResource<T>(load:()=>Promise<T>,initial:T,empty:(v:T)=>boolean,enabled=true,identity='resource'){
  const [resource,setResource]=useState<Resource<T>>(()=>initialResource(initial));
  const generation=useRef(0),emptyRef=useRef(empty),key=useRef(identity);emptyRef.current=empty;
  const run=useCallback(async()=>{
    const version=++generation.current;
    // Keep already-rendered live data visible during background polling. Only
    // the first request displays the loading state.
    setResource(previous=>previous.state==='idle'?{...previous,state:'loading',error:null}:{...previous,error:null});
    try{const data=await load();if(version===generation.current)setResource({state:emptyRef.current(data)?'empty':'ready',data,error:null,updatedAt:Date.now()});}
    catch(e){if(version===generation.current)setResource(previous=>({...previous,state:'error',error:e instanceof Error?e.message:'Unknown request error'}));}
  },[load]);
  useEffect(()=>{
    if(key.current!==identity){key.current=identity;setResource(initialResource(initial));}
    if(enabled)void run();else setResource(initialResource(initial));
    return()=>{generation.current++;};
  },[run,enabled,identity]); // changing subject clears data; refreshing the same subject retains timestamps
  return [resource,run] as const;
}
