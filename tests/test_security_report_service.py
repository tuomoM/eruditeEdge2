import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from Services.security_report_service import SecurityReportService


class SecurityReportServiceTestCase(unittest.TestCase):
    def test_generate_report_writes_to_configured_path(self):
        service = SecurityReportService()
        with tempfile.TemporaryDirectory() as report_directory:
            report_path = os.path.join(report_directory, "nested", "security-report.json")

            def fake_run(command, **kwargs):
                with open(report_path, "w", encoding="utf-8") as report_file:
                    report_file.write('{"dependencies": [], "fixes": []}')
                return SimpleNamespace(returncode=0, stdout="", stderr="")

            with patch("Services.security_report_service.subprocess.run", fake_run):
                generated, error = service.generate_report(report_path, "/app")

        self.assertTrue(generated)
        self.assertIsNone(error)

    def test_generate_report_accepts_vulnerability_exit_code_when_report_exists(self):
        service = SecurityReportService()
        with tempfile.NamedTemporaryFile(delete=False) as report_file:
            report_path = report_file.name
        os.unlink(report_path)
        try:
            def fake_run(command, **kwargs):
                with open(report_path, "w", encoding="utf-8") as report:
                    report.write('{"dependencies": [], "fixes": []}')
                return SimpleNamespace(returncode=1, stdout="", stderr="")

            with patch("Services.security_report_service.subprocess.run", fake_run):
                generated, error = service.generate_report(report_path, "/app")

            self.assertTrue(generated)
            self.assertIsNone(error)
        finally:
            if os.path.exists(report_path):
                os.unlink(report_path)

    def test_generate_report_returns_error_when_audit_fails_without_report(self):
        service = SecurityReportService()
        with tempfile.NamedTemporaryFile(delete=False) as report_file:
            report_path = report_file.name
        os.unlink(report_path)

        def fake_run(command, **kwargs):
            return SimpleNamespace(returncode=2, stdout="", stderr="pip-audit failed")

        with patch("Services.security_report_service.subprocess.run", fake_run):
            generated, error = service.generate_report(report_path, "/app")

        self.assertFalse(generated)
        self.assertEqual(error, "pip-audit failed")


if __name__ == "__main__":
    unittest.main()
