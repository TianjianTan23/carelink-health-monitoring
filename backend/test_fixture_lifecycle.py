"""Regression checks for failure-path diagnostics and child cleanup."""
from contextlib import ExitStack
import subprocess
import sys
import unittest
from unittest.mock import Mock, patch

from .process_test_support import reap_process
from .tls_test_support import TLSProcess


class FixtureLifecycleTests(unittest.TestCase):
    def test_timeout_cleanup_reaps_child_and_closes_all_pipes(self):
        with self.assertRaises(subprocess.TimeoutExpired):
            with ExitStack() as stack:
                child=subprocess.Popen([sys.executable,'-I','-S','-c','import time;time.sleep(30)'],
                    stdout=subprocess.PIPE,stderr=subprocess.PIPE)
                stack.callback(reap_process,child)
                child.communicate(timeout=0.01)
        self.assertIsNotNone(child.poll())
        self.assertTrue(child.stdout.closed)
        self.assertTrue(child.stderr.closed)

    def test_diagnostic_is_bounded_redacted_and_includes_exit_and_probe(self):
        with patch('backend.tls_test_support.socket.socket') as factory:
            factory.return_value.getsockname.return_value=('127.0.0.1',12345)
            fixture=TLSProcess('.', 'synthetic.invalid:app','unused','unused',None)
            try:
                fixture.child=Mock();fixture.child.poll.return_value=23
                fixture.last_probe='ConnectTimeout'
                fixture.log.write((('line\n'*3000)+'cookie: cl_s1_'+('a'*43)+'\nFAIL: fixture startup\n').encode())
                text=fixture.diagnostic('fixture failure')
                self.assertIn('returncode=23',text);self.assertIn('ConnectTimeout',text)
                self.assertIn('FAIL: fixture startup',text);self.assertNotIn('cl_s1_',text)
                self.assertLess(len(text),6300)
            finally:
                fixture.close()
            self.assertTrue(fixture.log.closed)
            factory.return_value.close.assert_called_once()

    def test_constructor_failure_closes_socket_for_bind_and_log_errors(self):
        for failure in ('bind','log'):
            with self.subTest(stage=failure),patch('backend.tls_test_support.socket.socket') as factory,patch('backend.tls_test_support.tempfile.TemporaryFile') as log:
                factory.return_value.getsockname.return_value=('127.0.0.1',12345)
                if failure=='bind':factory.return_value.bind.side_effect=PermissionError('synthetic bind denial')
                else:log.side_effect=OSError('synthetic log failure')
                with self.assertRaises(OSError):TLSProcess('.', 'unused:app','unused','unused',None)
                factory.return_value.close.assert_called_once()
