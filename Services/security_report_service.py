import json
import os
from datetime import datetime, timezone


class SecurityReportService:
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
