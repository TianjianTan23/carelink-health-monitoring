#!/usr/bin/env python3
"""Safe backend test output: names and PASS/FAIL only; no assertion values."""
import contextlib
import io
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

MODULES = ["backend.test_api","backend.test_device_auth","backend.test_device_api",
           "backend.test_migration_readiness","backend.test_web_auth",
           "backend.test_auth_hardening","backend.test_auth_https_isolated",
           "backend.test_password_preservation", "backend.test_nonce_recovery",
           "backend.test_nonce_https_recovery"]


class SafeResult(unittest.TestResult):
    def __init__(self):
        super().__init__();self.statuses=[]
    def addSuccess(self,test):
        super().addSuccess(test);self.statuses.append((test.id(),"PASS"))
    def addError(self,test,err):
        super().addError(test,err);self.statuses.append((test.id(),"FAIL (error)"))
    def addFailure(self,test,err):
        super().addFailure(test,err);self.statuses.append((test.id(),"FAIL"))
    def addSkip(self,test,reason):
        super().addSkip(test,reason);self.statuses.append((test.id(),"NOT VERIFIED (skip)"))
    def addSubTest(self,test,subtest,err):
        super().addSubTest(test,subtest,err)
        if err is not None:self.statuses.append((test.id(),"FAIL (subtest)"))


def main():
    result=SafeResult()
    # Captured assertion/exception/log text is never written to disk or output.
    # Debug failures locally with synthetic fixtures only, never live credentials.
    with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
        unittest.defaultTestLoader.loadTestsFromNames(MODULES).run(result)
    for name,status in result.statuses:print(f"{name}: {status}")
    print(f"TOTAL {result.testsRun}; FAIL {len(result.errors)+len(result.failures)}; SKIP {len(result.skipped)}")
    return 0 if result.wasSuccessful() and not result.skipped else 1


if __name__ == "__main__":sys.exit(main())
