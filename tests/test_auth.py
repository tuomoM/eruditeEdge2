import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

import db
from app import create_app
from csrf import CSRF_SESSION_KEY
from db import init_db
from Services.user_service import user_service


class AuthTestCase(unittest.TestCase):
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

    def register(self, username, password):
        invite_code = self.create_invite_code()
        return self.client.post(
            "/register",
            json={
                "username": username,
                "password": password,
                "invite_code": invite_code,
            },
            headers=self.registration_csrf_headers(),
        )

    def login(self, username, password):
        return self.client.post(
            "/login",
            json={"username": username, "password": password},
        )

    def registration_csrf_headers(self):
        with self.client.session_transaction() as session:
            session[CSRF_SESSION_KEY] = "test-registration-csrf-token"
        return {"X-CSRF-Token": "test-registration-csrf-token"}

    def user_categories(self):
        with self.app.app_context():
            rows = db.query(
                """
                SELECT username, account_category
                FROM users
                ORDER BY username
                """
            )
        return {
            row["username"]: row["account_category"]
            for row in rows
        }

    def invite_creator_id(self):
        with self.app.app_context():
            rows = db.query("SELECT id FROM users ORDER BY id LIMIT 1")
            if rows:
                return rows[0]["id"]
            admin_user, error = user_service.create_admin("invite_issuer", "safe-password")
            self.assertIsNone(error)
            return admin_user["id"]

    def create_invite_code(self, code=None, expires_at=None):
        expires_at = expires_at or datetime.now(timezone.utc) + timedelta(days=5)
        with self.app.app_context():
            if code is None:
                count = db.query("SELECT COUNT(*) AS count FROM invite_codes")[0]["count"]
                code = f"test-invite-code-{count + 1}"
            db.execute(
                """
                INSERT INTO invite_codes (code, created_by, expires_at)
                VALUES (?, ?, ?)
                """,
                [code, self.invite_creator_id(), expires_at.isoformat()],
            )
        return code

    def test_user_creation_succeeds(self):
        response = self.register("tuomo", "safe-password")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["username"], "tuomo")

    def test_user_creation_requires_invite_code(self):
        response = self.client.post(
            "/register",
            json={"username": "tuomo", "password": "safe-password"},
            headers=self.registration_csrf_headers(),
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "Invite code is required")

    def test_user_creation_requires_csrf_token(self):
        invite_code = self.create_invite_code("csrf-required-code")

        response = self.client.post(
            "/register",
            json={
                "username": "tuomo",
                "password": "safe-password",
                "invite_code": invite_code,
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "Invalid CSRF token")

    def test_user_creation_rejects_invalid_csrf_token(self):
        invite_code = self.create_invite_code("csrf-invalid-code")
        with self.client.session_transaction() as session:
            session[CSRF_SESSION_KEY] = "valid-token"

        response = self.client.post(
            "/register",
            json={
                "username": "tuomo",
                "password": "safe-password",
                "invite_code": invite_code,
            },
            headers={"X-CSRF-Token": "wrong-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "Invalid CSRF token")

    def test_user_creation_rejects_invalid_invite_code(self):
        response = self.client.post(
            "/register",
            json={
                "username": "tuomo",
                "password": "safe-password",
                "invite_code": "missing-code",
            },
            headers=self.registration_csrf_headers(),
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "Invite code is invalid or expired")

    def test_invalid_invite_code_does_not_reveal_existing_username(self):
        self.register("tuomo", "safe-password")

        response = self.client.post(
            "/register",
            json={
                "username": "tuomo",
                "password": "another-safe-password",
                "invite_code": "missing-code",
            },
            headers=self.registration_csrf_headers(),
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "Invite code is invalid or expired")

    def test_user_creation_rejects_expired_invite_code(self):
        invite_code = self.create_invite_code(
            "expired-code",
            datetime.now(timezone.utc) - timedelta(seconds=1),
        )

        response = self.client.post(
            "/register",
            json={
                "username": "tuomo",
                "password": "safe-password",
                "invite_code": invite_code,
            },
            headers=self.registration_csrf_headers(),
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "Invite code is invalid or expired")

    def test_user_creation_marks_invite_code_as_used(self):
        invite_code = self.create_invite_code("single-use-code")

        response = self.client.post(
            "/register",
            json={
                "username": "tuomo",
                "password": "safe-password",
                "invite_code": invite_code,
            },
            headers=self.registration_csrf_headers(),
        )

        self.assertEqual(response.status_code, 201)
        with self.app.app_context():
            rows = db.query(
                """
                SELECT users.username AS used_by_username, invite_codes.used_at
                FROM invite_codes
                JOIN users ON users.id = invite_codes.used_by
                WHERE invite_codes.code = ?
                """,
                [invite_code],
            )
        self.assertEqual(rows[0]["used_by_username"], "tuomo")
        self.assertIsNotNone(rows[0]["used_at"])

    def test_user_creation_rejects_reused_invite_code(self):
        invite_code = self.create_invite_code("reuse-code")

        first_response = self.client.post(
            "/register",
            json={
                "username": "tuomo",
                "password": "safe-password",
                "invite_code": invite_code,
            },
            headers=self.registration_csrf_headers(),
        )
        second_response = self.client.post(
            "/register",
            json={
                "username": "anna",
                "password": "safe-password",
                "invite_code": invite_code,
            },
            headers=self.registration_csrf_headers(),
        )

        self.assertEqual(first_response.status_code, 201)
        self.assertEqual(second_response.status_code, 400)
        self.assertEqual(second_response.get_json()["error"], "Invite code is invalid or expired")

    def test_registered_user_is_basic(self):
        response = self.register("tuomo", "safe-password")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["account_category"], "basic")

    def test_later_registered_users_are_basic(self):
        self.register("tuomo", "safe-password")

        response = self.register("anna", "safe-password")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["account_category"], "basic")

    def test_user_creation_does_not_allow_sql_injection(self):
        response = self.register("' OR 1=1 --", "safe-password")

        self.assertEqual(response.status_code, 400)

    def test_user_creation_does_not_allow_user_id_shorter_than_two_characters(self):
        response = self.register("a", "safe-password")

        self.assertEqual(response.status_code, 400)

    def test_user_creation_does_not_allow_empty_password(self):
        response = self.register("tuomo", "")

        self.assertEqual(response.status_code, 400)

    def test_user_creation_does_not_allow_password_same_as_user_id(self):
        response = self.register("tuomo", "tuomo")

        self.assertEqual(response.status_code, 400)

    def test_user_creation_does_not_allow_password_shorter_than_four_characters(self):
        response = self.register("tuomo", "abc")

        self.assertEqual(response.status_code, 400)

    def test_login_succeeds_with_correct_user_id_and_password(self):
        self.register("tuomo", "safe-password")

        response = self.login("tuomo", "safe-password")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["username"], "tuomo")
        self.assertEqual(response.get_json()["account_category"], "basic")

    def test_login_fails_with_incorrect_password(self):
        self.register("tuomo", "safe-password")

        response = self.login("tuomo", "wrong-password")

        self.assertEqual(response.status_code, 401)

    def test_login_does_not_allow_sql_injection(self):
        self.register("tuomo", "safe-password")

        response = self.login("' OR 1=1 --", "anything")

        self.assertEqual(response.status_code, 401)

    def test_admin_can_elevate_user_to_trusted(self):
        with self.app.app_context():
            admin_user, error = user_service.create_admin("tuomo", "safe-password")
        self.assertIsNone(error)
        user_response = self.register("anna", "safe-password")

        with self.app.app_context():
            updated_user, error = user_service.update_account_category(
                admin_user["id"],
                user_response.get_json()["id"],
                "trusted",
            )

        self.assertIsNone(error)
        self.assertEqual(updated_user["account_category"], "trusted")

    def test_admin_cannot_elevate_user_to_admin(self):
        with self.app.app_context():
            admin_user, error = user_service.create_admin("tuomo", "safe-password")
        self.assertIsNone(error)
        user_response = self.register("anna", "safe-password")

        with self.app.app_context():
            updated_user, error = user_service.update_account_category(
                admin_user["id"],
                user_response.get_json()["id"],
                "admin",
            )

        self.assertIsNone(updated_user)
        self.assertEqual(error, "Invalid account category")

    def test_non_admin_cannot_change_user_category(self):
        self.register("tuomo", "safe-password")
        basic_response = self.register("anna", "safe-password")
        target_response = self.register("mika", "safe-password")

        with self.app.app_context():
            updated_user, error = user_service.update_account_category(
                basic_response.get_json()["id"],
                target_response.get_json()["id"],
                "trusted",
            )

        self.assertIsNone(updated_user)
        self.assertEqual(error, "Admin account is required")

    def test_invalid_account_category_is_rejected(self):
        with self.app.app_context():
            admin_user, error = user_service.create_admin("tuomo", "safe-password")
        self.assertIsNone(error)
        user_response = self.register("anna", "safe-password")

        with self.app.app_context():
            updated_user, error = user_service.update_account_category(
                admin_user["id"],
                user_response.get_json()["id"],
                "owner",
            )

        self.assertIsNone(updated_user)
        self.assertEqual(error, "Invalid account category")

    def test_user_category_is_stored_in_database(self):
        self.register("tuomo", "safe-password")

        with self.app.app_context():
            rows = db.query(
                """
                SELECT account_category
                FROM users
                WHERE username = ?
                """,
                ["tuomo"],
            )

        self.assertEqual(rows[0]["account_category"], "basic")

    def test_create_admin_command_creates_new_admin_and_demotes_existing_admins(self):
        runner = self.app.test_cli_runner()
        runner.invoke(
            args=[
                "create-admin",
                "--username",
                "tuomo",
                "--password",
                "safe-password",
            ]
        )
        self.register("anna", "safe-password")

        result = runner.invoke(
            args=[
                "create-admin",
                "--username",
                "mika",
                "--password",
                "safe-password",
            ]
        )

        self.assertEqual(result.exit_code, 0)
        self.assertIn("Created admin user 'mika'", result.output)
        self.assertEqual(
            self.user_categories(),
            {
                "anna": "basic",
                "mika": "admin",
                "tuomo": "trusted",
            },
        )

    def test_create_admin_command_rejects_existing_username_without_demoting_admins(self):
        runner = self.app.test_cli_runner()
        runner.invoke(
            args=[
                "create-admin",
                "--username",
                "tuomo",
                "--password",
                "safe-password",
            ]
        )
        self.register("anna", "safe-password")

        result = runner.invoke(
            args=[
                "create-admin",
                "--username",
                "anna",
                "--password",
                "safe-password",
            ]
        )

        self.assertNotEqual(result.exit_code, 0)
        self.assertEqual(
            self.user_categories(),
            {
                "anna": "basic",
                "tuomo": "admin",
            },
        )


if __name__ == "__main__":
    unittest.main()
