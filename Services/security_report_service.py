import json
import os
import subprocess
import sys
from datetime import datetime, timezone


class SecurityReportService:
    def generate_report(self, report_path, working_directory):
        report_directory = os.path.dirname(report_path)
        if report_directory:
            os.makedirs(report_directory, exist_ok=True)

        command = [
            sys.executable,
            "-m",
            "pip_audit",
            "--format",
            "json",
            "--output",
            report_path,
            "--progress-spinner",
            "off",
        ]
        result = subprocess.run(
            command,
            cwd=working_directory,
            capture_output=True,
            text=True,
            check=False,
        )

        if os.path.exists(report_path) and result.returncode in {0, 1}:
            return True, None

        error = (result.stderr or result.stdout or "Security audit failed").strip()
        return False, error

    def read_report(self, report_path):
        if not os.path.exists(report_path):
            return self._empty_report("Security report has not been generated yet.")

        try:
            with open(report_path, encoding="utf-8") as report_file:
                report = json.load(report_file)
        except (OSError, json.JSONDecodeError):
            return self._empty_report("Security report could not be read.")

        dependencies = report.get("dependencies")
        if not isinstance(dependencies, list):
            return self._empty_report("Security report has an unexpected format.")

        vulnerable_dependencies = []
        vulnerability_count = 0
        for dependency in dependencies:
            vulns = dependency.get("vulns") or []
            if not vulns:
                continue

            vulnerability_count += len(vulns)
            vulnerable_dependencies.append(
                {
                    "name": dependency.get("name", "unknown"),
                    "version": dependency.get("version", "unknown"),
                    "vulnerabilities": [
                        self._format_vulnerability(vulnerability)
                        for vulnerability in vulns
                    ],
                }
            )

        return {
            "status": "ok",
            "message": None,
            "last_run_at": self._last_modified_at(report_path),
            "dependency_count": len(dependencies),
            "vulnerability_count": vulnerability_count,
            "vulnerable_dependencies": vulnerable_dependencies,
        }

    def _empty_report(self, message):
        return {
            "status": "missing",
            "message": message,
            "last_run_at": None,
            "dependency_count": 0,
            "vulnerability_count": 0,
            "vulnerable_dependencies": [],
        }

    def _last_modified_at(self, report_path):
        modified_at = datetime.fromtimestamp(
            os.path.getmtime(report_path),
            timezone.utc,
        )
        return modified_at.isoformat(timespec="seconds")

    def _format_vulnerability(self, vulnerability):
        return {
            "id": vulnerability.get("id", "unknown"),
            "description": vulnerability.get("description", ""),
            "fix_versions": vulnerability.get("fix_versions") or [],
        }


security_report_service = SecurityReportService()
