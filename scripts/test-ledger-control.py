#!/usr/bin/env python3
"""Safe local regression runner; no listener or live service access."""
import contextlib
import io
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
MODULES=["backend.test_api","backend.test_device_auth","backend.test_device_api","backend.test_migration_readiness",
 "backend.test_web_auth","backend.test_auth_hardening","backend.test_password_preservation",
 "backend.test_nonce_recovery","backend.test_ledger_control"]


def main():
    class SafeResult(unittest.TestResult):
        def __init__(self):super().__init__();self.statuses=[]
        def addSuccess(self,test):super().addSuccess(test);self.statuses.append((test.id(),"PASS"))
        def addError(self,test,error):super().addError(test,error);self.statuses.append((test.id(),"FAIL (error)"))
        def addFailure(self,test,error):super().addFailure(test,error);self.statuses.append((test.id(),"FAIL"))
        def addSubTest(self,test,subtest,error):
            super().addSubTest(test,subtest,error)
            if error is not None:self.statuses.append((test.id(),"FAIL (subtest)"))
    result=SafeResult()
    with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
        unittest.defaultTestLoader.loadTestsFromNames(MODULES).run(result)
    for name,status in result.statuses:print(name+": "+status)
    print(f"TOTAL {result.testsRun}; FAIL {len(result.failures)+len(result.errors)}; SKIP {len(result.skipped)}")
    return 0 if result.wasSuccessful() and not result.skipped else 1


if __name__=="__main__":sys.exit(main())
