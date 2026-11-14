"""Frozen-clock regression tests; no cloud or wall-clock-sensitive assertions."""
from datetime import datetime, timedelta, timezone
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cmk_expiry_preflight import check_initial_expiry, check_variable_file


NOW = datetime(2030, 1, 1, tzinfo=timezone.utc)


class InitialExpiryTests(unittest.TestCase):
    def test_disabled_profile_needs_no_expiry(self):
        check_initial_expiry(False, None, NOW)

    def test_disabled_profile_does_not_revalidate_old_key(self):
        check_initial_expiry(False, "2000-01-01T00:00:00Z", NOW)

    def test_reject_expired(self):
        with self.assertRaises(ValueError):
            check_initial_expiry(True, "2000-01-01T00:00:00Z", NOW)

    def test_reject_near_expiry(self):
        with self.assertRaises(ValueError):
            check_initial_expiry(True, (NOW + timedelta(days=29)).isoformat(), NOW)

    def test_reject_exact_thirty_day_boundary(self):
        with self.assertRaises(ValueError):
            check_initial_expiry(True, (NOW + timedelta(days=30)).isoformat(), NOW)

    def test_accept_strictly_more_than_thirty_days(self):
        check_initial_expiry(True, (NOW + timedelta(days=30, seconds=1)).isoformat(), NOW)

    def test_reject_missing_expiry(self):
        with self.assertRaises(ValueError):
            check_initial_expiry(True, None, NOW)

    def test_reject_malformed_expiry(self):
        with self.assertRaises(ValueError):
            check_initial_expiry(True, "invalid", NOW)

    def test_reject_missing_timezone(self):
        with self.assertRaises(ValueError):
            check_initial_expiry(True, "2031-01-01T00:00:00", NOW)

    def test_reject_non_utc_offset(self):
        with self.assertRaises(ValueError):
            check_initial_expiry(True, "2031-01-01T00:00:00+01:00", NOW)

    def check_file(self, contents, environment=None):
        with tempfile.TemporaryDirectory(prefix="cmk-initial-test-") as temporary:
            path = Path(temporary) / "reviewed.tfvars.json"
            path.write_text(json.dumps(contents), encoding="utf-8")
            with patch.dict(os.environ, environment or {}, clear=True):
                check_variable_file(path, NOW)

    def test_reads_expiry_from_same_reviewed_file(self):
        self.check_file({"enable_cmk": True, "key_expiration_utc": "2031-01-01T00:00:00Z"})

    def test_reject_expired_value_in_reviewed_file(self):
        with self.assertRaises(ValueError):
            self.check_file({"enable_cmk": True, "key_expiration_utc": "2000-01-01T00:00:00Z"})

    def test_reject_file_without_explicit_activation(self):
        with self.assertRaises(ValueError):
            self.check_file({"key_expiration_utc": "2031-01-01T00:00:00Z"})

    def test_reject_competing_environment_override(self):
        with self.assertRaises(ValueError):
            self.check_file({"enable_cmk": True, "key_expiration_utc": "2031-01-01T00:00:00Z"},
                            {"TF_VAR_key_expiration_utc": "2000-01-01T00:00:00Z"})


def run_frozen_clock_tests() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(InitialExpiryTests)
    result = unittest.TextTestRunner(stream=io.StringIO()).run(suite)
    if not result.wasSuccessful() or result.testsRun != 14:
        raise AssertionError("Initial CMK frozen-clock regression tests failed")
    return result.testsRun


if __name__ == "__main__":
    unittest.main()
