import os
import tempfile
import unittest

import db
from app import create_app
from db import init_db


class AdminTestCase(unittest.TestCase):
    def setUp(self):
        self.database_file = tempfile.NamedTemporaryFile(delete=False)
        self.database_file.close()
        self.app = create_app(
            {
                "TESTING": True,
                "DATABASE": self.database_file.name,
                "SECRET_KEY": "test-secret-key",
            }
        )
        init_db(self.app)
        self.client = self.app.test_client()

    def tearDown(self):
        os.unlink(self.database_file.name)

    def register(self, username):
        return self.client.post(
            "/register",
            json={"username": username, "password": "safe-password"},
        )

    def create_admin(self, username="tuomo"):
        runner = self.app.test_cli_runner()
        result = runner.invoke(
            args=[
                "create-admin",
                "--username",
                username,
                "--password",
                "safe-password",
            ]
        )
        self.assertEqual(result.exit_code, 0)

    def login(self, username):
        return self.client.post(
            "/login",
            json={"username": username, "password": "safe-password"},
        )

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

    def create_vocab(self, word):
        return self.client.post("/vocabulary", json=self.valid_entry(word))

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
            json={},
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
