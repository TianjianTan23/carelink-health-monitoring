#!/usr/bin/env python3
"""Initialize an explicitly NEW hardware acceptance environment, or start it.
No hardware, migration, recovery, simulator or production defaults are used.
"""
from pathlib import Path
import argparse,getpass,json,os,socket,sys,warnings,secrets
from contextlib import ExitStack
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))

def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='action',required=True)
    init=sub.add_parser('init');init.add_argument('--directory',type=Path,default=ROOT/'.coursework/hardware-gateway');init.add_argument('--lan-ip',required=True);init.add_argument('--hostname');init.add_argument('--device-id',default='esp32-integration-01');init.add_argument('--port',type=int,default=19443);init.add_argument('--confirm-new-identity',required=True,action='store_true')
    for name in ['check','run']:
        cmd=sub.add_parser(name);cmd.add_argument('--config',type=Path,default=ROOT/'.coursework/hardware-gateway/gateway.json')
    address=sub.add_parser('address');address.add_argument('--config',type=Path,default=ROOT/'.coursework/hardware-gateway/gateway.json');address.add_argument('--lan-ip',required=True);address.add_argument('--confirm-service-stopped',action='store_true',required=True)
    prepare=sub.add_parser('prepare');prepare.add_argument('--directory',type=Path,default=ROOT/'.coursework/hardware-gateway');prepare.add_argument('--device-id',default='esp32-integration-01');prepare.add_argument('--port',type=int,default=19443);prepare.add_argument('--confirm-new-identity',required=True,action='store_true')
    account=sub.add_parser('accounts');account.add_argument('--config',type=Path,default=ROOT/'.coursework/hardware-gateway/gateway.json')
    args=p.parse_args()
    from backend.local_gateway import create_new,load,app_from_config,readdress
    if args.action=='prepare':
        from backend.web_auth import hash_password_for_migration
        accounts={name:{'password_hash':hash_password_for_migration(secrets.token_urlsafe(32)),'role':role,'mode':mode,'patient_ids':['ttj'],'needs_password_rotation':0} for name,role,mode in [('ttj','patient','basic'),('wyn','clinician','pro')]}
        config=create_new(args.directory,accounts,device_id=args.device_id,port=args.port)
        config['accounts_pending']=True
        from backend.local_gateway import private_file
        pending=args.directory/'account-preparation.json';private_file(pending,(json.dumps(config,indent=2)+'\n').encode());os.replace(pending,args.directory/'gateway.json')
        print('Offline hardware environment prepared with NEW device identity; not started.')
        print('Tomorrow: run accounts, update address, fill Wi-Fi locally, then check/start. No password was printed or made usable by default.')
        return
    if args.action in {'init','accounts'}:
        if not sys.stdin.isatty() or not sys.stderr.isatty():p.error('Use a local terminal for hidden account password entry.')
        from backend.web_auth import hash_password_for_migration
        accounts={}
        for username,role,mode in [('ttj','patient','basic'),('wyn','clinician','pro')]:
            with warnings.catch_warnings():
                warnings.simplefilter('error',getpass.GetPassWarning)
                first=getpass.getpass('Password for '+username+' in NEW acceptance DB (hidden; existing password may be reused): ')
                second=getpass.getpass('Repeat (hidden): ')
            if first!=second:raise ValueError('Password confirmation differs')
            if not 1<=len(first.encode())<=1024:raise ValueError('Password is empty or too long')
            accounts[username]={'password_hash':hash_password_for_migration(first),'role':role,'mode':mode,'patient_ids':['ttj'],'needs_password_rotation':0}
        if args.action=='accounts':
            config=load(args.config,allow_pending=True)
            if not config.get('accounts_pending'):raise ValueError('Accounts already prepared; no automatic password rotation')
            from backend.local_gateway import environment,private_file
            from backend.web_auth import AuthStore
            with environment(config['environment']):
                store=AuthStore(config['environment']['CARELINK_AUTH_DATABASE_PATH'])
                for name,value in accounts.items():store.replace_password_hash(name,value['password_hash'])
            config['accounts_pending']=False;ready=args.config.with_name('account-ready-'+secrets.token_hex(4)+'.json')
            private_file(ready,(json.dumps(config,indent=2)+'\n').encode());os.replace(ready,args.config)
            print('Passwords set only in NEW local acceptance DB; original account databases unchanged. Gateway not started.');return
        create_new(args.directory,accounts,device_id=args.device_id,lan_ip=args.lan_ip,hostname=args.hostname,port=args.port)
        print('New acceptance environment ready: '+str(args.directory/'gateway.json'))
        print('Original account databases, device keys and replay history were not accessed or changed. No hardware flashed.')
        return
    if args.action=='address':
        readdress(args.config,args.lan_ip);print('Address/leaf certificate updated; CA, credentials and replay history preserved. Gateway not started.');return
    config=load(args.config)
    if args.action=='check':
        # Only approved config/storage is checked; this command never initializes missing state.
        app_from_config(config);print('PASS: existing data/auth/control paths and certificate identity; no simulator.');return
    # Only loopback and the explicitly chosen LAN interface; no public wildcard.
    # Loopback also supports Android emulator's 10.0.2.2 host alias.
    addresses=list(dict.fromkeys(['127.0.0.1',config['host']]))
    with ExitStack() as stack:
        listeners=[]
        for address in addresses:
            sock=stack.enter_context(socket.socket())
            sock.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
            try:sock.bind((address,config['port']));sock.listen(128);sock.setblocking(False)
            except OSError:raise ValueError('Required interface unavailable or port in use; nothing stopped')
            listeners.append(sock)
        import uvicorn
        app=app_from_config(config)
        from backend.device_diagnostics import configure
        configure()
        print('Hardware gateway, no automatic simulation: https://'+config['host']+':'+str(config['port']),flush=True)
        print('Mac: https://localhost:'+str(config['port'])+'; emulator: https://10.0.2.2:'+str(config['port']),flush=True)
        server=uvicorn.Server(uvicorn.Config(app,host=config['host'],port=config['port'],ssl_certfile=config['tls']['certfile'],ssl_keyfile=config['tls']['keyfile'],proxy_headers=False,access_log=False,log_level='warning'))
        server.run(sockets=listeners)


if __name__=='__main__':
    try:main()
    except (Exception,KeyboardInterrupt) as error:
        print('Gateway operation refused/stopped: '+(str(error) if type(error) is ValueError else type(error).__name__)+'. Preserve files; no automatic repair/migration/reset.',file=sys.stderr);sys.exit(1)
