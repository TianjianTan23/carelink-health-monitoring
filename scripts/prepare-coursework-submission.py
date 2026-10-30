#!/usr/bin/env python3
"""Prepare a source manifest without staging, committing or pushing anything."""
from pathlib import Path
import hashlib,json,re,subprocess
ROOT=Path(__file__).resolve().parents[1]
def main():
    files=subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','-z'],cwd=ROOT).decode().split('\0')
    records=[];blocked=[]
    for name in sorted(set(filter(None,files))):
        p=ROOT/name
        if not p.is_file():continue
        if p.suffix.lower() in {'.db','.sqlite','.sqlite3','.key','.keystore','.jks','.p12','.pfx'} or p.name in {'secrets.h','device_auth.h','signing.properties','local.properties'}:
            blocked.append({'path':name,'reason':'private/runtime artifact'});continue
        if p.suffix in {'.py','.ts','.tsx','.java','.swift','.mjs','.js','.md','.json','.properties','.gradle','.sh'}:
            text=p.read_text(errors='replace')
            if re.search(r'-----BEGIN (?:RSA |EC )?PRIVATE KEY-----|cl_s1_[A-Za-z0-9_-]{43}',text):
                blocked.append({'path':name,'reason':'credential-shaped literal; inspect locally without printing values'});continue
        records.append({'path':name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
    out=ROOT/'.coursework/submission';out.mkdir(parents=True,exist_ok=True)
    result={'branch':subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip(),'remote':subprocess.check_output(['git','remote','get-url','origin'],cwd=ROOT,text=True).strip(),'files':records,'blocked':blocked,'not_committed':True,'not_pushed':True,'scope':'Current proposed source only; not a proof of historical secrecy. Runtime and private evidence remain local.'}
    (out/'manifest.json').write_text(json.dumps(result,indent=2)+'\n')
    print('Prepared source manifest: '+str(len(records))+' files; blocked artifacts: '+str(len(blocked))+'. No git state changed.')
    return bool(blocked)
if __name__=='__main__':raise SystemExit(main())
