import React,{useMemo} from 'react';
import {App} from './App';
import {HardwareBridgeService} from './data/HardwareBridgeService';
import {HardwareDataService} from './data/HardwareDataService';
// Compatibility entry point: hardware uses the complete product UI.
export function HardwareApp({service}:{service:HardwareBridgeService}){
  const data=useMemo(()=>new HardwareDataService(service),[service]);
  return <App service={data}/>;
}
