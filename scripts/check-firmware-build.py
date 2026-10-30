#!/usr/bin/env python3
"""Compile restored public firmware with newly generated NON-HARDWARE headers.
Never opens a serial port, uploads, or reads the real firmware secrets/CA.
"""
from pathlib import Path
import argparse,json,os,secrets,shutil,subprocess,sys,tempfile
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence-dir',type=Path,default=ROOT/'.coursework/integration-20261030')
    evidence=parser.parse_args().evidence_dir;evidence.mkdir(parents=True,exist_ok=True)
    root=Path(tempfile.mkdtemp(prefix='firmware-build-',dir=evidence));root.chmod(0o700)
    from backend.local_gateway import make_tls
    make_tls(root)
    sketch=root/'elder_sensors';sketch.mkdir()
    for name in ['elder_sensors.ino','device_signing.h','upload_diagnostics.h']:shutil.copyfile(ROOT/'firmware/elder_sensors'/name,sketch/name)
    (sketch/'secrets.h').write_text('#pragma once\nconst char* WIFI_SSID="COMPILE_ONLY_NO_NETWORK";\nconst char* WIFI_PASSWORD="COMPILE_ONLY";\nconst char* SERVER_URL="https://localhost:19443/sensor-data";\n')
    (sketch/'device_auth.h').write_text('#pragma once\nstatic const char DEVICE_AUTH_ID[]="compile-fixture";\nstatic const char DEVICE_API_KEY[]="'+secrets.token_urlsafe(32)+'";\nstatic const char DEVICE_HMAC_KEY_HEX[]="'+secrets.token_hex(32)+'";\n')
    (sketch/'gateway_ca.h').write_text('#pragma once\nstatic const char GATEWAY_ROOT_CA[]=R"CA(\n'+(root/'tls/root.crt').read_text()+')CA";\n')
    for name in ['secrets.h','device_auth.h','gateway_ca.h']:(sketch/name).chmod(0o600)
    command=['arduino-cli','compile','--fqbn','esp32:esp32:esp32:DebugLevel=none','--build-path',str(root/'build'),str(sketch)]
    result=subprocess.run(command,cwd=ROOT)
    (evidence/'firmware-build-result.json').write_text(json.dumps({'command':command,'exit_code':result.returncode,'input':'public restored firmware plus generated test-only headers','hardware':'NOT CONNECTED','flash':'NOT PERFORMED'},indent=2)+'\n')
    return result.returncode
if __name__=='__main__':raise SystemExit(main())
