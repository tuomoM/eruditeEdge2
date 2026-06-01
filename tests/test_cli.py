import os
import tempfile
import unittest
from unittest.mock import patch

from app import create_app


class CliTestCase(unittest.TestCase):
    def create_test_app(self):
        database_file = tempfile.NamedTemporaryFile(delete=False)
        database_file.close()
        self.addCleanup(os.unlink, database_file.name)
        return create_app(
            {
                "TESTING": True,
                "DATABASE": database_file.name,
                "SECRET_KEY": "test-secret-key",
            }
        )

    def test_check_database_reports_railway_volume(self):
        app = self.create_test_app()

        with patch.dict(
            os.environ,
            {"RAILWAY_VOLUME_MOUNT_PATH": "/app/data"},
            clear=True,
        ):
            result = app.test_cli_runner().invoke(args=["check-database"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("Railway volume: /app/data", result.output)

    def test_check_database_allows_explicit_database_path(self):
        app = self.create_test_app()

        with patch.dict(
            os.environ,
            {"DATABASE": "/app/data/database.db"},
            clear=True,
        ):
            result = app.test_cli_runner().invoke(args=["check-database"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("Database path is set explicitly.", result.output)

    def test_check_database_fails_on_railway_without_persistent_path(self):
        app = self.create_test_app()

        with patch.dict(
            os.environ,
            {"RAILWAY_ENVIRONMENT": "production"},
            clear=True,
        ):
            result = app.test_cli_runner().invoke(args=["check-database"])

        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("has no persistent database path", result.output)

    def test_check_database_allows_local_environment(self):
        app = self.create_test_app()

        with patch.dict(os.environ, {}, clear=True):
            result = app.test_cli_runner().invoke(args=["check-database"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("using the local database path", result.output)


if __name__ == "__main__":
    unittest.main()
