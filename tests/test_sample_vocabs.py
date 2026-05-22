import os
import tempfile
import unittest

import db
from app import create_app
from db import init_db


class SampleVocabsTestCase(unittest.TestCase):
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

    def tearDown(self):
        os.unlink(self.database_file.name)

    def load_sample_vocabs(self):
        with self.app.app_context():
            with self.app.open_resource("sample_vocabs.sql") as sample_file:
                db.get_connection().executescript(sample_file.read().decode("utf-8"))

    def test_sample_vocabs_can_be_loaded_into_non_empty_database(self):
        with self.app.app_context():
            db.execute(
                "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                ["existing_user", "hash"],
            )
            user_id = db.query(
                "SELECT id FROM users WHERE username = ?",
                ["existing_user"],
            )[0]["id"]
            db.execute(
                """
                INSERT INTO vocabulary_entries
                    (word, definition, context, created_by)
                VALUES (?, ?, ?, ?)
                """,
                ["existing", "Existing definition", "Existing", user_id],
            )

        self.load_sample_vocabs()
        self.load_sample_vocabs()

        with self.app.app_context():
            rows = db.query(
                """
                SELECT word
                FROM vocabulary_entries
                WHERE created_by = (SELECT id FROM users WHERE username = ?)
                ORDER BY word
                """,
                ["sample_user"],
            )
            existing_synonyms = db.query(
                """
                SELECT COUNT(*) AS count
                FROM vocabulary_synonyms
                WHERE vocabulary_id = (
                    SELECT id FROM vocabulary_entries WHERE word = ?
                )
                """,
                ["existing"],
            )[0]["count"]

        self.assertEqual(
            [row["word"] for row in rows],
            ["Ubiquitous", "curfew", "indignation", "myopic", "predillection"],
        )
        self.assertEqual(existing_synonyms, 0)


if __name__ == "__main__":
    unittest.main()
