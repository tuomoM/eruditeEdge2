import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

import db
from app import create_app
from csrf import CSRF_SESSION_KEY


OLD_TRAINING_SCHEMA = """
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE vocabulary_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    word TEXT NOT NULL,
    definition TEXT NOT NULL,
    context TEXT,
    created_by INTEGER NOT NULL REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (word, context)
);

CREATE TABLE vocabulary_synonyms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vocabulary_id INTEGER NOT NULL REFERENCES vocabulary_entries(id) ON DELETE CASCADE,
    synonym TEXT NOT NULL,
    UNIQUE (vocabulary_id, synonym)
);

CREATE TABLE vocabulary_examples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vocabulary_id INTEGER NOT NULL REFERENCES vocabulary_entries(id) ON DELETE CASCADE,
    example_sentence TEXT NOT NULL,
    example_order INTEGER NOT NULL,
    CHECK (example_order BETWEEN 1 AND 4),
    UNIQUE (vocabulary_id, example_order)
);

CREATE TABLE training_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE training_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    training_session_id INTEGER NOT NULL REFERENCES training_sessions(id) ON DELETE CASCADE,
    vocabulary_id INTEGER NOT NULL REFERENCES vocabulary_entries(id),
    item_order INTEGER NOT NULL,
    UNIQUE (training_session_id, vocabulary_id),
    UNIQUE (training_session_id, item_order)
);
"""


class TrainingMigrationTestCase(unittest.TestCase):
    def setUp(self):
        self.database_file = tempfile.NamedTemporaryFile(delete=False)
        self.database_file.close()
        self._create_old_database()
        self._run_training_migration()
        self.app = create_app(
            {
                "TESTING": True,
                "DATABASE": self.database_file.name,
                "SECRET_KEY": "test-secret-key",
            }
        )
        self.client = self.app.test_client()

    def tearDown(self):
        os.unlink(self.database_file.name)

    def _create_old_database(self):
        connection = sqlite3.connect(self.database_file.name)
        try:
            connection.executescript(OLD_TRAINING_SCHEMA)
            connection.commit()
        finally:
            connection.close()

    def _run_training_migration(self):
        connection = sqlite3.connect(self.database_file.name)
        try:
            for migration_path in [
                "migrations/001_training_quiz.sql",
                "migrations/002_user_account_categories.sql",
                "migrations/003_ai_generation_usage.sql",
                "migrations/004_invite_codes.sql",
                "migrations/005_invite_code_usage.sql",
                "migrations/006_google_registration.sql",
                "migrations/010_cloze_training.sql",
            ]:
                with open(migration_path, encoding="utf-8") as migration:
                    connection.executescript(migration.read())
            connection.commit()
        finally:
            connection.close()

    def _login_user(self):
        with self.app.app_context():
            cursor = db.execute(
                """
                INSERT INTO users (username, password_hash, account_category)
                VALUES (?, ?, ?)
                """,
                ["invite_issuer", "not-used", "admin"],
            )
            db.execute(
                """
                INSERT INTO invite_codes (code, created_by, expires_at)
                VALUES (?, ?, ?)
                """,
                [
                    "migration-test-invite",
                    cursor.lastrowid,
                    (datetime.now(timezone.utc) + timedelta(days=5)).isoformat(),
                ],
            )
        self.client.post(
            "/register",
            json={
                "username": "tuomo",
                "password": "safe-password",
                "invite_code": "migration-test-invite",
            },
            headers=self.registration_csrf_headers(),
        )
        with self.app.app_context():
            db.execute(
                """
                UPDATE users
                SET account_category = ?
                WHERE username = ?
                """,
                ["trusted", "tuomo"],
            )

    def registration_csrf_headers(self):
        with self.client.session_transaction() as session:
            session[CSRF_SESSION_KEY] = "test-registration-csrf-token"
        return {"X-CSRF-Token": "test-registration-csrf-token"}

    def _create_vocab(self, word):
        response = self.client.post(
            "/vocabulary",
            json={
                "word": word,
                "definition": f"Definition for {word}",
                "context": "Training",
                "synonyms": [f"{word} synonym"],
                "examples": [f"{word} appears in this sentence."],
            },
        )
        return response.get_json()["id"]

    def test_html_training_selection_after_migration_keeps_selected_vocab_count(self):
        self._login_user()
        first_id = self._create_vocab("ubiquitous")
        second_id = self._create_vocab("curfew")

        response = self.client.post(
            "/training",
            data={"vocabulary_ids": [str(first_id), str(second_id)]},
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"2 vocabulary entries selected.", response.data)
        self.assertNotIn(b"0 vocabulary entries selected.", response.data)


class TrainingMigrationLegacySessionTestCase(unittest.TestCase):
    def setUp(self):
        self.database_file = tempfile.NamedTemporaryFile(delete=False)
        self.database_file.close()
        self._create_old_database_with_training_session()
        self._run_training_migration()

    def tearDown(self):
        os.unlink(self.database_file.name)

    def _create_old_database_with_training_session(self):
        connection = sqlite3.connect(self.database_file.name)
        try:
            connection.executescript(OLD_TRAINING_SCHEMA)
            connection.execute(
                "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                ["tuomo", "hash"],
            )
            for word in ["ubiquitous", "curfew", "myopic"]:
                cursor = connection.execute(
                    """
                    INSERT INTO vocabulary_entries
                        (word, definition, context, created_by)
                    VALUES (?, ?, ?, ?)
                    """,
                    [word, f"Definition for {word}", "Training", 1],
                )
                vocabulary_id = cursor.lastrowid
                connection.execute(
                    """
                    INSERT INTO vocabulary_examples
                        (vocabulary_id, example_sentence, example_order)
                    VALUES (?, ?, ?)
                    """,
                    [vocabulary_id, f"{word} appears in this sentence.", 1],
                )
            cursor = connection.execute(
                "INSERT INTO training_sessions (user_id) VALUES (?)",
                [1],
            )
            training_session_id = cursor.lastrowid
            for item_order, vocabulary_id in enumerate([1, 2, 3], start=1):
                connection.execute(
                    """
                    INSERT INTO training_items
                        (training_session_id, vocabulary_id, item_order)
                    VALUES (?, ?, ?)
                    """,
                    [training_session_id, vocabulary_id, item_order],
                )
            connection.commit()
        finally:
            connection.close()

    def _run_training_migration(self):
        connection = sqlite3.connect(self.database_file.name)
        try:
            for migration_path in [
                "migrations/001_training_quiz.sql",
                "migrations/002_user_account_categories.sql",
                "migrations/003_ai_generation_usage.sql",
                "migrations/004_invite_codes.sql",
                "migrations/005_invite_code_usage.sql",
                "migrations/006_google_registration.sql",
                "migrations/010_cloze_training.sql",
            ]:
                with open(migration_path, encoding="utf-8") as migration:
                    connection.executescript(migration.read())
            connection.commit()
        finally:
            connection.close()

    def test_legacy_training_sessions_are_expired_instead_of_becoming_active_quizzes(self):
        connection = sqlite3.connect(self.database_file.name)
        connection.row_factory = sqlite3.Row
        try:
            session = connection.execute(
                """
                SELECT submitted_at, score, total
                FROM training_sessions
                WHERE id = ?
                """,
                [1],
            ).fetchone()
            answer_option_count = connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM training_answer_options
                WHERE training_session_id = ?
                """,
                [1],
            ).fetchone()["count"]
        finally:
            connection.close()

        self.assertIsNotNone(session["submitted_at"])
        self.assertEqual(session["score"], 0)
        self.assertEqual(session["total"], 3)
        self.assertEqual(answer_option_count, 0)


if __name__ == "__main__":
    unittest.main()
