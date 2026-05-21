import os
import tempfile
import unittest
from unittest.mock import patch

from app import create_app
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
            }
        )
        init_db(self.app)
        self.client = self.app.test_client()

    def tearDown(self):
        os.unlink(self.database_file.name)

    def login_user(self):
        self.client.post(
            "/register",
            json={"username": "tuomo", "password": "safe-password"},
        )

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

    def generate_entry(self, word):
        return self.client.post("/vocabulary/generate", json={"word": word})

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

    def test_create_vocabulary_rejects_sql_injection(self):
        self.login_user()
        data = self.valid_entry()
        data["word"] = "operation'; DROP TABLE users; --"

        response = self.create_entry(data)

        self.assertEqual(response.status_code, 400)

    def test_generate_vocabulary_requires_login(self):
        response = self.generate_entry("operation")

        self.assertEqual(response.status_code, 401)

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

    def test_view_vocabulary_does_not_allow_sql_injection(self):
        self.login_user()

        response = self.client.get("/vocabulary/1 OR 1=1")

        self.assertEqual(response.status_code, 404)

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
