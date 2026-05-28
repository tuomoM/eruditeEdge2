import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

import db
from app import create_app
from csrf import CSRF_SESSION_KEY
from db import init_db


class AccessRequestTestCase(unittest.TestCase):
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

    def registration_csrf_headers(self):
        with self.client.session_transaction() as session:
            session[CSRF_SESSION_KEY] = "test-registration-csrf-token"
        return {"X-CSRF-Token": "test-registration-csrf-token"}

    def access_request_data(self):
        return {
            "name": "Ada Lovelace",
            "email": "Ada@example.com",
            "message": "I would like to practice vocabulary with the family.",
        }

    def create_access_request(self):
        response = self.client.post(
            "/access-request",
            json=self.access_request_data(),
            headers=self.registration_csrf_headers(),
        )
        self.assertEqual(response.status_code, 201)
        return response.get_json()

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

    def create_invite_code(self):
        expires_at = datetime.now(timezone.utc) + timedelta(days=5)
        with self.app.app_context():
            creator_id = db.query("SELECT id FROM users ORDER BY id LIMIT 1")[0]["id"]
            db.execute(
                """
                INSERT INTO invite_codes (code, created_by, expires_at)
                VALUES (?, ?, ?)
                """,
                ["basic-user-invite", creator_id, expires_at.isoformat()],
            )
        return "basic-user-invite"

    def register_basic_user(self):
        self.create_admin("invite_issuer")
        invite_code = self.create_invite_code()
        self.client.post(
            "/register",
            json={
                "username": "anna",
                "password": "safe-password",
                "invite_code": invite_code,
            },
            headers=self.registration_csrf_headers(),
        )

    def admin_csrf_headers(self):
        self.client.get("/admin")
        with self.client.session_transaction() as session:
            return {"X-CSRF-Token": session[CSRF_SESSION_KEY]}

    def access_requests(self):
        with self.app.app_context():
            rows = db.query(
                """
                SELECT name, email, message, ip_address
                FROM access_requests
                ORDER BY id
                """
            )
        return [dict(row) for row in rows]

    def test_public_user_can_create_access_request(self):
        response = self.client.post(
            "/access-request",
            json=self.access_request_data(),
            headers=self.registration_csrf_headers(),
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["name"], "Ada Lovelace")
        self.assertEqual(response.get_json()["email"], "ada@example.com")
        self.assertEqual(response.get_json()["ip_address"], "127.0.0.1")
        self.assertEqual(len(self.access_requests()), 1)

    def test_access_request_requires_csrf_token(self):
        response = self.client.post(
            "/access-request",
            json=self.access_request_data(),
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "Invalid CSRF token")
        self.assertEqual(self.access_requests(), [])

    def test_access_request_rejects_invalid_email(self):
        data = self.access_request_data()
        data["email"] = "not-an-email"

        response = self.client.post(
            "/access-request",
            json=data,
            headers=self.registration_csrf_headers(),
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "Email must be valid")
        self.assertEqual(self.access_requests(), [])

    def test_access_request_rejects_message_longer_than_one_thousand_characters(self):
        data = self.access_request_data()
        data["message"] = "x" * 1001

        response = self.client.post(
            "/access-request",
            json=data,
            headers=self.registration_csrf_headers(),
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "Message must be 1000 characters or fewer")
        self.assertEqual(self.access_requests(), [])

    def test_access_request_rejects_html_tags_and_sql_statements(self):
        data = self.access_request_data()
        data["message"] = "<script>alert(1)</script>"

        response = self.client.post(
            "/access-request",
            json=data,
            headers=self.registration_csrf_headers(),
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.get_json()["error"],
            "HTML tags and SQL statements are not allowed",
        )
        self.assertEqual(self.access_requests(), [])

    def test_access_request_rejects_honeypot_field(self):
        data = self.access_request_data()
        data["website"] = "https://spam.example"

        response = self.client.post(
            "/access-request",
            json=data,
            headers=self.registration_csrf_headers(),
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "Access request was rejected")
        self.assertEqual(self.access_requests(), [])

    def test_access_request_rejects_duplicate_active_email(self):
        self.create_access_request()
        data = self.access_request_data()
        data["name"] = "Different Person"
        data["email"] = "ADA@example.com"

        response = self.client.post(
            "/access-request",
            json=data,
            headers=self.registration_csrf_headers(),
            environ_base={"REMOTE_ADDR": "127.0.0.2"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "Email already has an active access request")
        self.assertEqual(len(self.access_requests()), 1)

    def test_access_request_email_is_unique_at_database_layer(self):
        self.create_access_request()

        with self.app.app_context():
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute(
                    """
                    INSERT INTO access_requests (name, email, message, ip_address)
                    VALUES (?, ?, ?, ?)
                    """,
                    [
                        "Another Person",
                        "ada@example.com",
                        "Trying to bypass the service.",
                        "127.0.0.2",
                    ],
                )

    def test_access_request_deletes_oldest_when_queue_has_twenty_requests(self):
        for request_number in range(20):
            data = self.access_request_data()
            data["name"] = f"Person {request_number}"
            data["email"] = f"person{request_number}@example.com"
            response = self.client.post(
                "/access-request",
                json=data,
                headers=self.registration_csrf_headers(),
                environ_base={"REMOTE_ADDR": f"127.0.0.{request_number + 1}"},
            )
            self.assertEqual(response.status_code, 201)

        data = self.access_request_data()
        data["name"] = "Newest Person"
        data["email"] = "newest@example.com"
        response = self.client.post(
            "/access-request",
            json=data,
            headers=self.registration_csrf_headers(),
            environ_base={"REMOTE_ADDR": "127.0.0.50"},
        )

        requests = self.access_requests()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(requests), 20)
        self.assertNotIn("person0@example.com", [request["email"] for request in requests])
        self.assertIn("newest@example.com", [request["email"] for request in requests])

    def test_access_request_allows_only_three_requests_from_same_ip_per_day(self):
        for request_number in range(3):
            data = self.access_request_data()
            data["name"] = f"Person {request_number}"
            data["email"] = f"person{request_number}@example.com"
            response = self.client.post(
                "/access-request",
                json=data,
                headers=self.registration_csrf_headers(),
                environ_base={"REMOTE_ADDR": "127.0.0.7"},
            )
            self.assertEqual(response.status_code, 201)

        data = self.access_request_data()
        data["email"] = "fourth@example.com"
        response = self.client.post(
            "/access-request",
            json=data,
            headers=self.registration_csrf_headers(),
            environ_base={"REMOTE_ADDR": "127.0.0.7"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.get_json()["error"],
            "Too many access requests from this IP address today",
        )
        self.assertEqual(len(self.access_requests()), 3)

    def test_admin_page_shows_access_requests(self):
        self.create_access_request()
        self.create_admin("tuomo")
        self.login("tuomo")

        response = self.client.get("/admin")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Access requests", response.data)
        self.assertIn(b"Ada Lovelace", response.data)
        self.assertIn(b"ada@example.com", response.data)
        self.assertIn(b"I would like to practice vocabulary", response.data)

    def test_admin_can_delete_access_request(self):
        access_request = self.create_access_request()
        self.create_admin("tuomo")
        self.login("tuomo")

        response = self.client.post(
            f"/admin/access-requests/{access_request['id']}/delete",
            json={},
            headers=self.admin_csrf_headers(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["deleted"])
        self.assertEqual(self.access_requests(), [])

    def test_basic_user_cannot_delete_access_request(self):
        access_request = self.create_access_request()
        self.register_basic_user()
        self.login("anna")

        response = self.client.post(
            f"/admin/access-requests/{access_request['id']}/delete",
            json={},
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()["error"], "Admin account is required")
        self.assertEqual(len(self.access_requests()), 1)

    def test_admin_delete_access_request_rejects_missing_csrf_token(self):
        access_request = self.create_access_request()
        self.create_admin("tuomo")
        self.login("tuomo")

        response = self.client.post(
            f"/admin/access-requests/{access_request['id']}/delete",
            json={},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "Invalid CSRF token")
        self.assertEqual(len(self.access_requests()), 1)


if __name__ == "__main__":
    unittest.main()
