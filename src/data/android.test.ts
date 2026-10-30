import {beforeEach,expect,it,vi} from 'vitest';
const bridge=vi.hoisted(()=>({configure:vi.fn().mockResolvedValue(undefined),request:vi.fn()}));
vi.mock('@capacitor/core',()=>({Capacitor:{isNativePlatform:()=>true,getPlatform:()=> 'android'},registerPlugin:()=>bridge}));
import {androidTransport,apiOrigin,configureAndroid} from './android';
beforeEach(()=>vi.clearAllMocks());
it('Android origin refuses HTTP, phone localhost and credentials',()=>{
  for(const value of ['http://10.0.2.2:18445','https://localhost:18445','https://127.0.0.1:18445','https://x:y@example.invalid','https://example.invalid/path'])expect(()=>apiOrigin(value)).toThrow();
  expect(apiOrigin('https://10.0.2.2:18445/')).toBe('https://10.0.2.2:18445');
});
it('native transport does not send or expose Javascript cookies',async()=>{
  bridge.request.mockResolvedValue({status:200,body:'{"status":"ok"}'});
  await configureAndroid('https://10.0.2.2:18445');
  const response=await androidTransport('https://10.0.2.2:18445')('https://10.0.2.2:18445/api/login',{method:'POST',body:'{}',credentials:'include'});
  expect(bridge.configure).toHaveBeenCalledWith({origin:'https://10.0.2.2:18445'});
  expect(bridge.request).toHaveBeenCalledWith({path:'/api/login',method:'POST',body:'{}'});
  expect(response.headers.has('Set-Cookie')).toBe(false);expect(await response.json()).toEqual({status:'ok'});
});
it('cross-origin native requests fail before bridge execution',async()=>{
  await expect(androidTransport('https://10.0.2.2:18445')('https://other.invalid/api/session')).rejects.toThrow();expect(bridge.request).not.toHaveBeenCalled();
});
it('native 401 stays 401 and never becomes mock success',async()=>{
  bridge.request.mockResolvedValue({status:401,body:'{"detail":"Authentication required"}'});
  const response=await androidTransport('https://10.0.2.2:18445')('https://10.0.2.2:18445/api/session');expect(response.status).toBe(401);
});

it('USB permits only the explicit verified HTTPS loopback endpoint',()=>{
  expect(apiOrigin('https://127.0.0.1:19443')).toBe('https://127.0.0.1:19443');
  for(const value of ['http://127.0.0.1:19443','https://127.0.0.1:19444','https://localhost:19443','https://127.0.0.1:19443/api'])expect(()=>apiOrigin(value)).toThrow();
});
