#!/usr/bin/env python3
"""Read-only readiness checks; never flash, provision, restart, or switch data."""
from contextlib import closing
import argparse
import ast
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import socket
import sqlite3
import ssl
import stat
import subprocess
from datetime import datetime, timezone
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def valid_target(value, ip):
    try:
        url = urllib.parse.urlsplit(value)
        return (url.scheme == 'https' and url.hostname == ip and url.port == 9443
                and url.path == '/sensor-data' and not url.query and not url.fragment
                and url.username is None and url.password is None)
    except ValueError:
        return False


def credentials_match(text, registry):
    values = {}
    for name in ('DEVICE_AUTH_ID','DEVICE_API_KEY','DEVICE_HMAC_KEY_HEX'):
        matches = re.findall(r'\b' + name + r'\[\]\s*=\s*"([^"\r\n]+)"\s*;', text)
        if len(matches) != 1:
            return False
        values[name] = matches[0]
    device, api, key = (values[name] for name in ('DEVICE_AUTH_ID','DEVICE_API_KEY','DEVICE_HMAC_KEY_HEX'))
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}',device) or not re.fullmatch(r'[A-Za-z0-9_-]{32,128}',api) or not re.fullmatch(r'[0-9a-f]{64}',key):
        return False
    record = registry.get('devices',{}).get(device,{})
    return (registry.get('version') == 1 and record.get('enabled') is True
            and hmac.compare_digest(hashlib.sha256(api.encode('ascii')).hexdigest(), record.get('api_key_sha256',''))
            and hmac.compare_digest(key, record.get('hmac_key_hex','')))


def isolated_paths(candidate, legacy):
    return candidate.resolve() != legacy.resolve() and not (
        candidate.exists() and legacy.exists() and os.path.samefile(candidate,legacy))


def main():
    global ROOT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config-root',required=True,type=Path,help='Explicit absolute root; no production default')
    parser.add_argument('--confirm-approved-read-only-inspection',required=True,action='store_true')
    parser.add_argument('--network',action='store_true',help='Also make health/read-only and rejected unsigned requests.')
    parser.add_argument('--report',type=Path)
    args = parser.parse_args()
    if not args.config_root.is_absolute():parser.error('Absolute config root required')
    if args.network:parser.error('Network probes require a separate approved plan; disabled in this checker')
    ROOT=args.config_root
    checks = {}

    def check(name, function):
        try: checks[name] = {'passed':bool(function())}
        except Exception as error:
            # Never include exception text that could contain private file data.
            checks[name] = {'passed':False,'errorType':type(error).__name__}

    gateway = json.loads((ROOT/'.tls/gateway.json').read_text())
    ip, hostname = gateway['lanIP'], gateway['hostname']
    private = ROOT/'.secrets/stage3'
    candidate, legacy = private/'authenticated-candidate.db', ROOT/'backend/carelink.db'
    registry = ROOT/'.secrets/device-auth.json'
    header = ROOT/'firmware/elder_sensors/device_auth.h'
    secrets_file = ROOT/'firmware/elder_sensors/secrets.h'
    source = (ROOT/'firmware/elder_sensors/elder_sensors.ino').read_text()
    check('gatewayIPStillAssigned',lambda:bool(re.search(r'inet '+re.escape(ip)+r'\s',subprocess.check_output(['/sbin/ifconfig'],text=True))))
    check('deviceCredentialsMatchRegistry',lambda:credentials_match(header.read_text(),json.loads(registry.read_text())))
    check('privateFilePermissions',lambda:all(stat.S_IMODE(p.stat().st_mode)==0o600 for p in [registry,header,secrets_file,ROOT/'.tls/gateway.key']))
    def ignored_files():
        paths=[str(p) for p in [registry,header,secrets_file,ROOT/'.secrets/device-nonces.sqlite3']]
        result=subprocess.run(['git','check-ignore',*paths],cwd=ROOT,capture_output=True,text=True)
        return result.returncode==0 and set(result.stdout.splitlines())==set(paths)
    check('privateFilesGitIgnored',ignored_files)
    check('firmwareUsesCandidateHTTPS',lambda:valid_target(re.search(r'\bSERVER_URL\s*=\s*"([^"\r\n]+)"',secrets_file.read_text()).group(1),ip))
    check('CAHeaderMatchesExistingRoot',lambda:(ROOT/'.tls/carelink-root-ca.pem').read_text() in (ROOT/'firmware/elder_sensors/gateway_ca.h').read_text())
    check('TLSVerificationConfigured',lambda:'client.setCACert(GATEWAY_ROOT_CA)' in source and not re.search(r'\.setInsecure\s*\(',source))
    check('candidateDatabaseIsolated',lambda:isolated_paths(candidate,legacy))
    check('legacyRollbackSourceParses',lambda:bool(ast.parse((private/'legacy-app.py').read_text())))
    check('originalWiFiConfigurationBackupExists',lambda:(private/'original-secrets.h').is_file())
    check('certificateKeyPairMatches',lambda:ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER).load_cert_chain(ROOT/'.tls/gateway.pem',ROOT/'.tls/gateway.key') is None)
    for label,flag,value in [('certificateIP','-verify_ip',ip),('certificateHostname','-verify_hostname',hostname)]:
        check(label,lambda flag=flag,value=value:subprocess.run(['openssl','verify','-CAfile',str(ROOT/'.tls/carelink-root-ca.pem'),flag,value,str(ROOT/'.tls/gateway.pem')],capture_output=True).returncode==0)
    check('certificateHasAtLeastSevenDays',lambda:subprocess.run(['openssl','x509','-in',str(ROOT/'.tls/gateway.pem'),'-noout','-checkend','604800'],capture_output=True).returncode==0)
    check('ledgerInitializationMarkerExists',lambda:(ROOT/'.secrets/device-nonces.sqlite3.initialized').is_file())
    metadata = {}
    for label,path in [('legacy',legacy),('candidate',candidate)]:
        try:
            with closing(sqlite3.connect(f'file:{path}?mode=ro',uri=True)) as db:
                count = db.execute('SELECT count(*) FROM readings').fetchone()[0]
                row = db.execute('SELECT device_id,created_at FROM readings ORDER BY id DESC LIMIT 1').fetchone()
            metadata[label] = {'rows':count,'lastDevice':row[0] if row else None,'lastReceivedAt':row[1] if row else None}
        except sqlite3.Error:
            metadata[label] = {'readable':False}
    check('databasesReadable',lambda:all('rows' in value for value in metadata.values()))
    static_names=set(checks)
    if args.network:
        context = ssl.create_default_context(cafile=str(ROOT/'.tls/carelink-root-ca.pem'))
        client = urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPSHandler(context=context))

        def status(url, body=None):
            try:
                request = urllib.request.Request(url,data=body,headers={'Content-Type':'application/json'} if body is not None else {})
                with client.open(request,timeout=4) as response: return response.status
            except urllib.error.HTTPError as error: return error.code

        check('productionHTTPSHealthy',lambda:status(f'https://{ip}:8443/health')==200)
        check('candidateHTTPSHealthy',lambda:status(f'https://{ip}:9443/health')==200)
        check('candidateRejectsUnsignedPost',lambda:status(f'https://{ip}:9443/sensor-data',b'{}')==401)
        check('previewHostnameHealthy',lambda:status(f'https://{hostname}:8444/health')==200)
        check('previewRejectsIPCookieCollision',lambda:status(f'https://{ip}:8444/health')==400)
        check('upstreamLoopbackHealthy',lambda:status('http://127.0.0.1:8000/health')==200)

        def rejected_tls(tls_context, name):
            try:
                with socket.create_connection((ip,9443),timeout=4) as connection:
                    with tls_context.wrap_socket(connection,server_hostname=name):
                        return False
            except ssl.SSLCertVerificationError:
                return True
        check('wrongServerIdentityRejected',lambda:rejected_tls(context,'wrong-gateway.invalid'))
        check('untrustedCARejected',lambda:rejected_tls(ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT),ip))

        def lan_blocked():
            try:
                with socket.create_connection((ip,8000),timeout=3): return False
            except OSError: return True
        check('legacyLANConnectionBlockedFromMac',lan_blocked)
    all_ready=all(item['passed'] for item in checks.values())
    result = {'checkedAtUTC':datetime.now(timezone.utc).isoformat(),'checks':checks,
        'offlineReady':all(checks[name]['passed'] for name in static_names),
        'liveEndpointsReady':all(checks[name]['passed'] for name in set(checks)-static_names) if args.network else None,
        'databaseMetadata':metadata,
        'hardwareAcceptance':'pending','productionCutoverAllowed':False,
        'scope':'Read-only checks; no valid sensor samples, hardware actions or service control. Live PF administrator state is not re-read.'}
    if args.report:
        args.report.parent.mkdir(parents=True,exist_ok=True)
        args.report.write_text(json.dumps(result,indent=2)+'\n')
    print('Offline configuration: '+('PASS' if result['offlineReady'] else 'NEEDS ATTENTION'))
    if args.network: print('Live endpoints: '+('PASS' if result['liveEndpointsReady'] else 'NEEDS ATTENTION'))
    for name,item in checks.items(): print(('PASS ' if item['passed'] else 'FAIL ')+name)
    print('Hardware acceptance remains pending. Production cutover is not permitted by this check.')
    raise SystemExit(0 if all_ready else 1)


if __name__=='__main__': main()
