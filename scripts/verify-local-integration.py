#!/usr/bin/env python3
"""Owned HTTPS fixture + real Web API + Android emulator. Never real hardware.

New private temporary gateway, one explicitly simulated signed snapshot, no
background producer. Fixed private test ports are probed; nothing is stopped.
"""
from pathlib import Path
import argparse,hashlib,hmac,json,os,secrets,signal,socket,ssl,subprocess,sys,tempfile,threading,time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import httpx
from backend.local_gateway import create_new
from backend.web_auth import hash_password

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--android',action='store_true');args=parser.parse_args()
    evidence=ROOT/'.coursework/integration-20261030';evidence.mkdir(exist_ok=True)
    for port in [19443,19444]:
        with socket.socket() as s:s.bind(('127.0.0.1',port))
    directory=Path(tempfile.mkdtemp(prefix='software-gateway-',dir=evidence));directory.chmod(0o700)
    account={'password_hash':hash_password('coursework-demo'),'role':'clinician','mode':'pro','patient_ids':['ttj'],'needs_password_rotation':0}
    config=create_new(directory/'gateway',{'demo-clinician':account},device_id='integration-software-fixture')
    (directory/'test-private').mkdir(mode=0o700)
    cert=directory/'bad.crt';key=directory/'bad.key';csr=directory/'bad.csr';ext=directory/'bad.ext'
    def openssl(*items):subprocess.run(['openssl',*map(str,items)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    openssl('req','-new','-newkey','rsa:2048','-nodes','-subj','/CN=localhost','-keyout',key,'-out',csr)
    key.chmod(0o600)
    ext.write_text('subjectAltName=DNS:localhost\nbasicConstraints=critical,CA:FALSE\nkeyUsage=digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\nsubjectKeyIdentifier=hash\nauthorityKeyIdentifier=keyid,issuer\n')
    openssl('x509','-req','-in',csr,'-CA',directory/'gateway/tls/root.crt','-CAkey',directory/'gateway/tls/root.key','-CAcreateserial','-days','1','-extfile',ext,'-out',cert)
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(b'{"unprotectedFixtureOnly":true}')
        def log_message(self,*_):pass
    bad=ThreadingHTTPServer(('127.0.0.1',19444),Handler);ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);ctx.load_cert_chain(cert,key);bad.socket=ctx.wrap_socket(bad.socket,server_side=True)
    bad_thread=threading.Thread(target=bad.serve_forever,daemon=True);bad_thread.start()
    env={k:v for k,v in os.environ.items() if not k.startswith('CARELINK_')};env.update(PYTHONDONTWRITEBYTECODE='1',CARELINK_LOGIN_TEST_LIMIT='100')
    command=[str(ROOT/'.venv/bin/python'),str(ROOT/'scripts/local-gateway.py'),'run','--config',str(directory/'gateway/gateway.json')]
    log=(directory/'server.log').open('w');child=subprocess.Popen(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
    result={'scope':'SOFTWARE FIXTURE ONLY; no physical devices or production state','command':command,'checks':[],'fixture':str(directory)}
    def check(name,value,expected):
        result['checks'].append({'name':name,'actual':value,'expected':expected});assert value==expected,name
    try:
        trust=ssl.create_default_context(cafile=config['tls']['cafile'])
        with httpx.Client(verify=trust,trust_env=False,base_url='https://localhost:19443',timeout=8) as web:
            deadline=time.monotonic()+45
            while time.monotonic()<deadline:
                if child.poll() is not None:raise RuntimeError('Owned gateway startup failed; see private fixture server.log')
                try:
                    if web.get('/health').status_code==200:break
                except httpx.HTTPError:pass
                time.sleep(.2)
            else:raise TimeoutError('Owned gateway not ready')
            check('HTTPS health',web.get('/health').status_code,200)
            h={'Origin':'https://localhost:19443','X-CareLink-CSRF':'1'}
            check('Web login',web.post('/api/login',headers=h,json={'username':'demo-clinician','password':'coursework-demo'}).status_code,200)
            check('Empty hardware-mode database',web.get('/api/patients').json()[0]['reading'],None)
            info=web.get('/api/gateway').json();check('No automatic simulator',info['hasAutomaticSimulator'],False)
            body=json.dumps({'device_id':'integration-software-fixture','patient_id':'patient-01','heart_rate_bpm':81,'object_temp_c':36.8,'fall_detected':False,'spo2_percent':97,'spo2_ok':True,'data_source':'simulation'},separators=(',',':')).encode()
            header=(directory/'gateway/firmware/elder_sensors/device_auth.h').read_text()
            import re
            api=re.search(r'DEVICE_API_KEY\[\] = "([^"]+)"',header).group(1);secret=bytes.fromhex(re.search(r'DEVICE_HMAC_KEY_HEX\[\] = "([^"]+)"',header).group(1))
            stamp=str(int(time.time()));nonce=secrets.token_hex(16);canonical='\n'.join(['CARELINK-HMAC-SHA256-V1','POST','/sensor-data','integration-software-fixture',stamp,nonce,hashlib.sha256(body).hexdigest()]).encode()
            headers={'Content-Type':'application/json','X-CareLink-Device-Id':'integration-software-fixture','X-CareLink-Api-Key':api,'X-CareLink-Timestamp':stamp,'X-CareLink-Nonce':nonce,'X-CareLink-Signature':hmac.new(secret,canonical,hashlib.sha256).hexdigest()}
            posted=web.post('/sensor-data',content=body,headers=headers);check('Signed HTTPS upload',posted.status_code,200)
            check('Replay rejected',web.post('/sensor-data',content=body,headers=headers).status_code,409)
            snapshot=web.get('/api/patients').json()[0]['reading'];check('Simulation stays marked',snapshot['source'],'mock');check('Web matches stored receive time',snapshot['receivedAt'],posted.json()['received_at'])
            old=web.cookies.get('carelink_session');check('Web rotation',web.post('/api/session/rotate',headers=h,json={}).status_code,200)
            check('Old Web session rejected',web.get('/api/session',headers={'Cookie':'carelink_session='+old}).status_code,401)
            old=web.cookies.get('carelink_session');check('Web logout',web.post('/api/logout',headers=h,json={}).status_code,200);check('Logged out Web session rejected',web.get('/api/session',headers={'Cookie':'carelink_session='+old}).status_code,401)
            # Same bad-SAN service is reachable with its valid DNS identity.
            check('Wrong-SAN fixture valid on localhost',web.get('https://localhost:19444/api/session').status_code,200)
            try:web.get('https://127.0.0.1:19444/api/session')
            except httpx.ConnectError:check('Wrong IP identity rejected',True,True)
            else:raise AssertionError('Wrong certificate identity accepted')
        if args.android:
            sdk=ROOT/'.coursework/sdk';adb=[str(sdk/'platform-tools/adb'),'-P','5047','-s','emulator-5580']
            adb_env={**os.environ,'ANDROID_USER_HOME':str(ROOT/'.coursework/android-user')}
            def run_adb(*items):return subprocess.run(adb+list(items),env=adb_env,check=True,capture_output=True,text=True,timeout=90).stdout
            check('Owned emulator ready',run_adb('shell','getprop','sys.boot_completed').strip(),'1')
            run_adb('root');run_adb('wait-for-device')
            root_ca=directory/'gateway/tls/root.crt';digest=subprocess.check_output(['openssl','x509','-in',str(root_ca),'-subject_hash_old','-noout'],text=True).strip();dest='/data/misc/user/0/cacerts-added/'+digest+'.0'
            run_adb('push',str(root_ca),'/data/local/tmp/carelink-integration-root.crt');run_adb('shell','mkdir','-p','/data/misc/user/0/cacerts-added');run_adb('shell','cp','/data/local/tmp/carelink-integration-root.crt',dest);run_adb('shell','chmod','644',dest);run_adb('shell','chmod','755','/data/misc/user/0/cacerts-added');run_adb('shell','chown','system:system',dest);run_adb('shell','restorecon','-R','/data/misc/user/0/cacerts-added')
            build_env={**os.environ,'ANDROID_ADB_SERVER_PORT':'5047','ANDROID_SERIAL':'emulator-5580',
              'CARELINK_ANDROID_TEST_ORIGIN':'https://10.0.2.2:19443','CARELINK_ANDROID_TEST_DEVICE':'integration-software-fixture','CARELINK_ANDROID_TEST_TIMESTAMP':snapshot['receivedAt']}
            with (evidence/'android-build-tests.log').open('w') as out:compiled=subprocess.run(['npm','run','android:apk','--','--device-tests'],cwd=ROOT,env=build_env,stdout=out,stderr=subprocess.STDOUT)
            check('Android release + JVM + emulator',compiled.returncode,0)
        result['status']='PASS';return 0
    except Exception as error:
        result['status']='FAIL';result['error_type']=type(error).__name__;print('Integration failed: '+type(error).__name__+' (no secret values printed).');return 1
    finally:
        child.terminate()
        try:child.wait(timeout=15)
        except subprocess.TimeoutExpired:child.kill();child.wait()
        log.close();bad.shutdown();bad.server_close();bad_thread.join(timeout=5)
        (evidence/('software-integration-android.json' if args.android else 'software-integration-http.json')).write_text(json.dumps(result,indent=2)+'\n')
        print('Software integration '+result.get('status','FAIL')+'; owned fixtures stopped, original services untouched.')
if __name__=='__main__':raise SystemExit(main())
