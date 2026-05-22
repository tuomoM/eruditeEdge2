import os
import sqlite3
import tempfile
import unittest

import db
from app import create_app
from db import init_db


class TrainingTestCase(unittest.TestCase):
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

    def login_user(self):
        self.client.post(
            "/register",
            json={"username": "tuomo", "password": "safe-password"},
        )

    def logout_user(self):
        self.client.post("/logout", json={})

    def login_second_user(self):
        self.client.post(
            "/register",
            json={"username": "anna", "password": "safe-password"},
        )

    def valid_entry(self, word):
        return {
            "word": word,
            "definition": f"Definition for {word}",
            "context": "Training",
            "synonyms": [f"{word} synonym"],
            "examples": [f"{word} appears in this sentence."],
        }

    def create_sample_vocabs(self):
        vocabulary_ids = []
        for word in [
            "Ubiquitous",
            "curfew",
            "myopic",
            "indignation",
            "predillection",
        ]:
            response = self.client.post("/vocabulary", json=self.valid_entry(word))
            vocabulary_ids.append(response.get_json()["id"])
        return vocabulary_ids

    def create_training(self, vocabulary_ids):
        return self.client.post(
            "/training",
            json={"vocabulary_ids": vocabulary_ids},
        )

    def test_training_selection_requires_login(self):
        response = self.create_training([1])

        self.assertEqual(response.status_code, 401)

    def test_one_vocab_can_be_chosen_for_training(self):
        self.login_user()
        vocabulary_ids = self.create_sample_vocabs()

        response = self.create_training(vocabulary_ids[:1])

        self.assertEqual(response.status_code, 201)
        body = response.get_json()
        self.assertEqual(body["vocabulary_ids"], vocabulary_ids[:1])
        self.assertEqual(len(body["vocabs"]), 1)

    def test_two_vocabs_can_be_chosen_for_training(self):
        self.login_user()
        vocabulary_ids = self.create_sample_vocabs()

        response = self.create_training(vocabulary_ids[:2])

        self.assertEqual(response.status_code, 201)
        body = response.get_json()
        self.assertEqual(body["vocabulary_ids"], vocabulary_ids[:2])
        self.assertEqual(len(body["vocabs"]), 2)

    def test_five_vocabs_can_be_chosen_for_training(self):
        self.login_user()
        vocabulary_ids = self.create_sample_vocabs()

        response = self.create_training(vocabulary_ids)

        self.assertEqual(response.status_code, 201)
        body = response.get_json()
        self.assertEqual(body["vocabulary_ids"], vocabulary_ids)
        self.assertEqual(len(body["vocabs"]), 5)

    def test_training_can_include_global_vocab_created_by_another_user(self):
        self.login_user()
        vocabulary_ids = self.create_sample_vocabs()
        self.logout_user()
        self.login_second_user()

        response = self.create_training([vocabulary_ids[0]])

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["vocabulary_ids"], [vocabulary_ids[0]])

    def test_sqlite_foreign_keys_are_enforced(self):
        with self.app.app_context():
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute(
                    """
                    INSERT INTO training_items
                        (training_session_id, vocabulary_id, item_order)
                    VALUES (?, ?, ?)
                    """,
                    [999, 999, 1],
                )


if __name__ == "__main__":
    unittest.main()
