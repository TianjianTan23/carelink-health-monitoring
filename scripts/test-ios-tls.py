#!/usr/bin/env python3
"""Synthetic TLS + native client + actual isolated FastAPI. No real config."""
from contextlib import ExitStack
import json,os,secrets,ssl,subprocess,sys,tempfile
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backend.device_auth_test_support import fixture_device_control, write_registry, signed_headers
import httpx
from backend.web_auth import AuthStore,hash_password
from backend.tls_test_support import TLSProcess

def openssl(*args):
    subprocess.run(['openssl',*map(str,args)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=15)

def main():
    binary=Path(sys.argv[1]).resolve()
    with tempfile.TemporaryDirectory(prefix='carelink-native-tls-') as d:
        root=Path(d);old=os.umask(0o077)
        try:
            openssl('req','-x509','-newkey','rsa:2048','-nodes','-days','2','-subj','/CN=CareLink Synthetic Root','-addext','basicConstraints=critical,CA:TRUE','-addext','keyUsage=critical,keyCertSign,cRLSign','-addext','subjectKeyIdentifier=hash','-keyout',root/'root.key','-out',root/'root.pem')
            openssl('x509','-in',root/'root.pem','-outform','der','-out',root/'root.cer')
            openssl('req','-new','-newkey','rsa:2048','-nodes','-subj','/CN=localhost','-keyout',root/'leaf.key','-out',root/'leaf.csr')
            (root/'extensions').write_text('subjectAltName=DNS:localhost\nbasicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\nsubjectKeyIdentifier=hash\nauthorityKeyIdentifier=keyid,issuer\n')
            openssl('x509','-req','-in',root/'leaf.csr','-CA',root/'root.pem','-CAkey',root/'root.key','-CAcreateserial','-days','1','-extfile',root/'extensions','-out',root/'leaf.pem')
            openssl('x509','-in',root/'leaf.pem','-outform','der','-out',root/'leaf.cer')
            (root/'index').write_text('');(root/'serial').write_text('1000\n');(root/'issued').mkdir()
            (root/'ca.conf').write_text(f'[ ca ]\ndefault_ca=local\n[ local ]\ndatabase={root}/index\nserial={root}/serial\nnew_certs_dir={root}/issued\ncertificate={root}/root.pem\nprivate_key={root}/root.key\ndefault_md=sha256\npolicy=policy\n[ policy ]\ncommonName=supplied\n')
            openssl('ca','-batch','-config',root/'ca.conf','-in',root/'leaf.csr','-startdate','20010101000000Z','-enddate','20020101000000Z','-extfile',root/'extensions','-out',root/'expired.pem')
            openssl('x509','-in',root/'expired.pem','-outform','der','-out',root/'expired.cer')
            openssl('req','-x509','-newkey','rsa:2048','-nodes','-days','1','-subj','/CN=localhost','-addext','subjectAltName=DNS:localhost','-keyout',root/'untrusted.key','-out',root/'untrusted.pem')
            openssl('x509','-in',root/'untrusted.pem','-outform','der','-out',root/'untrusted.cer')
        finally:os.umask(old)
        context=ssl.create_default_context(cafile=str(root/'root.pem'))
        with ExitStack() as stack:
            fixture=TLSProcess(ROOT,'backend.app:app',root/'leaf.key',root/'leaf.pem',context);stack.callback(fixture.close)
            env={k:v for k,v in os.environ.items() if not k.startswith('CARELINK_')}
            env.update(fixture_device_control(root))
            write_registry(root/'devices.json')
            env.update(CARELINK_DATABASE_PATH=str(root/'readings.db'),CARELINK_AUTH_DATABASE_PATH=str(root/'accounts/auth.db'),CARELINK_DEVICE_NONCE_DB=str(root/'auth/nonces.sqlite3'),CARELINK_WEB_ORIGINS=fixture.url,CARELINK_DEVICE_REGISTRY=str(root/'devices.json'),PYTHONDONTWRITEBYTECODE='1')
            password=secrets.token_urlsafe(24)
            with patch.dict(os.environ,env,clear=True):
                auth=AuthStore(root/'accounts/auth.db')
                auth.initialize({'fixture_native':{'password_hash':hash_password(password),'role':'patient','mode':'basic','patient_ids':['ttj'],'needs_password_rotation':0}})
            fixture.start(env)
            body=b'{"device_id":"esp32-test","heart_rate_bpm":null,"heart_rate_ok":false,"object_temp_c":36.5,"mlx90614_ok":true}'
            with httpx.Client(verify=context,trust_env=False,timeout=5) as client:
                assert client.post(fixture.url+'/sensor-data',content=body,headers=signed_headers(body)).status_code==200
            result=subprocess.run([str(binary),str(root),fixture.url,str(ROOT/'shared')],input=password+'\n',text=True,capture_output=True,timeout=90)
            # Native test only prints named status checks; never pass credentials
            # through arguments, a file, a shell command, or diagnostic output.
            if result.returncode:
                print('FAIL: Native TLS fixture; no credentials emitted.')
                # Keep only explicit FAIL labels from the synthetic executable.
                for line in result.stderr.splitlines():
                    if 'Fatal error: FAIL:' in line:print(line.split('Fatal error: ',1)[1])
                return 1
            print(result.stdout,end='')
            return 0

if __name__=='__main__':raise SystemExit(main())
