#!/usr/bin/env python3
"""Stop only this checkout's default course demo processes; never gateway ports."""
from pathlib import Path
import argparse,os,signal,subprocess
ROOT=Path(__file__).resolve().parents[1]
def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--stop',action='store_true');args=parser.parse_args()
    for port,marker in [(18500,'vite preview --outDir build-demo'),(18445,'scripts/coursework-backend.py')]:
        result=subprocess.run(['lsof','-t',f'-iTCP:{port}','-sTCP:LISTEN'],capture_output=True,text=True)
        for value in set(result.stdout.split()):
            pid=int(value)
            command=subprocess.run(['ps','-p',value,'-o','command='],capture_output=True,text=True).stdout
            cwd=subprocess.run(['lsof','-a','-p',value,'-d','cwd','-Fn'],capture_output=True,text=True).stdout
            if marker not in command or ('n'+str(ROOT)+'\n') not in cwd:
                print(f'Port {port}: owner differs; left untouched.');continue
            if args.stop:os.kill(pid,signal.SIGTERM)
            print(f'Course demo {port}: '+('stopped' if args.stop else 'running'))
if __name__=='__main__':main()
