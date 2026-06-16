import os
import unittest
from unittest.mock import patch

import config
from app import create_app


class ConfigTestCase(unittest.TestCase):
    def test_database_uses_explicit_database_env(self):
        with patch.dict(
            os.environ,
            {
                "DATABASE": "/tmp/custom-erudite-edge.db",
                "RAILWAY_VOLUME_MOUNT_PATH": "/app/data",
            },
            clear=True,
        ):
            self.assertEqual(
                config._default_database_path(),
                "/tmp/custom-erudite-edge.db",
            )

    def test_database_defaults_to_railway_volume_when_present(self):
        with patch.dict(
            os.environ,
            {"RAILWAY_VOLUME_MOUNT_PATH": "/app/data"},
            clear=True,
        ):
            self.assertEqual(
                config._default_database_path(),
                "/app/data/database.db",
            )

    def test_database_defaults_to_local_database_without_volume(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                config._default_database_path(),
                os.path.join(config.BASE_DIR, "database.db"),
            )

    def test_security_report_uses_explicit_path_env(self):
        with patch.dict(
            os.environ,
            {
                "SECURITY_REPORT_PATH": "/tmp/custom-security-report.json",
                "SECURITY_REPORT_DIR": "/tmp/reports",
            },
            clear=True,
        ):
            self.assertEqual(
                config._default_security_report_path(),
                "/tmp/custom-security-report.json",
            )

    def test_security_report_uses_report_dir_env(self):
        with patch.dict(
            os.environ,
            {"SECURITY_REPORT_DIR": "/app/data"},
            clear=True,
        ):
            self.assertEqual(
                config._default_security_report_path(),
                "/app/data/security-report.json",
            )

    def test_security_report_defaults_to_project_root_without_env(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                config._default_security_report_path(),
                os.path.join(config.BASE_DIR, "security-report.json"),
            )

    def test_production_requires_explicit_secret_key(self):
        with self.assertRaisesRegex(RuntimeError, "SECRET_KEY must be set"):
            create_app(
                {
                    "APP_ENV": "production",
                    "SECRET_KEY": "dev-secret-key",
                }
            )

    def test_production_accepts_explicit_secret_key_and_secure_cookie_defaults(self):
        app = create_app(
            {
                "APP_ENV": "production",
                "SECRET_KEY": "production-secret-key",
            }
        )

        self.assertTrue(app.config["SESSION_COOKIE_HTTPONLY"])
        self.assertEqual(app.config["SESSION_COOKIE_SAMESITE"], "Lax")
        self.assertTrue(app.config["SESSION_COOKIE_SECURE"])


if __name__ == "__main__":
    unittest.main()
