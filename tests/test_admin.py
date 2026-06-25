import json
import os
import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime, timedelta, timezone

import db
from app import create_app
from csrf import CSRF_SESSION_KEY
from db import init_db


class AdminTestCase(unittest.TestCase):
    def setUp(self):
        self.database_file = tempfile.NamedTemporaryFile(delete=False)
        self.database_file.close()
        self.security_report_file = tempfile.NamedTemporaryFile(delete=False)
        self.security_report_file.close()
        self.app = create_app(
            {
                "TESTING": True,
                "DATABASE": self.database_file.name,
                "SECRET_KEY": "test-secret-key",
                "SECURITY_REPORT_PATH": self.security_report_file.name,
            }
        )
        init_db(self.app)
        self.client = self.app.test_client()

    def tearDown(self):
        os.unlink(self.database_file.name)
        if os.path.exists(self.security_report_file.name):
            os.unlink(self.security_report_file.name)

    def register(self, username):
        invite_code = self.create_invite_code()
        return self.client.post(
            "/register",
            json={
                "username": username,
                "password": "AdminSafe12!",
                "invite_code": invite_code,
            },
            headers=self.registration_csrf_headers(),
        )

    def create_admin(self, username="tuomo"):
        runner = self.app.test_cli_runner()
        result = runner.invoke(
            args=[
                "create-admin",
                "--username",
                username,
                "--password",
                "AdminSafe12!",
            ]
        )
        self.assertEqual(result.exit_code, 0)

    def login(self, username):
        return self.client.post(
            "/login",
            json={"username": username, "password": "AdminSafe12!"},
        )

    def registration_csrf_headers(self):
        with self.client.session_transaction() as session:
            session[CSRF_SESSION_KEY] = "test-registration-csrf-token"
        return {"X-CSRF-Token": "test-registration-csrf-token"}

    def invite_creator_id(self):
        with self.app.app_context():
            rows = db.query("SELECT id FROM users ORDER BY id LIMIT 1")
            if rows:
                return rows[0]["id"]
            self.create_admin("invite_issuer")
            return db.query("SELECT id FROM users WHERE username = ?", ["invite_issuer"])[0]["id"]

    def create_invite_code(self, expires_at=None):
        if expires_at is None:
            expires_at = datetime.now(timezone.utc) + timedelta(days=5)
        creator_id = self.invite_creator_id()
        with self.app.app_context():
            count = db.query("SELECT COUNT(*) AS count FROM invite_codes")[0]["count"]
            code = f"test-invite-code-{count + 1}"
            db.execute(
                """
                INSERT INTO invite_codes (code, created_by, expires_at)
                VALUES (?, ?, ?)
                """,
                [code, creator_id, expires_at.isoformat()],
            )
        return code

    def logout(self):
        self.client.post("/logout", json={})

    def valid_entry(self, word):
        return {
            "word": word,
            "definition": f"Definition for {word}",
            "context": "Admin",
            "synonyms": [f"{word} synonym"],
            "examples": [f"{word} appears in this sentence."],
        }

    def valid_cloze_entry(self, word):
        entry = self.valid_entry(word)
        entry["part_of_speech"] = "adjective"
        entry["domains"] = ["cognition"]
        entry["cloze_sentences"] = [
            "The argument rested on a ____ assumption.",
            "The evidence showed only a ____ connection.",
        ]
        return entry

    def create_vocab(self, word):
        return self.client.post("/vocabulary", json=self.valid_entry(word))

    def create_cloze_vocab(self, word):
        return self.client.post("/vocabulary", json=self.valid_cloze_entry(word))

    def csrf_token(self):
        self.client.get("/admin")
        with self.client.session_transaction() as session:
            return session["_csrf_token"]

    def csrf_headers(self):
        return {"X-CSRF-Token": self.csrf_token()}

    def user_categories(self):
        with self.app.app_context():
            rows = db.query(
                """
                SELECT username, account_category
                FROM users
                ORDER BY username
                """
            )
        return {row["username"]: row["account_category"] for row in rows}

    def set_ai_generation_count(self, user_id, generation_count):
        with self.app.app_context():
            db.execute(
                """
                INSERT INTO ai_generation_usage
                    (user_id, generation_date, generation_count)
                VALUES (?, DATE('now'), ?)
                """,
                [user_id, generation_count],
            )

    def ai_generation_count(self, user_id):
        with self.app.app_context():
            rows = db.query(
                """
                SELECT generation_count
                FROM ai_generation_usage
                WHERE user_id = ? AND generation_date = DATE('now')
                """,
                [user_id],
            )
        if not rows:
            return 0
        return rows[0]["generation_count"]

    def invite_codes(self):
        with self.app.app_context():
            rows = db.query(
                """
                SELECT code, created_by, expires_at
                FROM invite_codes
                ORDER BY id
                """
            )
        return [dict(row) for row in rows]

    def sqlite_timestamp(self, value):
        return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    def write_security_report(self, report):
        with open(self.security_report_file.name, "w", encoding="utf-8") as report_file:
            json.dump(report, report_file)

    def test_admin_page_requires_admin(self):
        self.register("anna")

        response = self.client.get("/admin", follow_redirects=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Admin account is required", response.data)

    def test_admin_page_shows_ai_generation_quota_usage(self):
        self.create_admin("tuomo")
        user_response = self.register("anna")
        user_id = user_response.get_json()["id"]
        self.set_ai_generation_count(user_id, 7)
        self.logout()
        self.login("tuomo")

        response = self.client.get("/admin")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"AI generations today:", response.data)
        self.assertIn(b"7 / 20", response.data)
        self.assertIn(b"0 / unlimited", response.data)

    def test_admin_page_shows_invite_codes(self):
        self.create_admin("tuomo")
        self.logout()
        self.login("tuomo")
        self.client.post(
            "/admin/invite-codes",
            json={},
            headers=self.csrf_headers(),
        )

        response = self.client.get("/admin")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Invite codes", response.data)
        self.assertIn(self.invite_codes()[0]["code"].encode(), response.data)

    def test_admin_page_shows_new_user_and_vocab_summary(self):
        self.create_admin("tuomo")
        now = datetime.now(timezone.utc)
        today = self.sqlite_timestamp(now)
        rolling_week = self.sqlite_timestamp(now - timedelta(days=2))
        older = self.sqlite_timestamp(now - timedelta(days=8))
        with self.app.app_context():
            admin_id = db.query("SELECT id FROM users WHERE username = ?", ["tuomo"])[0]["id"]
            db.execute(
                "UPDATE users SET created_at = ? WHERE id = ?",
                [older, admin_id],
            )
            for username, created_at in [
                ("today_user", today),
                ("week_user", rolling_week),
                ("old_user", older),
            ]:
                db.execute(
                    """
                    INSERT INTO users (username, password_hash, account_category, created_at)
                    VALUES (?, 'test-hash', 'basic', ?)
                    """,
                    [username, created_at],
                )
            for index, created_at in enumerate(
                [today, today, today, rolling_week, older],
                start=1,
            ):
                db.execute(
                    """
                    INSERT INTO vocabulary_entries
                        (word, definition, context, created_by, created_at)
                    VALUES (?, ?, 'Admin', ?, ?)
                    """,
                    [
                        f"summaryword{index}",
                        f"Definition {index}",
                        admin_id,
                        created_at,
                    ],
                )
        self.logout()
        self.login("tuomo")

        response = self.client.get("/admin")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"New users today", response.data)
        self.assertIn(b"New users last 7 days", response.data)
        self.assertIn(b"New vocabulary entries today", response.data)
        self.assertIn(b"New vocabulary entries last 7 days", response.data)
        self.assertIn(b"Pending requests", response.data)
        self.assertIn(b"Active invite codes", response.data)
        self.assertIn(b"Users at AI quota", response.data)
        self.assertIn(b"<strong>1</strong>", response.data)
        self.assertIn(b"<strong>2</strong>", response.data)
        self.assertIn(b"<strong>3</strong>", response.data)
        self.assertIn(b"<strong>4</strong>", response.data)

    def test_admin_page_shows_clean_dependency_security_report(self):
        self.write_security_report(
            {
                "dependencies": [
                    {"name": "flask", "version": "3.1.3", "vulns": []},
                    {"name": "werkzeug", "version": "3.1.8", "vulns": []},
                ],
                "fixes": [],
            }
        )
        self.create_admin("tuomo")
        self.logout()
        self.login("tuomo")

        response = self.client.get("/admin")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Dependency security report", response.data)
        self.assertIn(b"last run", response.data)
        self.assertIn(b"2 dependencies checked.", response.data)
        self.assertIn(b"0 vulnerabilities found.", response.data)
        self.assertIn(b"No dependency vulnerabilities", response.data)

    def test_admin_page_shows_run_security_audit_button(self):
        self.create_admin("tuomo")
        self.logout()
        self.login("tuomo")

        response = self.client.get("/admin")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"/admin/security-report/run", response.data)
        self.assertIn(b"Run security audit", response.data)

    def test_admin_vocabulary_maintenance_requires_admin(self):
        self.register("anna")

        response = self.client.get("/admin/vocabulary-maintenance", follow_redirects=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Admin account is required", response.data)

    def test_admin_vocabulary_maintenance_shows_entries_needing_cloze_data(self):
        self.create_admin("tuomo")
        self.logout()
        self.login("tuomo")
        self.create_vocab("alpha")

        response = self.client.get("/admin/vocabulary-maintenance")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Vocabulary maintenance", response.data)
        self.assertIn(b"alpha", response.data)
        self.assertIn(b"Generate missing", response.data)

    def test_admin_vocabulary_maintenance_shows_entry_missing_only_domains(self):
        self.create_admin("tuomo")
        self.logout()
        self.login("tuomo")
        entry = self.valid_cloze_entry("tenuous")
        entry["domains"] = []
        self.client.post("/vocabulary", json=entry)

        response = self.client.get("/admin/vocabulary-maintenance")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"tenuous", response.data)
        self.assertIn(b'name="domains"', response.data)

    def test_admin_vocabulary_maintenance_all_view_shows_complete_entries(self):
        self.create_admin("tuomo")
        self.logout()
        self.login("tuomo")
        self.create_vocab("alpha")
        self.create_cloze_vocab("tenuous")

        missing_response = self.client.get("/admin/vocabulary-maintenance")
        all_response = self.client.get(
            "/admin/vocabulary-maintenance",
            query_string={"view": "all"},
        )

        self.assertEqual(missing_response.status_code, 200)
        self.assertIn(b"alpha", missing_response.data)
        self.assertNotIn(b"tenuous", missing_response.data)
        self.assertEqual(all_response.status_code, 200)
        self.assertIn(b"alpha", all_response.data)
        self.assertIn(b"tenuous", all_response.data)
        self.assertIn(b"All vocabulary", all_response.data)
        self.assertIn(
            b"/admin/vocabulary/",
            all_response.data,
        )
        self.assertIn(b"/cloze-data?view=all", all_response.data)

    def test_admin_maintenance_save_preserves_all_view(self):
        self.create_admin("tuomo")
        self.logout()
        self.login("tuomo")
        vocabulary_id = self.create_cloze_vocab("tenuous").get_json()["id"]

        response = self.client.post(
            f"/admin/vocabulary/{vocabulary_id}/cloze-data?view=all",
            data={
                "csrf_token": self.csrf_token(),
                "part_of_speech": "adjective",
                "domains": ["cognition"],
                "cloze_sentences": "\n".join(
                    self.valid_cloze_entry("tenuous")["cloze_sentences"]
                ),
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.headers["Location"],
            "/admin/vocabulary-maintenance?view=all",
        )

    def test_admin_maintenance_form_persists_selected_domains(self):
        self.create_admin("tuomo")
        self.logout()
        self.login("tuomo")
        entry = self.valid_cloze_entry("tenuous")
        entry["domains"] = []
        vocabulary_id = self.client.post("/vocabulary", json=entry).get_json()["id"]

        response = self.client.post(
            f"/admin/vocabulary/{vocabulary_id}/cloze-data?view=all",
            data={
                "csrf_token": self.csrf_token(),
                "part_of_speech": "adjective",
                "domains": ["quality", "reasoning"],
                "cloze_sentences": "\n".join(entry["cloze_sentences"]),
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        with self.app.app_context():
            domains = [
                row["domain"]
                for row in db.query(
                    """
                    SELECT domain
                    FROM vocabulary_domains
                    WHERE vocabulary_id = ?
                    ORDER BY domain_order
                    """,
                    [vocabulary_id],
                )
            ]
        self.assertEqual(domains, ["quality", "reasoning"])
        html = response.get_data(as_text=True)
        self.assertRegex(html, r'value="quality"\s+checked')
        self.assertRegex(html, r'value="reasoning"\s+checked')
        self.assertIn(
            b"Updated part of speech, domains, and cloze data for tenuous.",
            response.data,
        )

    def test_admin_can_update_vocabulary_cloze_data(self):
        self.create_admin("tuomo")
        self.logout()
        self.login("tuomo")
        vocabulary_id = self.create_vocab("tenuous").get_json()["id"]

        response = self.client.post(
            f"/admin/vocabulary/{vocabulary_id}/cloze-data",
            json={
                "part_of_speech": "adjective",
                "domains": ["cognition", "rhetoric"],
                "cloze_sentences": [
                    "The argument rested on a ____ assumption.",
                    "The evidence showed only a ____ connection.",
                ],
            },
            headers=self.csrf_headers(),
        )

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["part_of_speech"], "adjective")
        self.assertEqual(body["domains"], ["cognition", "rhetoric"])
        self.assertEqual(len(body["cloze_sentences"]), 2)

    def test_admin_update_vocabulary_cloze_data_rejects_missing_csrf_token(self):
        self.create_admin("tuomo")
        self.logout()
        self.login("tuomo")
        vocabulary_id = self.create_vocab("tenuous").get_json()["id"]

        response = self.client.post(
            f"/admin/vocabulary/{vocabulary_id}/cloze-data",
            json={
                "part_of_speech": "adjective",
                "cloze_sentences": ["The argument rested on a ____ assumption."],
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "Invalid CSRF token")

    def test_admin_update_vocabulary_cloze_data_validates_sentence_blank(self):
        self.create_admin("tuomo")
        self.logout()
        self.login("tuomo")
        vocabulary_id = self.create_vocab("tenuous").get_json()["id"]

        response = self.client.post(
            f"/admin/vocabulary/{vocabulary_id}/cloze-data",
            json={
                "part_of_speech": "adjective",
                "cloze_sentences": ["The argument rested on a tenuous assumption."],
            },
            headers=self.csrf_headers(),
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.get_json()["error"],
            "Each cloze sentence must contain exactly one ____ blank",
        )

    def test_admin_can_generate_missing_vocabulary_cloze_data(self):
        self.create_admin("tuomo")
        self.logout()
        self.login("tuomo")
        vocabulary_id = self.create_vocab("tenuous").get_json()["id"]
        generated_data = {
            "part_of_speech": "adjective",
            "domains": ["cognition", "communication"],
            "cloze_sentences": [
                "The argument rested on a ____ assumption.",
                "The evidence showed only a ____ connection.",
            ],
        }

        with patch(
            "Views.admin.vocabulary_ai_service.generate_cloze_data",
            return_value=(generated_data, None),
        ) as generate_cloze_data:
            response = self.client.post(
                f"/admin/vocabulary/{vocabulary_id}/generate-cloze-data",
                json={},
                headers=self.csrf_headers(),
            )

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["part_of_speech"], "adjective")
        self.assertEqual(body["domains"], ["cognition", "communication"])
        self.assertEqual(body["cloze_sentences"], generated_data["cloze_sentences"])
        generate_cloze_data.assert_called_once()

    def test_admin_generate_cloze_data_preserves_existing_valid_manual_data(self):
        self.create_admin("tuomo")
        self.logout()
        self.login("tuomo")
        vocabulary_id = self.create_cloze_vocab("tenuous").get_json()["id"]
        generated_data = {
            "part_of_speech": "noun",
            "domains": ["communication"],
            "cloze_sentences": [
                "Generated ____ should not replace manual data.",
                "Another generated ____ should stay unused.",
            ],
        }

        with patch(
            "Views.admin.vocabulary_ai_service.generate_cloze_data",
            return_value=(generated_data, None),
        ):
            response = self.client.post(
                f"/admin/vocabulary/{vocabulary_id}/generate-cloze-data",
                json={},
                headers=self.csrf_headers(),
            )

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["part_of_speech"], "adjective")
        self.assertEqual(body["domains"], ["cognition"])
        self.assertEqual(
            body["cloze_sentences"],
            self.valid_cloze_entry("tenuous")["cloze_sentences"],
        )

    def test_admin_can_run_security_audit(self):
        self.create_admin("tuomo")
        self.logout()
        self.login("tuomo")

        with patch(
            "Views.admin.security_report_service.generate_report",
            return_value=(True, None),
        ) as generate_report:
            response = self.client.post(
                "/admin/security-report/run",
                headers=self.csrf_headers(),
                follow_redirects=True,
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Generated dependency security report.", response.data)
        generate_report.assert_called_once_with(
            self.security_report_file.name,
            self.app.root_path,
        )

    def test_admin_run_security_audit_rejects_missing_csrf_token(self):
        self.create_admin("tuomo")
        self.logout()
        self.login("tuomo")

        response = self.client.post("/admin/security-report/run")

        self.assertEqual(response.status_code, 302)
        with patch(
            "Views.admin.security_report_service.generate_report",
            return_value=(True, None),
        ) as generate_report:
            self.client.post("/admin/security-report/run")
        generate_report.assert_not_called()

    def test_non_admin_cannot_run_security_audit(self):
        self.create_admin("tuomo")
        self.register("anna")

        response = self.client.post(
            "/admin/security-report/run",
            headers=self.csrf_headers(),
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()["error"], "Admin account is required")

    def test_admin_page_shows_dependency_vulnerabilities(self):
        self.write_security_report(
            {
                "dependencies": [
                    {
                        "name": "example-package",
                        "version": "1.0.0",
                        "vulns": [
                            {
                                "id": "PYSEC-2026-1",
                                "description": "Unsafe example dependency",
                                "fix_versions": ["1.0.1"],
                            }
                        ],
                    },
                ],
                "fixes": [],
            }
        )
        self.create_admin("tuomo")
        self.logout()
        self.login("tuomo")

        response = self.client.get("/admin")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"example-package", response.data)
        self.assertIn(b"PYSEC-2026-1", response.data)
        self.assertIn(b"Unsafe example dependency", response.data)
        self.assertIn(b"Fix: 1.0.1", response.data)

    def test_admin_page_handles_missing_dependency_security_report(self):
        os.unlink(self.security_report_file.name)
        self.create_admin("tuomo")
        self.logout()
        self.login("tuomo")

        response = self.client.get("/admin")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Security report has not been generated yet.", response.data)

    def test_admin_page_hides_used_invite_codes(self):
        self.create_admin("tuomo")
        used_code = self.create_invite_code()
        unused_code = self.create_invite_code()
        self.logout()
        self.client.post(
            "/register",
            json={
                "username": "anna",
                "password": "AdminSafe12!",
                "invite_code": used_code,
            },
            headers=self.registration_csrf_headers(),
        )
        self.logout()
        self.login("tuomo")

        response = self.client.get("/admin")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn(used_code.encode(), response.data)
        self.assertIn(unused_code.encode(), response.data)

    def test_admin_page_hides_expired_invite_codes(self):
        self.create_admin("tuomo")
        expired_code = self.create_invite_code(
            datetime.now(timezone.utc) - timedelta(days=1)
        )
        valid_code = self.create_invite_code(
            datetime.now(timezone.utc) + timedelta(days=1)
        )
        self.logout()
        self.login("tuomo")

        response = self.client.get("/admin")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn(expired_code.encode(), response.data)
        self.assertIn(valid_code.encode(), response.data)

    def test_admin_can_generate_invite_code_valid_for_five_days(self):
        self.create_admin("tuomo")
        self.logout()
        self.login("tuomo")

        response = self.client.post(
            "/admin/invite-codes",
            json={},
            headers=self.csrf_headers(),
        )

        self.assertEqual(response.status_code, 201)
        body = response.get_json()
        self.assertGreaterEqual(len(body["code"]), 24)
        expires_at = datetime.fromisoformat(body["expires_at"])
        expected_expiry = datetime.now(timezone.utc) + timedelta(days=5)
        self.assertLess(abs(expires_at - expected_expiry), timedelta(seconds=5))
        self.assertEqual(self.invite_codes()[0]["code"], body["code"])

    def test_admin_invite_code_generation_deletes_expired_codes(self):
        self.create_admin("tuomo")
        expired_code = self.create_invite_code(
            datetime.now(timezone.utc) - timedelta(days=1)
        )
        valid_code = self.create_invite_code(
            datetime.now(timezone.utc) + timedelta(days=1)
        )
        self.logout()
        self.login("tuomo")

        response = self.client.post(
            "/admin/invite-codes",
            json={},
            headers=self.csrf_headers(),
        )

        self.assertEqual(response.status_code, 201)
        codes = [invite_code["code"] for invite_code in self.invite_codes()]
        self.assertNotIn(expired_code, codes)
        self.assertIn(valid_code, codes)
        self.assertIn(response.get_json()["code"], codes)

    def test_basic_user_cannot_generate_invite_code(self):
        self.register("anna")
        invite_code_count = len(self.invite_codes())

        response = self.client.post("/admin/invite-codes", json={})

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()["error"], "Admin account is required")
        self.assertEqual(len(self.invite_codes()), invite_code_count)

    def test_admin_generate_invite_code_rejects_missing_csrf_token(self):
        self.create_admin("tuomo")
        self.logout()
        self.login("tuomo")

        response = self.client.post("/admin/invite-codes", json={})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "Invalid CSRF token")
        self.assertEqual(self.invite_codes(), [])

    def test_admin_can_promote_basic_user_to_trusted(self):
        self.create_admin("tuomo")
        user_response = self.register("anna")
        self.logout()
        self.login("tuomo")

        response = self.client.post(
            f"/admin/users/{user_response.get_json()['id']}/category",
            json={"account_category": "trusted"},
            headers=self.csrf_headers(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["account_category"], "trusted")
        self.assertEqual(self.user_categories()["anna"], "trusted")
        self.assertEqual(self.user_categories()["tuomo"], "admin")

    def test_admin_can_demote_trusted_user_to_basic(self):
        self.create_admin("tuomo")
        user_response = self.register("anna")
        self.logout()
        self.login("tuomo")
        self.client.post(
            f"/admin/users/{user_response.get_json()['id']}/category",
            json={"account_category": "trusted"},
            headers=self.csrf_headers(),
        )

        response = self.client.post(
            f"/admin/users/{user_response.get_json()['id']}/category",
            json={"account_category": "basic"},
            headers=self.csrf_headers(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["account_category"], "basic")
        self.assertEqual(self.user_categories()["anna"], "basic")

    def test_admin_cannot_promote_user_to_admin(self):
        self.create_admin("tuomo")
        user_response = self.register("anna")
        self.logout()
        self.login("tuomo")

        response = self.client.post(
            f"/admin/users/{user_response.get_json()['id']}/category",
            json={"account_category": "admin"},
            headers=self.csrf_headers(),
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "Invalid account category")
        self.assertEqual(self.user_categories()["anna"], "basic")

    def test_basic_user_cannot_change_categories(self):
        basic_response = self.register("anna")
        target_response = self.register("mika")

        response = self.client.post(
            f"/admin/users/{target_response.get_json()['id']}/category",
            json={"account_category": "trusted"},
        )

        self.assertEqual(basic_response.get_json()["account_category"], "basic")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()["error"], "Admin account is required")
        self.assertEqual(self.user_categories()["mika"], "basic")

    def test_admin_cannot_change_admin_category(self):
        self.create_admin("tuomo")
        self.login("tuomo")
        with self.app.app_context():
            admin_id = db.query(
                "SELECT id FROM users WHERE username = ?",
                ["tuomo"],
            )[0]["id"]

        response = self.client.post(
            f"/admin/users/{admin_id}/category",
            json={"account_category": "basic"},
            headers=self.csrf_headers(),
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "Admin users cannot be changed here")
        self.assertEqual(self.user_categories()["tuomo"], "admin")

    def test_stale_admin_session_cannot_change_categories_after_demoted_in_database(self):
        self.create_admin("tuomo")
        user_response = self.register("anna")
        self.logout()
        self.login("tuomo")
        headers = self.csrf_headers()
        with self.app.app_context():
            db.execute(
                "UPDATE users SET account_category = ? WHERE username = ?",
                ["trusted", "tuomo"],
            )

        response = self.client.post(
            f"/admin/users/{user_response.get_json()['id']}/category",
            json={"account_category": "trusted"},
            headers=headers,
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()["error"], "Admin account is required")
        self.assertEqual(self.user_categories()["anna"], "basic")

    def test_admin_category_change_rejects_missing_csrf_token(self):
        self.create_admin("tuomo")
        user_response = self.register("anna")
        self.logout()
        self.login("tuomo")

        response = self.client.post(
            f"/admin/users/{user_response.get_json()['id']}/category",
            json={"account_category": "trusted"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "Invalid CSRF token")
        self.assertEqual(self.user_categories()["anna"], "basic")

    def test_admin_vocab_deletion_requires_confirmation(self):
        self.create_admin("tuomo")
        user_response = self.register("anna")
        user_id = user_response.get_json()["id"]
        self.logout()
        self.login("tuomo")
        self.client.post(
            f"/admin/users/{user_id}/category",
            json={"account_category": "trusted"},
            headers=self.csrf_headers(),
        )
        self.logout()
        self.login("anna")
        self.create_vocab("alpha")
        self.logout()
        self.login("tuomo")

        response = self.client.get("/admin")

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            f'/admin/users/{user_id}/vocabs/delete/confirm'.encode(),
            response.data,
        )

        response = self.client.get(
            f"/admin/users/{user_id}/vocabs/delete/confirm",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            b"You are about to permanently remove all",
            response.data,
        )
        self.assertIn(b"<strong>1</strong>", response.data)
        self.assertIn(b"<strong>anna</strong>", response.data)
        self.assertIn(b"This action cannot be undone.", response.data)
        self.assertIn(b'name="confirmed" value="yes"', response.data)

    def test_admin_cannot_remove_user_vocabs_without_confirmation(self):
        self.create_admin("tuomo")
        user_response = self.register("anna")
        user_id = user_response.get_json()["id"]
        self.logout()
        self.login("tuomo")
        self.client.post(
            f"/admin/users/{user_id}/category",
            json={"account_category": "trusted"},
            headers=self.csrf_headers(),
        )
        self.logout()
        self.login("anna")
        self.create_vocab("alpha")
        self.logout()
        self.login("tuomo")

        response = self.client.post(
            f"/admin/users/{user_id}/vocabs/delete",
            json={},
            headers=self.csrf_headers(),
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.get_json()["error"],
            "Vocabulary deletion must be confirmed",
        )
        with self.app.app_context():
            vocab_count = db.query(
                """
                SELECT COUNT(*) AS count
                FROM vocabulary_entries
                WHERE created_by = ?
                """,
                [user_id],
            )[0]["count"]
        self.assertEqual(vocab_count, 1)

    def test_admin_can_remove_all_vocabs_created_by_user(self):
        self.create_admin("tuomo")
        user_response = self.register("anna")
        user_id = user_response.get_json()["id"]
        self.logout()
        self.login("tuomo")
        self.client.post(
            f"/admin/users/{user_id}/category",
            json={"account_category": "trusted"},
            headers=self.csrf_headers(),
        )
        self.logout()
        self.login("anna")
        first_vocab_id = self.create_vocab("alpha").get_json()["id"]
        self.create_vocab("beta")
        self.logout()
        self.login("tuomo")
        training_response = self.client.post(
            "/training",
            json={"vocabulary_ids": [first_vocab_id]},
        )

        response = self.client.post(
            f"/admin/users/{user_id}/vocabs/delete",
            json={"confirmed": True},
            headers=self.csrf_headers(),
        )

        self.assertEqual(training_response.status_code, 201)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["deleted_vocabulary_count"], 2)
        with self.app.app_context():
            vocab_count = db.query(
                """
                SELECT COUNT(*) AS count
                FROM vocabulary_entries
                WHERE created_by = ?
                """,
                [user_id],
            )[0]["count"]
            training_count = db.query(
                """
                SELECT COUNT(*) AS count
                FROM training_sessions
                WHERE id = ?
                """,
                [training_response.get_json()["id"]],
            )[0]["count"]

        self.assertEqual(vocab_count, 0)
        self.assertEqual(training_count, 0)

    def test_admin_can_remove_user_vocabs_with_cloze_sentences(self):
        self.create_admin("tuomo")
        user_response = self.register("anna")
        user_id = user_response.get_json()["id"]
        self.logout()
        self.login("tuomo")
        self.client.post(
            f"/admin/users/{user_id}/category",
            json={"account_category": "trusted"},
            headers=self.csrf_headers(),
        )
        self.logout()
        self.login("anna")
        vocab_id = self.create_cloze_vocab("tenuous").get_json()["id"]
        self.logout()
        self.login("tuomo")

        response = self.client.post(
            f"/admin/users/{user_id}/vocabs/delete",
            json={"confirmed": True},
            headers=self.csrf_headers(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["deleted_vocabulary_count"], 1)
        with self.app.app_context():
            vocab_count = db.query(
                "SELECT COUNT(*) AS count FROM vocabulary_entries WHERE id = ?",
                [vocab_id],
            )[0]["count"]
            cloze_count = db.query(
                """
                SELECT COUNT(*) AS count
                FROM vocabulary_cloze_sentences
                WHERE vocabulary_id = ?
                """,
                [vocab_id],
            )[0]["count"]

        self.assertEqual(vocab_count, 0)
        self.assertEqual(cloze_count, 0)

    def test_admin_cannot_remove_admin_user_vocabs(self):
        self.create_admin("tuomo")
        self.logout()
        self.login("tuomo")
        admin_id = self.create_vocab("adminword").get_json()["created_by"]

        response = self.client.post(
            f"/admin/users/{admin_id}/vocabs/delete",
            json={"confirmed": True},
            headers=self.csrf_headers(),
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.get_json()["error"],
            "Admin vocabulary entries cannot be removed here",
        )

    def test_basic_user_cannot_remove_user_vocabs(self):
        target_response = self.register("anna")
        self.register("mika")

        response = self.client.post(
            f"/admin/users/{target_response.get_json()['id']}/vocabs/delete",
            json={},
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()["error"], "Admin account is required")

    def test_admin_delete_vocabs_rejects_invalid_csrf_token(self):
        self.create_admin("tuomo")
        target_response = self.register("anna")
        self.logout()
        self.login("tuomo")

        response = self.client.post(
            f"/admin/users/{target_response.get_json()['id']}/vocabs/delete",
            json={},
            headers={"X-CSRF-Token": "wrong-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "Invalid CSRF token")

    def test_admin_can_reset_user_ai_generation_quota(self):
        self.create_admin("tuomo")
        target_response = self.register("anna")
        target_user_id = target_response.get_json()["id"]
        self.set_ai_generation_count(target_user_id, 12)
        self.logout()
        self.login("tuomo")

        response = self.client.post(
            f"/admin/users/{target_user_id}/ai-quota/reset",
            json={},
            headers=self.csrf_headers(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["ai_generation_count"], 0)
        self.assertEqual(self.ai_generation_count(target_user_id), 0)

    def test_admin_reset_ai_generation_quota_rejects_missing_csrf_token(self):
        self.create_admin("tuomo")
        target_response = self.register("anna")
        target_user_id = target_response.get_json()["id"]
        self.set_ai_generation_count(target_user_id, 12)
        self.logout()
        self.login("tuomo")

        response = self.client.post(
            f"/admin/users/{target_user_id}/ai-quota/reset",
            json={},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "Invalid CSRF token")
        self.assertEqual(self.ai_generation_count(target_user_id), 12)


if __name__ == "__main__":
    unittest.main()
