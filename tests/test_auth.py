import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

import db
from app import create_app
from csrf import CSRF_SESSION_KEY
from db import init_db
from Services.user_service import user_service
from werkzeug.security import generate_password_hash


class AuthTestCase(unittest.TestCase):
    def setUp(self):
        self.database_file = tempfile.NamedTemporaryFile(delete=False)
        self.database_file.close()
        self.app = create_app(
            {
                "TESTING": True,
                "DATABASE": self.database_file.name,
                "SECRET_KEY": "test-secret-key",
                "GOOGLE_CLIENT_ID": "google-client-id",
                "GOOGLE_CLIENT_SECRET": "google-client-secret",
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

    def registration_csrf_headers(self, base_url=None):
        session_kwargs = {}
        if base_url:
            session_kwargs["base_url"] = base_url
        with self.client.session_transaction(**session_kwargs) as session:
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

    def create_trusted_user_directly(self, username):
        with self.app.app_context():
            db.execute(
                """
                INSERT INTO users (username, password_hash, account_category)
                VALUES (?, ?, ?)
                """,
                [username, generate_password_hash("safe-password"), "trusted"],
            )

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

    def create_google_user(self, google_sub="google-sub-login", email="login@example.com"):
        invite_code = self.create_invite_code()
        with self.app.app_context():
            user_id, error = user_service.register_google_user(
                {
                    "sub": google_sub,
                    "email": email,
                    "email_verified": True,
                },
                invite_code,
            )
        self.assertIsNone(error)
        return user_id

    def test_user_creation_succeeds(self):
        response = self.register("tuomo", "safe-password")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["username"], "tuomo")

    def test_account_page_for_anonymous_user_shows_login_and_create_account(self):
        response = self.client.get("/account")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Log in or create an account", response.data)
        self.assertIn(b"Log in with Google", response.data)
        self.assertIn(b"Create account", response.data)
        self.assertIn(b"Request invite code", response.data)

    def test_account_page_for_logged_in_user_shows_logout(self):
        self.register("tuomo", "safe-password")

        response = self.client.get("/account")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"You are logged on as tuomo.", response.data)
        self.assertIn(b"Log out", response.data)
        self.assertNotIn(b"Create account", response.data)

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

    def test_google_registration_start_requires_invite_code(self):
        response = self.client.post(
            "/register/google",
            json={},
            headers=self.registration_csrf_headers(),
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "Invite code is required")

    def test_google_registration_start_requires_csrf_token(self):
        response = self.client.post(
            "/register/google",
            json={"invite_code": "some-code"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "Invalid CSRF token")

    def test_google_registration_start_returns_authorization_url(self):
        invite_code = self.create_invite_code("google-start-code")

        response = self.client.post(
            "/register/google",
            json={"invite_code": invite_code},
            headers=self.registration_csrf_headers(),
        )

        self.assertEqual(response.status_code, 200)
        authorization_url = response.get_json()["authorization_url"]
        self.assertIn("https://accounts.google.com/o/oauth2/v2/auth", authorization_url)
        self.assertIn("client_id=google-client-id", authorization_url)

    def test_google_registration_callback_uri_uses_https_for_public_hosts(self):
        invite_code = self.create_invite_code("google-start-https-code")
        base_url = "http://erudite-edge.example"

        response = self.client.post(
            "/register/google",
            json={"invite_code": invite_code},
            headers=self.registration_csrf_headers(base_url),
            base_url=base_url,
        )

        authorization_url = response.get_json()["authorization_url"]
        query = parse_qs(urlparse(authorization_url).query)
        self.assertEqual(
            query["redirect_uri"][0],
            "https://erudite-edge.example/register/google/callback",
        )

    def test_google_registration_callback_creates_user_with_invite_code(self):
        invite_code = self.create_invite_code("google-callback-code")
        start_response = self.client.post(
            "/register/google",
            json={"invite_code": invite_code},
            headers=self.registration_csrf_headers(),
        )
        authorization_url = start_response.get_json()["authorization_url"]
        state = authorization_url.split("state=", 1)[1].split("&", 1)[0]

        with patch(
            "Views.user.google_oauth_service.fetch_user_info",
            return_value=(
                {
                    "sub": "google-sub-1",
                    "email": "Google.User@example.com",
                    "email_verified": True,
                },
                None,
            ),
        ):
            response = self.client.get(
                "/register/google/callback",
                query_string={"state": state, "code": "google-code"},
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/vocabulary")
        with self.app.app_context():
            users = db.query(
                """
                SELECT username, google_sub, google_email
                FROM users
                WHERE google_sub = ?
                """,
                ["google-sub-1"],
            )
            invite_codes = db.query(
                """
                SELECT used_by, used_at
                FROM invite_codes
                WHERE code = ?
                """,
                [invite_code],
            )
        self.assertEqual(users[0]["username"], "google_user")
        self.assertEqual(users[0]["google_email"], "google.user@example.com")
        self.assertIsNotNone(invite_codes[0]["used_by"])
        self.assertIsNotNone(invite_codes[0]["used_at"])

    def test_google_registration_callback_rejects_invalid_state(self):
        self.create_invite_code("google-state-code")
        self.client.post(
            "/register/google",
            json={"invite_code": "google-state-code"},
            headers=self.registration_csrf_headers(),
        )

        with patch("Views.user.google_oauth_service.fetch_user_info") as fetch_user_info:
            response = self.client.get(
                "/register/google/callback",
                query_string={"state": "wrong-state", "code": "google-code"},
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/register")
        fetch_user_info.assert_not_called()

    def test_google_registration_callback_rejects_expired_invite_code(self):
        invite_code = self.create_invite_code(
            "google-expired-code",
            datetime.now(timezone.utc) + timedelta(days=5),
        )
        start_response = self.client.post(
            "/register/google",
            json={"invite_code": invite_code},
            headers=self.registration_csrf_headers(),
        )
        state = start_response.get_json()["authorization_url"].split("state=", 1)[1].split("&", 1)[0]
        with self.app.app_context():
            db.execute(
                "UPDATE invite_codes SET expires_at = ? WHERE code = ?",
                [(datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(), invite_code],
            )

        with patch(
            "Views.user.google_oauth_service.fetch_user_info",
            return_value=(
                {
                    "sub": "google-sub-expired",
                    "email": "expired@example.com",
                    "email_verified": True,
                },
                None,
            ),
        ):
            response = self.client.get(
                "/register/google/callback",
                query_string={"state": state, "code": "google-code"},
            )

        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            users = db.query(
                "SELECT id FROM users WHERE google_sub = ?",
                ["google-sub-expired"],
            )
        self.assertEqual(users, [])

    def test_google_registration_callback_rejects_unverified_email(self):
        invite_code = self.create_invite_code("google-unverified-code")
        start_response = self.client.post(
            "/register/google",
            json={"invite_code": invite_code},
            headers=self.registration_csrf_headers(),
        )
        state = start_response.get_json()["authorization_url"].split("state=", 1)[1].split("&", 1)[0]

        with patch(
            "Views.user.google_oauth_service.fetch_user_info",
            return_value=(
                {
                    "sub": "google-sub-unverified",
                    "email": "unverified@example.com",
                    "email_verified": False,
                },
                None,
            ),
        ):
            response = self.client.get(
                "/register/google/callback",
                query_string={"state": state, "code": "google-code"},
            )

        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            invite_codes = db.query(
                "SELECT used_by FROM invite_codes WHERE code = ?",
                [invite_code],
            )
        self.assertIsNone(invite_codes[0]["used_by"])

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

    def test_google_login_start_requires_csrf_token(self):
        response = self.client.post("/login/google", json={})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "Invalid CSRF token")

    def test_google_login_start_returns_authorization_url(self):
        response = self.client.post(
            "/login/google",
            json={},
            headers=self.registration_csrf_headers(),
        )

        self.assertEqual(response.status_code, 200)
        authorization_url = response.get_json()["authorization_url"]
        self.assertIn("https://accounts.google.com/o/oauth2/v2/auth", authorization_url)
        self.assertIn("client_id=google-client-id", authorization_url)

    def test_google_login_callback_uri_uses_https_for_public_hosts(self):
        base_url = "http://erudite-edge.example"

        response = self.client.post(
            "/login/google",
            json={},
            headers=self.registration_csrf_headers(base_url),
            base_url=base_url,
        )

        authorization_url = response.get_json()["authorization_url"]
        query = parse_qs(urlparse(authorization_url).query)
        self.assertEqual(
            query["redirect_uri"][0],
            "https://erudite-edge.example/login/google/callback",
        )

    def test_google_login_callback_logs_in_existing_google_user(self):
        self.create_google_user("google-sub-login-success", "login.success@example.com")
        start_response = self.client.post(
            "/login/google",
            json={},
            headers=self.registration_csrf_headers(),
        )
        state = start_response.get_json()["authorization_url"].split("state=", 1)[1].split("&", 1)[0]

        with patch(
            "Views.user.google_oauth_service.fetch_user_info",
            return_value=(
                {
                    "sub": "google-sub-login-success",
                    "email": "login.success@example.com",
                    "email_verified": True,
                },
                None,
            ),
        ):
            response = self.client.get(
                "/login/google/callback",
                query_string={"state": state, "code": "google-code"},
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/vocabulary")
        with self.client.session_transaction() as session:
            self.assertEqual(session["username"], "login_success")

    def test_google_login_callback_rejects_invalid_state(self):
        self.client.post(
            "/login/google",
            json={},
            headers=self.registration_csrf_headers(),
        )

        with patch("Views.user.google_oauth_service.fetch_user_info") as fetch_user_info:
            response = self.client.get(
                "/login/google/callback",
                query_string={"state": "wrong-state", "code": "google-code"},
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/login")
        fetch_user_info.assert_not_called()

    def test_google_login_callback_rejects_unregistered_google_user(self):
        start_response = self.client.post(
            "/login/google",
            json={},
            headers=self.registration_csrf_headers(),
        )
        state = start_response.get_json()["authorization_url"].split("state=", 1)[1].split("&", 1)[0]

        with patch(
            "Views.user.google_oauth_service.fetch_user_info",
            return_value=(
                {
                    "sub": "google-sub-not-registered",
                    "email": "not.registered@example.com",
                    "email_verified": True,
                },
                None,
            ),
        ):
            response = self.client.get(
                "/login/google/callback",
                query_string={"state": state, "code": "google-code"},
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/login")
        with self.client.session_transaction() as session:
            self.assertNotIn("user_id", session)

    def test_google_login_callback_rejects_unverified_email(self):
        self.create_google_user("google-sub-login-unverified", "login.unverified@example.com")
        start_response = self.client.post(
            "/login/google",
            json={},
            headers=self.registration_csrf_headers(),
        )
        state = start_response.get_json()["authorization_url"].split("state=", 1)[1].split("&", 1)[0]

        with patch(
            "Views.user.google_oauth_service.fetch_user_info",
            return_value=(
                {
                    "sub": "google-sub-login-unverified",
                    "email": "login.unverified@example.com",
                    "email_verified": False,
                },
                None,
            ),
        ):
            response = self.client.get(
                "/login/google/callback",
                query_string={"state": state, "code": "google-code"},
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/login")

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

    def test_create_admin_command_aborts_when_admin_already_exists(self):
        runner = self.app.test_cli_runner()
        first_result = runner.invoke(
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

        self.assertEqual(first_result.exit_code, 0)
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("Admin user already exists", result.output)
        self.assertEqual(
            self.user_categories(),
            {
                "anna": "basic",
                "tuomo": "admin",
            },
        )

    def test_create_admin_command_aborts_before_replacing_existing_admin(self):
        runner = self.app.test_cli_runner()
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
        self.assertIn("Admin user already exists", result.output)
        self.assertEqual(
            self.user_categories(),
            {
                "anna": "basic",
                "invite_issuer": "admin",
            },
        )

    def test_rotate_admin_command_requires_env_allowance(self):
        runner = self.app.test_cli_runner()

        result = runner.invoke(args=["rotate-admin"])

        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("Admin rotation is not allowed", result.output)

    def test_rotate_admin_command_rotates_admin_to_trusted_user(self):
        self.app.config["ROTATE_ADMIN_ALLOWED"] = "YES"
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
        self.create_trusted_user_directly("anna")

        result = runner.invoke(
            args=["rotate-admin"],
            input="tuomo\nsafe-password\nanna\ny\n",
        )

        self.assertEqual(result.exit_code, 0)
        self.assertIn("Rotated admin role to 'anna'.", result.output)
        self.assertEqual(
            self.user_categories(),
            {
                "anna": "admin",
                "tuomo": "trusted",
            },
        )

    def test_rotate_admin_command_accepts_yes_confirmation(self):
        self.app.config["ROTATE_ADMIN_ALLOWED"] = "YES"
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
        self.create_trusted_user_directly("anna")

        result = runner.invoke(
            args=["rotate-admin"],
            input="tuomo\nsafe-password\nanna\nYES\n",
        )

        self.assertEqual(result.exit_code, 0)
        self.assertEqual(self.user_categories()["anna"], "admin")

    def test_rotate_admin_command_rejects_wrong_admin_password(self):
        self.app.config["ROTATE_ADMIN_ALLOWED"] = "YES"
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
        self.create_trusted_user_directly("anna")

        result = runner.invoke(
            args=["rotate-admin"],
            input="tuomo\nwrong-password\nanna\ny\n",
        )

        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("Admin credentials are invalid", result.output)
        self.assertEqual(
            self.user_categories(),
            {
                "anna": "trusted",
                "tuomo": "admin",
            },
        )

    def test_rotate_admin_command_aborts_without_confirmation(self):
        self.app.config["ROTATE_ADMIN_ALLOWED"] = "YES"
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
        self.create_trusted_user_directly("anna")

        result = runner.invoke(
            args=["rotate-admin"],
            input="tuomo\nsafe-password\nanna\nn\n",
        )

        self.assertEqual(result.exit_code, 0)
        self.assertIn("Admin rotation aborted.", result.output)
        self.assertEqual(
            self.user_categories(),
            {
                "anna": "trusted",
                "tuomo": "admin",
            },
        )


if __name__ == "__main__":
    unittest.main()
