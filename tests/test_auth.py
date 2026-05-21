import os
import tempfile
import unittest

from app import create_app
from db import init_db


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
        return self.client.post(
            "/register",
            json={"username": username, "password": password},
        )

    def login(self, username, password):
        return self.client.post(
            "/login",
            json={"username": username, "password": password},
        )

    def test_user_creation_succeeds(self):
        response = self.register("tuomo", "safe-password")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["username"], "tuomo")

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

    def test_login_fails_with_incorrect_password(self):
        self.register("tuomo", "safe-password")

        response = self.login("tuomo", "wrong-password")

        self.assertEqual(response.status_code, 401)

    def test_login_does_not_allow_sql_injection(self):
        self.register("tuomo", "safe-password")

        response = self.login("' OR 1=1 --", "anything")

        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
