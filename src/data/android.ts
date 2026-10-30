import {Capacitor,registerPlugin} from '@capacitor/core';
import {DataError} from './service';

interface NativeApi {
  configure(options:{origin:string}):Promise<void>;
  request(options:{path:string;method:string;body?:string}):Promise<{status:number;body:string}>;
}
const native=registerPlugin<NativeApi>('CareLinkApi');
export const isAndroid=()=>Capacitor.isNativePlatform()&&Capacitor.getPlatform()==='android';
export function apiOrigin(value:string){
  const url=new URL(value.trim());
  if(url.protocol!=='https:'||url.username||url.password||url.search||url.hash||!['','/'].includes(url.pathname))throw new DataError('configuration','Use an HTTPS origin, including its port; no path or credentials.');
  const usbTunnel=url.hostname==='127.0.0.1'&&url.port==='19443';
  if(['localhost','127.0.0.1','[::1]'].includes(url.hostname)&&isAndroid()&&!usbTunnel)throw new DataError('configuration','Use the Mac LAN HTTPS address, or https://127.0.0.1:19443 with an active ADB USB tunnel.');
  return url.origin;
}
export async function configureAndroid(origin:string){await native.configure({origin:apiOrigin(origin)});}
// No Cookie/Token is returned to JavaScript. Native HTTPS and Keystore own it.
export function androidTransport(origin:string):typeof fetch {
  return (async(input:RequestInfo|URL,options:RequestInit={})=>{
    const url=new URL(String(input));
    if(url.origin!==origin)throw new DataError('configuration','Cross-origin native request refused.');
    const result=await native.request({path:url.pathname+url.search,method:options.method??'GET',...(typeof options.body==='string'?{body:options.body}:{})});
    return new Response([204,205,304].includes(result.status)?null:result.body,{status:result.status,headers:{'Content-Type':'application/json'}});
  }) as typeof fetch;
}
