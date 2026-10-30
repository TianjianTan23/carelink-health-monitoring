#!/usr/bin/env python3
"""Explicit operator interface. No default paths, auto recovery or reset."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.ledger_control import Controller


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--control-root",required=True,type=Path)
    subs=p.add_subparsers(dest="action",required=True)
    enroll=subs.add_parser("enroll-offline")
    enroll.add_argument("--source",required=True,type=Path);enroll.add_argument("--inventory",required=True,type=Path)
    enroll.add_argument("--confirm-audited-offline-adoption",action="store_true",required=True)
    freeze=subs.add_parser("freeze");freeze.add_argument("--drain-timeout",type=float,default=10)
    for name in ("switch","resume","recover-frozen","status"):subs.add_parser(name)
    verify=subs.add_parser("verify-backup");verify.add_argument("--backup",required=True,type=Path)
    prep=subs.add_parser("prepare");prep.add_argument("--generation",required=True);prep.add_argument("--backup",type=Path)
    args=p.parse_args()
    paths=[args.control_root]+[getattr(args,n) for n in ("source","inventory","backup") if getattr(args,n,None) is not None]
    if not all(path.is_absolute() for path in paths):p.error("Absolute paths required")
    try:
        c=Controller(args.control_root)
        if args.action=="enroll-offline":c=Controller.enroll(args.control_root,args.source,args.inventory);result=c.state()
        elif args.action=="verify-backup":result=c.verify_backup(args.backup)
        elif args.action=="prepare":result=c.prepare(args.generation,backup=args.backup)
        elif args.action=="recover-frozen":result=c.recover()
        elif args.action=="status":result=c.state()
        elif args.action=="freeze":result=c.freeze(timeout=args.drain_timeout)
        else:result=getattr(c,args.action)()
        print("PASS phase="+result["phase"]+" sequence="+str(result["sequence"]))
        return 0
    except Exception:
        print("FAIL: operation refused or incomplete; keep all evidence. No automatic cleanup.")
        return 1


if __name__=="__main__":sys.exit(main())
