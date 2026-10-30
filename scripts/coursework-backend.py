#!/usr/bin/env python3
"""Local synthetic course backend, never a production service launcher."""
from pathlib import Path
import argparse,json,os,re,socket,ssl,sys,threading
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--initialize',action='store_true');p.add_argument('--host',default='127.0.0.1');p.add_argument('--port',type=int,default=18445);p.add_argument('--lan-ip');p.add_argument('--profile');args=p.parse_args()
    if args.port in {8000,8443,9443,18443,18444} or not 1024<=args.port<=65535:p.error('Use a separate course port (default18445).')
    if args.host!='127.0.0.1' and (not args.lan_ip or args.host!=args.lan_ip):p.error('LAN binding requires --host and --lan-ip to match the approved current Mac IP.')
    if not (ROOT/'build-demo/index.html').is_file():p.error('First run npm run build:demo.')
    # Check conflict before any initialization; never stop a conflicting service.
    with socket.socket() as check:
        try:check.bind((args.host,args.port))
        except OSError:p.error('Requested course port is in use; choose another one.')
    for name in list(os.environ):
        if name.startswith('CARELINK_'):del os.environ[name]
    from backend.coursework_demo import prepare,paths,simulator_headers,simulated_payload,install_demo_adapter
    if args.profile and not re.fullmatch(r'[A-Za-z0-9_-]{1,32}',args.profile):p.error('Profile must be a short simple name.')
    root=ROOT/('.coursework/backend-'+args.profile if args.profile else '.coursework/backend')
    os.environ.update(paths(root))
    os.environ.update(prepare(root,initialize=args.initialize,san_ip=args.lan_ip))
    origins=[f'https://localhost:{args.port}',f'https://127.0.0.1:{args.port}',f'https://10.0.2.2:{args.port}']
    if args.lan_ip:origins.append(f'https://{args.lan_ip}:{args.port}')
    os.environ['CARELINK_WEB_ORIGINS']=','.join(origins)
    from backend import app as core
    app=install_demo_adapter(core,ROOT/'build-demo')
    import httpx,uvicorn
    stopped=threading.Event()
    def simulate():
        context=ssl.create_default_context(cafile=str(root/'tls/root.crt'))
        target=f'https://{args.host}:{args.port}'
        with httpx.Client(verify=context,trust_env=False,timeout=5) as client:
            tick=0
            while not stopped.wait(2):
                try:
                    body=json.dumps(simulated_payload(tick),separators=(',',':')).encode();response=client.post(target+'/sensor-data',content=body,headers=simulator_headers(root,body))
                    if response.status_code==200:tick+=1
                    else:print('SIMULATOR HTTP '+str(response.status_code),flush=True)
                except httpx.HTTPError:pass  # startup/offline; never invent successful receipt
    thread=threading.Thread(target=simulate,daemon=True);thread.start()
    print('COURSEWORK SIMULATED DATA ONLY. Web/API: '+origins[0],flush=True)
    print('Public demo CA: '+str(root/'tls/root.crt'),flush=True)
    print('Android emulator API: '+origins[2]+' (install demo CA first). Ctrl+C stops only this course service.',flush=True)
    try:uvicorn.run(app,host=args.host,port=args.port,ssl_keyfile=str(root/'tls/server.key'),ssl_certfile=str(root/'tls/server.crt'),proxy_headers=False,access_log=False,log_level='warning')
    finally:stopped.set();thread.join(timeout=7)

if __name__=='__main__':
    try:main()
    except (Exception,KeyboardInterrupt):print('Course backend stopped or refused startup. Preserve .coursework/backend; no real services changed.',file=sys.stderr);sys.exit(1)
