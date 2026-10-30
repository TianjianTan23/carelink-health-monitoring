#!/usr/bin/env python3
"""Complete backend suite, safe status output and aggregate acceptance evidence."""
import gc
import warnings
import contextlib
import io
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
ROOT=Path(__file__).resolve().parents[1]


def main():
    class SafeResult(unittest.TestResult):
        def __init__(self):super().__init__();self.statuses=[]
        def addSuccess(self,test):super().addSuccess(test);self.statuses.append((test.id(),'PASS'))
        def addError(self,test,error):super().addError(test,error);self.statuses.append((test.id(),'FAIL (error)'))
        def addFailure(self,test,error):super().addFailure(test,error);self.statuses.append((test.id(),'FAIL'))
        def addSkip(self,test,reason):super().addSkip(test,reason);self.statuses.append((test.id(),'NOT VERIFIED (skip)'))
        def addSubTest(self,test,subtest,error):
            super().addSubTest(test,subtest,error)
            if error:self.statuses.append((test.id(),'FAIL (subtest)'))
    result=SafeResult()
    captured=io.StringIO()
    warnings.simplefilter('always',ResourceWarning)
    with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(captured):
        unittest.defaultTestLoader.discover(str(ROOT),pattern='test_*.py',top_level_dir=str(ROOT)).run(result)
        gc.collect()
    resource_warnings=captured.getvalue().count('ResourceWarning:')
    print('RESOURCE_WARNINGS '+str(resource_warnings))
    for name,status in result.statuses:print(name+': '+status)
    summary=f'TOTAL {result.testsRun}; FAIL {len(result.failures)+len(result.errors)}; SKIP {len(result.skipped)}'
    print(summary)
    if len(sys.argv)>1:
        from backend.test_atomic_freeze import RESULTS
        Path(sys.argv[1]).write_text(json.dumps({'summary':summary,'cases':RESULTS,'statuses':result.statuses,'resource_warnings':resource_warnings},indent=2)+'\n')
    return 0 if result.wasSuccessful() and not result.skipped and not resource_warnings else 1


if __name__=='__main__':sys.exit(main())
