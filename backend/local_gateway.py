"""Unified local gateway preparation, using the existing security/data modules.

No simulator, no automatic adoption/migration of any existing database or ledger.
New-environment creation always uses new device keys in a distinct identity domain.
"""
from contextlib import contextmanager
import hashlib,ipaddress,json,os,re,secrets,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
ENV_NAMES=('CARELINK_DATABASE_PATH','CARELINK_AUTH_DATABASE_PATH','CARELINK_DEVICE_REGISTRY','CARELINK_DEVICE_NONCE_DB','CARELINK_LEDGER_CONTROL_ROOT','CARELINK_WEB_ORIGINS','CARELINK_DATA_ORIGIN')

@contextmanager
def environment(values):
    previous={name:os.environ.get(name) for name in ENV_NAMES}
    os.environ.update(values)
    try:yield
    finally:
        for name,value in previous.items():
            if value is None:os.environ.pop(name,None)
            else:os.environ[name]=value

def private_file(path,data):
    path=Path(path);path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as stream:stream.write(data);stream.flush();os.fsync(stream.fileno())

def make_tls(root,lan_ip=None,hostname=None):
    tls=root/'tls';tls.mkdir(mode=0o700)
    def openssl(*args):subprocess.run(['openssl',*map(str,args)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    old=os.umask(0o077)
    try:
        openssl('req','-x509','-newkey','rsa:2048','-nodes','-days','365','-subj','/CN=CareLink Local Integration Root','-addext','basicConstraints=critical,CA:TRUE','-addext','keyUsage=critical,keyCertSign,cRLSign','-addext','subjectKeyIdentifier=hash','-keyout',tls/'root.key','-out',tls/'root.crt')
        openssl('req','-new','-newkey','rsa:2048','-nodes','-subj','/CN=CareLink Mac Gateway','-keyout',tls/'server.key','-out',tls/'server.csr')
        names=['DNS:localhost','IP:127.0.0.1','IP:10.0.2.2']
        if lan_ip:names.append('IP:'+str(ipaddress.ip_address(lan_ip)))
        if hostname:
            if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.-]{0,252}',hostname):raise ValueError('Invalid hostname')
            names.append('DNS:'+hostname)
        private_file(tls/'extensions',('subjectAltName='+','.join(names)+'\nbasicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\nsubjectKeyIdentifier=hash\nauthorityKeyIdentifier=keyid,issuer\n').encode())
        openssl('x509','-req','-in',tls/'server.csr','-CA',tls/'root.crt','-CAkey',tls/'root.key','-CAcreateserial','-days','90','-extfile',tls/'extensions','-out',tls/'server.crt')
    finally:os.umask(old)

def create_new(root,accounts,*,device_id,lan_ip=None,hostname=None,port=19443):
    from .nonce_ledger import initialize_new_ledger,AUTHORIZATION,NonceStore
    from .ledger_control import Controller,sql,history,fingerprint
    from .web_auth import AuthStore
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}',device_id):raise ValueError('Invalid device ID')
    if port in {8000,8443,9443,18443,18444,18445,18500} or not 1024<=port<=65535:raise ValueError('Use a separate gateway port')
    if lan_ip:ipaddress.ip_address(lan_ip)
    root=Path(root).absolute();root.mkdir(mode=0o700,parents=True,exist_ok=False)
    private_file(root/'.initializing',b'Explicit new gateway identity; preserve partial state on failure.\n')
    for name in ['data','accounts','device']: (root/name).mkdir(mode=0o700)
    env={'CARELINK_DATABASE_PATH':str(root/'data/readings.sqlite3'),'CARELINK_AUTH_DATABASE_PATH':str(root/'accounts/web.sqlite3'),
         'CARELINK_DEVICE_REGISTRY':str(root/'device/registry.json'),'CARELINK_DEVICE_NONCE_DB':str(root/'device/nonces.sqlite3'),
         'CARELINK_LEDGER_CONTROL_ROOT':str(root/'device/control'),'CARELINK_DATA_ORIGIN':'hardware'}
    origins=[f'https://localhost:{port}',f'https://127.0.0.1:{port}',f'https://10.0.2.2:{port}']
    if lan_ip:origins.append(f'https://{lan_ip}:{port}')
    if hostname:origins.append(f'https://{hostname}:{port}')
    env['CARELINK_WEB_ORIGINS']=','.join(origins)
    nonce=Path(env['CARELINK_DEVICE_NONCE_DB']);initialize_new_ledger(nonce,authorization=AUTHORIZATION)
    NonceStore(nonce).reserve('environment-bootstrap',secrets.token_hex(16),int(time.time()),int(time.time()))
    with sql(nonce) as db:checkpoint=fingerprint(history(db))
    info=nonce.stat();inventory=root/'device/new-install-inventory.json'
    private_file(inventory,json.dumps({'source':str(nonce),'device':info.st_dev,'inode':info.st_ino,'checkpoint':checkpoint,'all_writers_controlled':True,'legacy_writers_stopped':True,'expires_at':int(time.time())+3600,'review_reference':'EXPLICIT NEW PRIVATE ENVIRONMENT, NEW KEYS; not production recovery'}).encode())
    controller=Controller.enroll(Path(env['CARELINK_LEDGER_CONTROL_ROOT']),nonce,inventory);controller.resume()
    api=secrets.token_urlsafe(32);key=secrets.token_hex(32)
    private_file(env['CARELINK_DEVICE_REGISTRY'],json.dumps({'version':1,'devices':{device_id:{'enabled':True,'api_key_sha256':hashlib.sha256(api.encode()).hexdigest(),'hmac_key_hex':key}}}).encode())
    with environment(env):
        AuthStore(env['CARELINK_AUTH_DATABASE_PATH']).initialize(accounts)
        from . import app as core
        previous=core.DATABASE_PATH
        try:core.DATABASE_PATH=Path(env['CARELINK_DATABASE_PATH']);core.initialize_database()
        finally:core.DATABASE_PATH=previous
    make_tls(root,lan_ip,hostname)
    config={'schema':1,'purpose':'new-local-hardware-acceptance','accounts_pending':False,'mode':'hardware','host':lan_ip or '127.0.0.1','port':port,'environment':env,
            'hostname':hostname,'tls':{'certfile':str(root/'tls/server.crt'),'keyfile':str(root/'tls/server.key'),'cafile':str(root/'tls/root.crt')},'web_dir':str(ROOT/'build')}
    # Export a new, isolated sketch; existing user/production headers are untouched.
    sketch=root/'firmware/elder_sensors';sketch.mkdir(mode=0o700,parents=True)
    for name in ['elder_sensors.ino','device_signing.h','upload_diagnostics.h']:
        private_file(sketch/name,(ROOT/'firmware/elder_sensors'/name).read_bytes())
    private_file(sketch/'device_auth.h',('#pragma once\n// PRIVATE new local acceptance identity; never commit.\nstatic const char DEVICE_AUTH_ID[] = "'+device_id+'";\nstatic const char DEVICE_API_KEY[] = "'+api+'";\nstatic const char DEVICE_HMAC_KEY_HEX[] = "'+key+'";\n').encode())
    private_file(sketch/'gateway_ca.h',('#pragma once\nstatic const char GATEWAY_ROOT_CA[] = R"CA(\n'+(root/'tls/root.crt').read_text()+')CA";\n').encode())
    target=f'https://{lan_ip or "YOUR_MAC_LAN_IP"}:{port}/sensor-data'
    private_file(sketch/'gateway_endpoint.h',('#pragma once\nconst char *SERVER_URL="'+target+'";\n').encode())
    private_file(sketch/'secrets.h',b'#pragma once\n#include "gateway_endpoint.h"\n// Fill Wi-Fi locally; never commit.\nconst char *WIFI_SSID="YOUR_WIFI";\nconst char *WIFI_PASSWORD="YOUR_WIFI_PASSWORD";\n')
    private_file(root/'gateway.json',(json.dumps(config,indent=2)+'\n').encode())
    (root/'.initializing').unlink()
    return config

def load(config_path, *, allow_pending=False):
    path=Path(config_path).absolute();config=json.loads(path.read_text())
    if config.get('schema')!=1 or config.get('purpose')!='new-local-hardware-acceptance' or config.get('mode')!='hardware' or (path.parent/'.initializing').exists():raise ValueError('Incomplete or non-hardware gateway configuration')
    if config.get('accounts_pending') and not allow_pending:raise ValueError('Local account passwords pending; run accounts before starting')
    env=config['environment']
    if set(env)!=set(ENV_NAMES) or env['CARELINK_DATA_ORIGIN']!='hardware':raise ValueError('Explicit existing security/data paths required')
    for name in ENV_NAMES[:5]:
        p=Path(env[name])
        if not p.is_absolute() or not p.exists():raise ValueError('Required existing gateway storage missing')
    for name in ['certfile','keyfile','cafile']:
        if not Path(config['tls'][name]).is_file():raise ValueError('TLS file missing')
    if not Path(config['web_dir'],'index.html').is_file():raise ValueError('Build Web before starting gateway')
    if config['port'] in {8000,8443,9443,18443,18444,18445,18500}:raise ValueError('Existing service ports are not gateway defaults')
    # Public certificate checks; no private key output or verification bypass.
    command=['openssl','verify','-CAfile',config['tls']['cafile'],'-purpose','sslserver']
    try:ipaddress.ip_address(config['host']);command+=['-verify_ip',config['host']]
    except ValueError:command+=['-verify_hostname',config['host']]
    result=subprocess.run(command+[config['tls']['certfile']],capture_output=True)
    if result.returncode:raise ValueError('Certificate identity/chain invalid for bind address')
    return config

def app_from_config(config):
    if config.get('accounts_pending'):raise ValueError('Local account preparation required')
    os.environ.update(config['environment'])
    from .device_auth import preflight_device_authentication
    preflight_device_authentication()
    from . import app as core
    core.DATABASE_PATH=Path(config['environment']['CARELINK_DATABASE_PATH'])
    from fastapi.staticfiles import StaticFiles
    core.app.router.routes[:]=[r for r in core.app.router.routes if getattr(r,'name',None) not in {'web','gateway-web'}]
    core.app.mount('/',StaticFiles(directory=config['web_dir'],html=True),name='gateway-web')
    return core.app


def readdress(config_path,lan_ip):
    """Stopped NEW local environment only. Preserve keys, CA, data and ledgers.

    A partial update stays diagnosable; load() rejects a certificate/config
    mismatch. Wi-Fi secrets are never read: endpoint lives in a separate header.
    """
    ipaddress.ip_address(lan_ip);config=load(config_path,allow_pending=True);root=Path(config_path).absolute().parent
    import socket
    with socket.socket() as sock:
        try:sock.bind(('0.0.0.0',config['port']))
        except OSError:raise ValueError('Stop the local gateway before changing its address')
    backup=root/'address-history'/secrets.token_hex(8);backup.mkdir(mode=0o700,parents=True)
    private_file(backup/'gateway.json',Path(config_path).read_bytes())
    private_file(backup/'server.crt',Path(config['tls']['certfile']).read_bytes())
    endpoint=root/'firmware/elder_sensors/gateway_endpoint.h'
    if not endpoint.is_file():raise ValueError('Expected separate endpoint header missing; preserve existing Wi-Fi secrets')
    private_file(backup/'gateway_endpoint.h',endpoint.read_bytes())
    names=['DNS:localhost','IP:127.0.0.1','IP:10.0.2.2','IP:'+lan_ip]
    if config.get('hostname'):names.append('DNS:'+config['hostname'])
    ext=backup/'extensions';private_file(ext,('subjectAltName='+','.join(names)+'\nbasicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\nsubjectKeyIdentifier=hash\nauthorityKeyIdentifier=keyid,issuer\n').encode())
    def openssl(*args):subprocess.run(['openssl',*map(str,args)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    old=os.umask(0o077)
    try:
        openssl('req','-new','-key',config['tls']['keyfile'],'-subj','/CN=CareLink Mac Gateway','-out',backup/'server.csr')
        openssl('x509','-req','-in',backup/'server.csr','-CA',config['tls']['cafile'],'-CAkey',root/'tls/root.key','-CAserial',root/'tls/root.srl','-days','90','-extfile',ext,'-out',backup/'new.crt')
    finally:os.umask(old)
    # Validate before publishing; don't delete prior diagnostics on any failure.
    result=subprocess.run(['openssl','verify','-CAfile',config['tls']['cafile'],'-verify_ip',lan_ip,str(backup/'new.crt')],capture_output=True)
    if result.returncode:raise ValueError('New certificate did not validate')
    config['host']=lan_ip
    origins=[f'https://localhost:{config["port"]}',f'https://127.0.0.1:{config["port"]}',f'https://10.0.2.2:{config["port"]}',f'https://{lan_ip}:{config["port"]}']
    if config.get('hostname'):origins.append(f'https://{config["hostname"]}:{config["port"]}')
    config['environment']['CARELINK_WEB_ORIGINS']=','.join(origins)
    private_file(backup/'new-endpoint.h',('#pragma once\nconst char *SERVER_URL="https://'+lan_ip+':'+str(config['port'])+'/sensor-data";\n').encode())
    private_file(backup/'new-config.json',(json.dumps(config,indent=2)+'\n').encode())
    os.replace(backup/'new.crt',config['tls']['certfile']);os.replace(backup/'new-endpoint.h',endpoint);os.replace(backup/'new-config.json',config_path)
    return load(config_path,allow_pending=True)
