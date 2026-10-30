import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest

SCRIPT=Path(__file__).resolve().parents[1]/'scripts/check-device-migration.py'
spec=importlib.util.spec_from_file_location('migration_readiness',SCRIPT)
readiness=importlib.util.module_from_spec(spec)
spec.loader.exec_module(readiness)


class ReadinessTests(unittest.TestCase):
    def test_exact_candidate_url(self):
        ip='172.20.10.11'
        self.assertTrue(readiness.valid_target('https://172.20.10.11:9443/sensor-data',ip))
        for url in ['http://172.20.10.11:9443/sensor-data','https://172.20.10.11:8443/sensor-data',
                    'https://172.20.10.11:9443/sensor-data?key=fixture','https://172.20.10.11:9443/sensor-data#fragment',
                    'https://fixture:fixture@172.20.10.11:9443/sensor-data','https://172.20.10.11:9443/wrong',
                    'https://172.20.10.12:9443/sensor-data']:
            self.assertFalse(readiness.valid_target(url,ip))

    def test_device_match_and_disabled_or_changed_keys(self):
        api='fixture_api_key_only_'+'a'*32
        key='1'*64
        text=f'const char DEVICE_AUTH_ID[]="esp32-test";\nconst char DEVICE_API_KEY[]="{api}";\nconst char DEVICE_HMAC_KEY_HEX[]="{key}";'
        record={'enabled':True,'api_key_sha256':hashlib.sha256(api.encode()).hexdigest(),'hmac_key_hex':key}
        registry={'version':1,'devices':{'esp32-test':record}}
        self.assertTrue(readiness.credentials_match(text,registry))
        for field,value in [('enabled',False),('api_key_sha256','0'*64),('hmac_key_hex','0'*64)]:
            original=record[field];record[field]=value
            self.assertFalse(readiness.credentials_match(text,registry))
            record[field]=original
        self.assertFalse(readiness.credentials_match(text+text,registry))

    def test_database_aliases_never_count_as_isolated(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);legacy=root/'legacy.db';legacy.touch()
            self.assertFalse(readiness.isolated_paths(legacy,legacy))
            link=root/'linked.db';link.symlink_to(legacy)
            self.assertFalse(readiness.isolated_paths(link,legacy))
            self.assertTrue(readiness.isolated_paths(root/'candidate.db',legacy))
