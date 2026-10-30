"""Owned test child cleanup and visible, enforced ResourceWarning checks."""
import os
import re
import subprocess
import sys

CHILD_CHECKS=[]


def warning_environment(env=None):
    result=dict(os.environ if env is None else env)
    prior=result.get('PYTHONWARNINGS','')
    result['PYTHONWARNINGS']=(prior+',' if prior else '')+'always::ResourceWarning'
    return result


def check_child_warnings(stderr):
    text=stderr.decode(errors='replace') if isinstance(stderr,bytes) else stderr or ''
    count=text.count('ResourceWarning:')
    CHILD_CHECKS.append(count)
    print(f'FIXTURE_CHILD_RESOURCE_WARNINGS {count}',file=sys.stderr)
    if count:raise AssertionError('Disposable child emitted ResourceWarning; test failed')


def start_process(*args,**kwargs):
    kwargs['env']=warning_environment(kwargs.get('env'))
    return subprocess.Popen(*args,**kwargs)


def checked_run(*args,**kwargs):
    kwargs['env']=warning_environment(kwargs.get('env'))
    result=subprocess.run(*args,**kwargs)
    check_child_warnings(result.stderr)
    return result


def reap_process(child):
    if child.poll() is None:child.kill()
    # communicate closes pipes and returns cached stderr after an earlier call.
    _,stderr=child.communicate(timeout=5)
    check_child_warnings(stderr)


def child_diagnostic(stderr):
    text=stderr.decode(errors='replace') if isinstance(stderr,bytes) else str(stderr or '')
    text=re.sub(r'cl_s1_[A-Za-z0-9_-]+|[0-9a-fA-F]{32,}','[REDACTED]',text[-6000:])
    return re.sub(r'(?im)^.*(?:password|cookie|api.key|signature|hmac.key|authorization).*$', '[REDACTED LINE]',text)
