import React,{createContext,useContext} from 'react';
import type {DataService} from '../data/service';
import type {Language} from '../data/models';
export type UIContextValue={lang:Language;t:(zh:string,en:string)=>string;service:DataService;now:number;refreshVersion:number};
export const UIContext=createContext<UIContextValue|null>(null);
export function useUI(){const value=useContext(UIContext);if(!value)throw new Error('UIContext missing');return value;}
