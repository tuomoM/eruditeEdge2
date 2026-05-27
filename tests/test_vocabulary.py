import os
import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime, timedelta, timezone

import db
from app import create_app
from csrf import CSRF_SESSION_KEY
from db import init_db


class VocabularyTestCase(unittest.TestCase):
    def setUp(self):
        self.database_file = tempfile.NamedTemporaryFile(delete=False)
        self.database_file.close()
        self.app = create_app(
            {
                "TESTING": True,
                "DATABASE": self.database_file.name,
                "SECRET_KEY": "test-secret-key",
                "OPENAI_API_KEY": "test-api-key",
                "OPENAI_MODEL": "test-model",
                "TRUSTED_AI_DAILY_QUOTA": 2,
            }
        )
        init_db(self.app)
        self.client = self.app.test_client()

    def tearDown(self):
        os.unlink(self.database_file.name)

    def login_user(self):
        invite_code = self.create_invite_code()
        self.client.post(
            "/register",
            json={
                "username": "tuomo",
                "password": "safe-password",
                "invite_code": invite_code,
            },
            headers=self.csrf_headers(),
        )
        self.set_user_category("tuomo", "trusted")

    def logout_user(self):
        self.client.post("/logout", json={})

    def login_second_user(self):
        invite_code = self.create_invite_code()
        self.client.post(
            "/register",
            json={
                "username": "anna",
                "password": "safe-password",
                "invite_code": invite_code,
            },
            headers=self.csrf_headers(),
        )

    def login_existing_second_user(self):
        self.client.post(
            "/login",
            json={"username": "anna", "password": "safe-password"},
        )

    def make_user_trusted(self, username):
        self.set_user_category(username, "trusted")

    def set_user_category(self, username, account_category):
        with self.app.app_context():
            db.execute(
                """
                UPDATE users
                SET account_category = ?
                WHERE username = ?
                """,
                [account_category, username],
            )

    def invite_creator_id(self):
        with self.app.app_context():
            rows = db.query("SELECT id FROM users ORDER BY id LIMIT 1")
            if rows:
                return rows[0]["id"]
            cursor = db.execute(
                """
                INSERT INTO users (username, password_hash, account_category)
                VALUES (?, ?, ?)
                """,
                ["invite_issuer", "not-used", "admin"],
            )
            return cursor.lastrowid

    def create_invite_code(self):
        creator_id = self.invite_creator_id()
        expires_at = datetime.now(timezone.utc) + timedelta(days=5)
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

    def csrf_headers(self):
        with self.client.session_transaction() as session:
            session[CSRF_SESSION_KEY] = "test-csrf-token"
        return {"X-CSRF-Token": "test-csrf-token"}

    def ai_generation_count(self, username):
        with self.app.app_context():
            rows = db.query(
                """
                SELECT ai_generation_usage.generation_count
                FROM ai_generation_usage
                JOIN users ON users.id = ai_generation_usage.user_id
                WHERE users.username = ? AND generation_date = DATE('now')
                """,
                [username],
            )
        if not rows:
            return 0
        return rows[0]["generation_count"]

    def valid_entry(self):
        return {
            "word": "operation",
            "definition": "A planned activity or procedure",
            "context": "Scientific/Medical",
            "synonyms": ["procedure", "process"],
            "examples": [
                "The operation required careful preparation.",
                "The doctor explained the operation to the patient.",
            ],
        }

    def create_entry(self, data=None):
        return self.client.post("/vocabulary", json=data or self.valid_entry())

    def create_entry_with_word(self, word):
        data = self.valid_entry()
        data["word"] = word
        data["definition"] = f"Definition for {word}"
        data["examples"] = [f"{word} appears in this sentence."]
        return self.create_entry(data)

    def generate_entry(self, word, include_csrf=True):
        headers = self.csrf_headers() if include_csrf else {}
        return self.client.post(
            "/vocabulary/generate",
            json={"word": word},
            headers=headers,
        )

    def search_entries(self, word):
        return self.client.get("/vocabulary/search", query_string={"word": word})

    def test_create_vocabulary_requires_login(self):
        response = self.create_entry()

        self.assertEqual(response.status_code, 401)

    def test_create_vocabulary_succeeds_when_logged_in(self):
        self.login_user()

        response = self.create_entry()

        self.assertEqual(response.status_code, 201)
        body = response.get_json()
        self.assertEqual(body["word"], "operation")
        self.assertEqual(body["context"], "Scientific/Medical")
        self.assertEqual(body["synonyms"], ["procedure", "process"])
        self.assertEqual(len(body["examples"]), 2)

    def test_different_users_cannot_create_duplicate_global_word_and_context(self):
        self.login_user()
        first_response = self.create_entry()
        self.logout_user()
        self.login_second_user()
        self.make_user_trusted("anna")
        self.logout_user()
        self.login_existing_second_user()

        second_response = self.create_entry()

        self.assertEqual(first_response.status_code, 201)
        self.assertEqual(second_response.status_code, 400)

    def test_create_vocabulary_rejects_sql_injection(self):
        self.login_user()
        data = self.valid_entry()
        data["word"] = "operation'; DROP TABLE users; --"

        response = self.create_entry(data)

        self.assertEqual(response.status_code, 400)

    def test_generate_vocabulary_requires_login(self):
        response = self.generate_entry("operation")

        self.assertEqual(response.status_code, 401)

    def test_generate_vocabulary_rejects_missing_csrf_token(self):
        self.login_user()

        response = self.generate_entry("operation", include_csrf=False)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "Invalid CSRF token")

    def test_generate_vocabulary_rejects_invalid_csrf_token(self):
        self.login_user()
        with self.client.session_transaction() as session:
            session[CSRF_SESSION_KEY] = "valid-token"

        response = self.client.post(
            "/vocabulary/generate",
            json={"word": "operation"},
            headers={"X-CSRF-Token": "wrong-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "Invalid CSRF token")

    def test_generate_vocabulary_succeeds_when_logged_in(self):
        self.login_user()
        generated_entry = self.valid_entry()

        with patch(
            "Views.vocabulary.vocabulary_ai_service.generate_entry",
            return_value=(generated_entry, None),
        ) as generate_entry:
            response = self.generate_entry("operation")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), generated_entry)
        generate_entry.assert_called_once_with(
            "operation",
            "test-api-key",
                "test-model",
        )

    def test_generate_vocabulary_accepts_semicolons_in_generated_prose(self):
        self.login_user()
        generated_entry = self.valid_entry()
        generated_entry["word"] = "stultify"
        generated_entry["definition"] = (
            "To cause someone to lose enthusiasm or initiative; to make ineffective."
        )
        generated_entry["examples"] = [
            "The rigid process stultified the team; it left no room for judgment."
        ]

        with patch(
            "Views.vocabulary.vocabulary_ai_service.generate_entry",
            return_value=(generated_entry, None),
        ):
            response = self.generate_entry("stultify")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), generated_entry)

    def test_generate_vocabulary_rejects_sql_injection(self):
        self.login_user()

        response = self.generate_entry("operation'; DROP TABLE users; --")

        self.assertEqual(response.status_code, 400)

    def test_generate_vocabulary_rejects_sql_keyword(self):
        self.login_user()

        response = self.generate_entry("DROP")

        self.assertEqual(response.status_code, 400)

    def test_generate_vocabulary_rejects_more_than_one_word(self):
        self.login_user()

        response = self.generate_entry("two words")

        self.assertEqual(response.status_code, 400)

    def test_generate_vocabulary_rejects_html_tags(self):
        self.login_user()

        response = self.generate_entry("<b>word</b>")

        self.assertEqual(response.status_code, 400)

    def test_trusted_user_cannot_generate_more_than_daily_quota(self):
        self.login_user()
        generated_entry = self.valid_entry()

        with patch(
            "Views.vocabulary.vocabulary_ai_service.generate_entry",
            return_value=(generated_entry, None),
        ) as generate_entry:
            first_response = self.generate_entry("first")
            second_response = self.generate_entry("second")
            third_response = self.generate_entry("third")

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 200)
        self.assertEqual(third_response.status_code, 429)
        self.assertEqual(
            third_response.get_json()["error"],
            "Daily AI generation quota reached (2)",
        )
        self.assertEqual(generate_entry.call_count, 2)

    def test_admin_user_has_unlimited_ai_generation_quota(self):
        self.login_user()
        self.set_user_category("tuomo", "admin")
        generated_entry = self.valid_entry()

        with patch(
            "Views.vocabulary.vocabulary_ai_service.generate_entry",
            return_value=(generated_entry, None),
        ) as generate_entry:
            responses = [
                self.generate_entry("first"),
                self.generate_entry("second"),
                self.generate_entry("third"),
            ]

        self.assertEqual([response.status_code for response in responses], [200, 200, 200])
        self.assertEqual(generate_entry.call_count, 3)

    def test_invalid_ai_generation_request_does_not_use_daily_quota(self):
        self.login_user()
        invalid_response = self.generate_entry("two words")
        generated_entry = self.valid_entry()

        with patch(
            "Views.vocabulary.vocabulary_ai_service.generate_entry",
            return_value=(generated_entry, None),
        ) as generate_entry:
            first_response = self.generate_entry("first")
            second_response = self.generate_entry("second")

        self.assertEqual(invalid_response.status_code, 400)
        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 200)
        self.assertEqual(generate_entry.call_count, 2)

    def test_failed_ai_generation_does_not_use_daily_quota(self):
        self.login_user()

        with patch(
            "Views.vocabulary.vocabulary_ai_service.generate_entry",
            return_value=(None, "OpenAI request failed: TimeoutError"),
        ) as generate_entry:
            failed_response = self.generate_entry("first")

        self.assertEqual(failed_response.status_code, 400)
        self.assertEqual(generate_entry.call_count, 1)
        self.assertEqual(self.ai_generation_count("tuomo"), 0)

    def test_invalid_generated_entry_does_not_use_daily_quota(self):
        self.login_user()
        generated_entry = self.valid_entry()
        generated_entry["definition"] = "<b>unsafe</b>"

        with patch(
            "Views.vocabulary.vocabulary_ai_service.generate_entry",
            return_value=(generated_entry, None),
        ) as generate_entry:
            failed_response = self.generate_entry("first")

        self.assertEqual(failed_response.status_code, 400)
        self.assertEqual(generate_entry.call_count, 1)
        self.assertEqual(self.ai_generation_count("tuomo"), 0)

    def test_basic_user_cannot_create_vocabulary(self):
        self.login_user()
        self.logout_user()
        self.login_second_user()

        response = self.create_entry()

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()["error"], "Trusted account is required")

    def test_basic_user_cannot_open_new_vocabulary_page(self):
        self.login_user()
        self.logout_user()
        self.login_second_user()

        response = self.client.get("/vocabulary/new", follow_redirects=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Trusted account is required", response.data)

    def test_basic_user_cannot_generate_vocabulary_with_ai(self):
        self.login_user()
        self.logout_user()
        self.login_second_user()

        response = self.generate_entry("operation")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()["error"], "Trusted account is required")

    def test_stale_trusted_session_cannot_create_vocabulary_after_demoted_in_database(self):
        self.login_user()
        self.set_user_category("tuomo", "basic")

        response = self.create_entry()

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()["error"], "Trusted account is required")

    def test_basic_user_cannot_check_ai_status(self):
        self.login_user()
        self.logout_user()
        self.login_second_user()

        response = self.client.get("/vocabulary/generate/status")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()["error"], "Trusted account is required")

    def test_create_vocabulary_rejects_html_tags(self):
        self.login_user()
        data = self.valid_entry()
        data["definition"] = "<b>unsafe</b>"

        response = self.create_entry(data)

        self.assertEqual(response.status_code, 400)

    def test_create_vocabulary_requires_one_to_four_examples(self):
        self.login_user()
        data = self.valid_entry()
        data["examples"] = []

        response = self.create_entry(data)

        self.assertEqual(response.status_code, 400)

    def test_create_vocabulary_rejects_more_than_four_examples(self):
        self.login_user()
        data = self.valid_entry()
        data["examples"] = ["one", "two", "three", "four", "five"]

        response = self.create_entry(data)

        self.assertEqual(response.status_code, 400)

    def test_view_vocabulary_requires_login(self):
        response = self.client.get("/vocabulary/1")

        self.assertEqual(response.status_code, 401)

    def test_view_vocabulary_succeeds_when_logged_in(self):
        self.login_user()
        create_response = self.create_entry()
        vocabulary_id = create_response.get_json()["id"]

        response = self.client.get(f"/vocabulary/{vocabulary_id}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["word"], "operation")

    def test_view_vocabulary_shows_another_users_entry_because_vocabs_are_global(self):
        self.login_user()
        create_response = self.create_entry()
        vocabulary_id = create_response.get_json()["id"]
        self.logout_user()
        self.login_second_user()

        response = self.client.get(f"/vocabulary/{vocabulary_id}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["word"], "operation")

    def test_view_vocabulary_does_not_allow_sql_injection(self):
        self.login_user()

        response = self.client.get("/vocabulary/1 OR 1=1")

        self.assertEqual(response.status_code, 404)

    def test_search_vocabulary_requires_login(self):
        response = self.search_entries("oper*")

        self.assertEqual(response.status_code, 401)

    def test_search_vocabulary_supports_wildcard_at_end(self):
        self.login_user()
        self.create_entry_with_word("operation")
        self.create_entry_with_word("operate")
        self.create_entry_with_word("cooperate")

        response = self.search_entries("oper*")

        self.assertEqual(response.status_code, 200)
        words = [entry["word"] for entry in response.get_json()]
        self.assertEqual(words, ["operate", "operation"])

    def test_search_vocabulary_supports_wildcard_at_beginning(self):
        self.login_user()
        self.create_entry_with_word("operation")
        self.create_entry_with_word("cooperation")
        self.create_entry_with_word("operate")

        response = self.search_entries("*tion")

        self.assertEqual(response.status_code, 200)
        words = [entry["word"] for entry in response.get_json()]
        self.assertEqual(words, ["cooperation", "operation"])

    def test_search_vocabulary_supports_wildcard_in_middle(self):
        self.login_user()
        self.create_entry_with_word("operation")
        self.create_entry_with_word("opinion")
        self.create_entry_with_word("option")

        response = self.search_entries("op*ion")

        self.assertEqual(response.status_code, 200)
        words = [entry["word"] for entry in response.get_json()]
        self.assertEqual(words, ["operation", "opinion", "option"])

    def test_search_vocabulary_rejects_sql_injection(self):
        self.login_user()

        response = self.search_entries("operation'; DROP TABLE users; --")

        self.assertEqual(response.status_code, 400)

    def test_search_vocabulary_does_not_crash_when_nothing_is_found(self):
        self.login_user()
        self.create_entry_with_word("operation")

        response = self.search_entries("missing*")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), [])

    def test_search_vocabulary_returns_another_users_entry_because_vocabs_are_global(self):
        self.login_user()
        self.create_entry_with_word("operation")
        self.logout_user()
        self.login_second_user()

        response = self.search_entries("oper*")

        self.assertEqual(response.status_code, 200)
        self.assertEqual([entry["word"] for entry in response.get_json()], ["operation"])

    def test_update_vocabulary_requires_login(self):
        response = self.client.put("/vocabulary/1", json=self.valid_entry())

        self.assertEqual(response.status_code, 401)

    def test_update_vocabulary_succeeds_when_logged_in(self):
        self.login_user()
        create_response = self.create_entry()
        vocabulary_id = create_response.get_json()["id"]
        data = self.valid_entry()
        data["definition"] = "A controlled activity"
        data["synonyms"] = ["activity"]
        data["examples"] = ["The operation was successful."]

        response = self.client.put(f"/vocabulary/{vocabulary_id}", json=data)

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["definition"], "A controlled activity")
        self.assertEqual(body["synonyms"], ["activity"])
        self.assertEqual(body["examples"], ["The operation was successful."])

    def test_update_vocabulary_can_update_another_users_entry_because_vocabs_are_global(self):
        self.login_user()
        create_response = self.create_entry()
        vocabulary_id = create_response.get_json()["id"]
        self.logout_user()
        self.login_second_user()
        self.make_user_trusted("anna")
        self.logout_user()
        self.login_existing_second_user()
        data = self.valid_entry()
        data["definition"] = "Updated global definition"

        response = self.client.put(f"/vocabulary/{vocabulary_id}", json=data)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["definition"], "Updated global definition")

    def test_basic_user_cannot_update_vocabulary(self):
        self.login_user()
        create_response = self.create_entry()
        vocabulary_id = create_response.get_json()["id"]
        self.logout_user()
        self.login_second_user()
        data = self.valid_entry()
        data["definition"] = "Updated global definition"

        response = self.client.put(f"/vocabulary/{vocabulary_id}", json=data)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()["error"], "Trusted account is required")

    def test_basic_user_cannot_open_edit_vocabulary_page(self):
        self.login_user()
        create_response = self.create_entry()
        vocabulary_id = create_response.get_json()["id"]
        self.logout_user()
        self.login_second_user()

        response = self.client.get(
            f"/vocabulary/{vocabulary_id}/edit",
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Trusted account is required", response.data)

    def test_update_vocabulary_rejects_sql_injection(self):
        self.login_user()
        create_response = self.create_entry()
        vocabulary_id = create_response.get_json()["id"]
        data = self.valid_entry()
        data["context"] = "Medical'; DROP TABLE users; --"

        response = self.client.put(f"/vocabulary/{vocabulary_id}", json=data)

        self.assertEqual(response.status_code, 400)

    def test_update_vocabulary_rejects_html_tags(self):
        self.login_user()
        create_response = self.create_entry()
        vocabulary_id = create_response.get_json()["id"]
        data = self.valid_entry()
        data["examples"] = ["<script>alert('x')</script>"]

        response = self.client.put(f"/vocabulary/{vocabulary_id}", json=data)

        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
