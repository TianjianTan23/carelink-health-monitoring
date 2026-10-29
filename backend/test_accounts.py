"""Account setup is independent of certificates, and preserves configured passwords."""
import importlib.util
from pathlib import Path
import secrets
import stat
import tempfile
import unittest
from dotenv import dotenv_values
from .security import verify_password

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("configure_accounts", ROOT / "scripts/configure-accounts.py")
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)

class AccountSetupTests(unittest.TestCase):
    def test_first_setup_needs_no_certificate_or_device_key(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / ".env"
            patient, nurse = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
            values = iter([patient, patient, nurse, nurse])
            self.assertTrue(setup.configure(path, prompt=lambda _: next(values)))
            config = dotenv_values(path, interpolate=False)
            self.assertTrue(setup.configured(config))
            self.assertTrue(verify_password(patient, config["CARELINK_PATIENT_PASSWORD_HASH"]))
            self.assertTrue(verify_password(nurse, config["CARELINK_NURSE_PASSWORD_HASH"]))
            self.assertNotIn(patient, path.read_text())
            self.assertNotIn(nurse, path.read_text())
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual([p.name for p in Path(folder).iterdir()], [".env"])
            self.assertFalse(any("TLS" in k or "DEVICES" in k for k in config))
            before = path.read_bytes()
            self.assertFalse(setup.configure(path, prompt=lambda _: self.fail("Existing accounts must not prompt")))
            self.assertEqual(before, path.read_bytes())

    def test_mismatched_passwords_do_not_overwrite_existing_settings(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / ".env"
            path.write_text("VITE_DATA_MODE=live\n")
            before = path.read_bytes()
            values = iter([secrets.token_urlsafe(24), secrets.token_urlsafe(24)])
            with self.assertRaises(ValueError):
                setup.configure(path, prompt=lambda _: next(values))
            self.assertEqual(before, path.read_bytes())
