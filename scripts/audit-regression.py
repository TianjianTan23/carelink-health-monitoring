#!/usr/bin/env python3
"""Discover current tests, preserve warning output, record synthetic evidence."""
import gc
import json
from pathlib import Path
import sys
import time
import unittest
import warnings

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

def main():
    destination=Path(sys.argv[1])
    modules=sys.argv[2:]
    suite=(unittest.defaultTestLoader.loadTestsFromNames(modules) if modules else
           unittest.defaultTestLoader.discover(str(ROOT),pattern='test_*.py',top_level_dir=str(ROOT)))
    warning_counts={}
    original=warnings.showwarning
    def observed(message,category,filename,lineno,file=None,line=None):
        warning_counts[category.__name__]=warning_counts.get(category.__name__,0)+1
        return original(message,category,filename,lineno,file,line)
    class Result(unittest.TextTestResult):
        def __init__(self,*a,**kw):super().__init__(*a,**kw);self.statuses=[]
        def addSuccess(self,t):super().addSuccess(t);self.statuses.append([t.id(),'PASS'])
        def addFailure(self,t,e):super().addFailure(t,e);self.statuses.append([t.id(),'FAIL'])
        def addError(self,t,e):super().addError(t,e);self.statuses.append([t.id(),'FAIL (error)'])
        def addSkip(self,t,r):super().addSkip(t,r);self.statuses.append([t.id(),'NOT VERIFIED'])
    started=time.monotonic()
    warnings.showwarning=observed
    try:
        result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(suite)
        gc.collect()
    finally:warnings.showwarning=original
    from backend.test_atomic_freeze import RESULTS
    from backend.tls_test_support import OBSERVATIONS
    from backend.process_test_support import CHILD_CHECKS
    from backend.test_remediation_controls import REHEARSALS
    report={'command':sys.orig_argv,'total':result.testsRun,'passed':sum(s=='PASS' for _,s in result.statuses),
        'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),
        'warnings':warning_counts,'seconds':round(time.monotonic()-started,3),
        'statuses':result.statuses,'concurrency':RESULTS,'tls':OBSERVATIONS,'recovery':REHEARSALS,
        'checked_child_streams':len(CHILD_CHECKS),'child_resource_warnings':sum(CHILD_CHECKS)}
    report['exit_code']=0 if result.wasSuccessful() and not result.skipped and not warning_counts.get('ResourceWarning') else 1
    destination.write_text(json.dumps(report,indent=2)+'\n')
    print('AUDIT_SUMMARY '+json.dumps({k:v for k,v in report.items() if k not in ['statuses','concurrency','tls','command','recovery']}))
    return report['exit_code']

if __name__=='__main__':raise SystemExit(main())
