import {act,renderHook,waitFor} from '@testing-library/react';
import {it,expect,vi} from 'vitest';
import {useResource} from './useResource';
it('failed refresh keeps the original data timestamp; a new subject clears previous content',async()=>{
 const load=vi.fn().mockResolvedValueOnce(['patient-a']).mockRejectedValueOnce(new Error('network unavailable'));
 const {result,rerender}=renderHook(({id})=>useResource(load,[] as string[],v=>v.length===0,true,id),{initialProps:{id:'a'}});
 await waitFor(()=>expect(result.current[0].state).toBe('ready'));const timestamp=result.current[0].updatedAt;
 await act(async()=>{await result.current[1]();});expect(result.current[0]).toMatchObject({state:'error',data:['patient-a'],updatedAt:timestamp});
 load.mockResolvedValueOnce([]);rerender({id:'b'});await waitFor(()=>expect(result.current[0].state).toBe('empty'));expect(result.current[0].data).toEqual([]);
});
it('a late response cannot replace a newly selected patient',async()=>{
 let finishA!:(value:string[])=>void;const a=new Promise<string[]>(resolve=>{finishA=resolve;});
 const loadA=()=>a,loadB=async()=>['patient-b'];
 const {result,rerender}=renderHook(({id,load})=>useResource(load,[] as string[],v=>v.length===0,true,id),{initialProps:{id:'a',load:loadA}});
 rerender({id:'b',load:loadB});await waitFor(()=>expect(result.current[0].data).toEqual(['patient-b']));
 await act(async()=>{finishA(['patient-a']);await a;});expect(result.current[0].data).toEqual(['patient-b']);
});

it('coalesces fast polls and renders a slow successful response',async()=>{
 let finish!:(v:string[])=>void;const pending=new Promise<string[]>(resolve=>{finish=resolve;});
 const load=vi.fn(()=>pending);
 const first=()=>load(),second=()=>load(),third=()=>load();
 const {result,rerender}=renderHook(({loadFn})=>useResource(loadFn,[] as string[],v=>!v.length,true,'same-patient'),{initialProps:{loadFn:first}});
 rerender({loadFn:second});rerender({loadFn:third});
 expect(load).toHaveBeenCalledTimes(1);
 await act(async()=>{finish(['fresh-reading']);await pending;});
 await waitFor(()=>expect(result.current[0].data).toEqual(['fresh-reading']));
});
