"""Explicit, isolated course demonstration. Never loads a production configuration.

The only automatic producer is coursework-simulator; returned readings are marked
mock even though they traverse the actual TLS/HMAC, model and SQLite pipeline.
"""
from pathlib import Path
import hashlib,hmac,ipaddress,json,os,secrets,subprocess,time

DEVICE='coursework-simulator'
DEMO_PASSWORD='coursework-demo'  # Public fake demo credential, not a real account password.

def private_json(path,value):
    path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    with path.open('x') as f:json.dump(value,f)
    path.chmod(0o600)

def paths(root):
    root=Path(root).absolute()
    return {'CARELINK_LEDGER_CONTROL_ROOT':str(root/'auth/control'),'CARELINK_DEVICE_NONCE_DB':str(root/'auth/nonces.sqlite3'),'CARELINK_DEVICE_REGISTRY':str(root/'auth/devices.json'),'CARELINK_DATABASE_PATH':str(root/'data/readings.db'),'CARELINK_AUTH_DATABASE_PATH':str(root/'accounts/web.sqlite3')}

def prepare(root, *, initialize=False, san_ip=None):
    from .nonce_ledger import initialize_new_ledger,AUTHORIZATION,NonceStore
    from .ledger_control import Controller,sql,history,fingerprint
    from .web_auth import AuthStore,hash_password
    root=Path(root).absolute()
    if san_ip is not None:ipaddress.ip_address(san_ip)
    if not root.exists():
        if not initialize:raise RuntimeError('New course environment requires --initialize; no existing data is reset.')
        root.mkdir(mode=0o700,parents=True)
        for name in ['auth','accounts','data','tls']: (root/name).mkdir(mode=0o700)
        nonce=root/'auth/nonces.sqlite3';initialize_new_ledger(nonce,authorization=AUTHORIZATION)
        NonceStore(nonce).reserve('coursework-bootstrap',secrets.token_hex(16),int(time.time()),int(time.time()))
        with sql(nonce) as db:checkpoint=fingerprint(history(db))
        info=nonce.stat();inventory=root/'auth/inventory.json'
        private_json(inventory,{'source':str(nonce),'device':info.st_dev,'inode':info.st_ino,'checkpoint':checkpoint,'all_writers_controlled':True,'legacy_writers_stopped':True,'expires_at':int(time.time())+3600,'review_reference':'new synthetic coursework environment; no real hardware'})
        c=Controller.enroll(root/'auth/control',nonce,inventory);c.resume()
        key=secrets.token_bytes(32);api=secrets.token_urlsafe(32)
        private_json(root/'auth/devices.json',{'version':1,'devices':{DEVICE:{'enabled':True,'api_key_sha256':hashlib.sha256(api.encode()).hexdigest(),'hmac_key_hex':key.hex()}}})
        private_json(root/'auth/simulator.json',{'api_key':api,'hmac_key_hex':key.hex()})
        auth=AuthStore(root/'accounts/web.sqlite3');auth.initialize({
          'demo-patient':{'password_hash':hash_password(DEMO_PASSWORD),'role':'patient','mode':'basic','patient_ids':['ttj'],'needs_password_rotation':0},
          'demo-clinician':{'password_hash':hash_password(DEMO_PASSWORD),'role':'clinician','mode':'pro','patient_ids':['ttj'],'needs_password_rotation':0}})
        def openssl(*args):subprocess.run(['openssl',*map(str,args)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        tls=root/'tls';old=os.umask(0o077)
        try:
            openssl('req','-x509','-newkey','rsa:2048','-nodes','-days','365','-subj','/CN=CareLink Coursework Demo Root','-addext','basicConstraints=critical,CA:TRUE','-addext','keyUsage=critical,keyCertSign,cRLSign','-keyout',tls/'root.key','-out',tls/'root.crt')
            openssl('req','-new','-newkey','rsa:2048','-nodes','-subj','/CN=CareLink Coursework Demo','-keyout',tls/'server.key','-out',tls/'server.csr')
            sans='DNS:localhost,IP:127.0.0.1,IP:10.0.2.2'+(',IP:'+san_ip if san_ip else '')
            (tls/'extensions').write_text('subjectAltName='+sans+'\nbasicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\nsubjectKeyIdentifier=hash\nauthorityKeyIdentifier=keyid,issuer\n')
            openssl('x509','-req','-in',tls/'server.csr','-CA',tls/'root.crt','-CAkey',tls/'root.key','-CAcreateserial','-days','90','-extfile',tls/'extensions','-out',tls/'server.crt')
            private_json(root/'demo.json',{'schema':1,'source':'SIMULATED COURSEWORK DATA','san_ip':san_ip})
        finally:os.umask(old)
    # Existing or partial environments never get auto-repaired/reseeded.
    required=['demo.json','auth/control/state.json','auth/nonces.sqlite3','auth/nonces.sqlite3.initialized','auth/devices.json','auth/simulator.json','accounts/web.sqlite3','accounts/web.sqlite3.initialized','tls/root.crt','tls/server.crt','tls/server.key']
    if any(not (root/name).is_file() for name in required):raise RuntimeError('Incomplete demo environment; preserve it, do not auto-reinitialize.')
    manifest=json.loads((root/'demo.json').read_text())
    if manifest.get('schema')!=1 or manifest.get('san_ip')!=san_ip:raise RuntimeError('Demo certificate SAN setting differs. Use its original setting or a separately reviewed new demo directory.')
    return {'CARELINK_LEDGER_CONTROL_ROOT':str(root/'auth/control'),'CARELINK_DEVICE_NONCE_DB':str(root/'auth/nonces.sqlite3'),'CARELINK_DEVICE_REGISTRY':str(root/'auth/devices.json'),'CARELINK_DATABASE_PATH':str(root/'data/readings.db'),'CARELINK_AUTH_DATABASE_PATH':str(root/'accounts/web.sqlite3')}

def simulator_headers(root,body):
    credentials=json.loads((Path(root)/'auth/simulator.json').read_text());timestamp=str(int(time.time()));nonce=secrets.token_hex(16)
    canonical='\n'.join(['CARELINK-HMAC-SHA256-V1','POST','/sensor-data',DEVICE,timestamp,nonce,hashlib.sha256(body).hexdigest()]).encode('ascii')
    return {'Content-Type':'application/json','X-CareLink-Device-Id':DEVICE,'X-CareLink-Api-Key':credentials['api_key'],'X-CareLink-Timestamp':timestamp,'X-CareLink-Nonce':nonce,'X-CareLink-Signature':hmac.new(bytes.fromhex(credentials['hmac_key_hex']),canonical,hashlib.sha256).hexdigest()}

def simulated_payload(tick):
    phase=(tick//8)%4
    return {'device_id':DEVICE,'data_source':'coursework-simulator','heart_rate_bpm':None if phase==3 else 78+tick%6 if phase==0 else 114 if phase==1 else 92,'heart_rate_ok':phase!=3,'object_temp_c':36.5 if phase!=1 else 38.4,'ambient_temp_c':24.5,'mlx90614_ok':True,'mpu6050_ok':True,'fall_detected':phase==2,'accel_x_g':0.02,'accel_y_g':0.01,'accel_z_g':1.0}

def install_demo_adapter(core,build):
    # Local process adapter, not a change to production serialization or data.
    os.environ['CARELINK_DATA_ORIGIN']='simulation'
    original=core._reading_from_row
    def reading(row):
        value=original(row)
        if value.get('deviceId')==DEVICE:value['source']='mock'
        return value
    core._reading_from_row=reading
    from fastapi.staticfiles import StaticFiles
    core.app.router.routes[:]=[route for route in core.app.router.routes if getattr(route,'name',None)!='web']
    core.app.mount('/',StaticFiles(directory=build,html=True),name='coursework-web')
    return core.app
