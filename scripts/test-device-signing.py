#!/usr/bin/env python3
"""Compare the actual firmware signer against independent Python vectors on macOS."""
import hashlib
import hmac
from pathlib import Path
import subprocess
import tempfile
ROOT=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='carelink-signing-') as tmp:
    binary=Path(tmp)/'signing-host'
    subprocess.run(['clang++','-std=c++17','-Wno-deprecated-declarations','-I',str(ROOT/'firmware/elder_sensors'),str(ROOT/'firmware/tests/signing_host.cpp'),'-o',str(binary)],check=True)
    bodies=['{"device_id":"esp32-test","heart_rate_bpm":72}','{ "device_id": "esp32-test", "heart_rate_bpm": 72 }','{"device_id":"esp32-test","note":"温度","heart_rate_bpm":null}','']
    key='01'*32;nonce='000102030405060708090a0b0c0d0e0f';stamp='1793100000'
    for body in bodies:
        output=subprocess.run([str(binary),body,'esp32-test',stamp,nonce,key],capture_output=True,text=True,check=True).stdout
        canonical='\n'.join(['CARELINK-HMAC-SHA256-V1','POST','/sensor-data','esp32-test',stamp,nonce,hashlib.sha256(body.encode()).hexdigest()]).encode()
        assert hmac.compare_digest(output,hmac.new(bytes.fromhex(key),canonical,hashlib.sha256).hexdigest())
    for device,ts,n in [('bad\nID',stamp,nonce),('esp32-test','01793100000',nonce),('esp32-test',stamp,'A'*32)]:
        assert subprocess.run([str(binary),'{}',device,ts,n,key],capture_output=True).returncode!=0
    diagnostics=Path(tmp)/'upload-host'
    subprocess.run(['clang++','-std=c++17','-I',str(ROOT/'firmware/elder_sensors'),str(ROOT/'firmware/tests/upload_host.cpp'),'-o',str(diagnostics)],check=True)
    subprocess.run([str(diagnostics)],check=True)
print('Firmware signing header: four independent vectors agree; three malformed inputs rejected (synthetic keys only).')
