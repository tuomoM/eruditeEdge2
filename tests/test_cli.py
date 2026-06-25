import os
import tempfile
import unittest
from unittest.mock import patch

import db
from app import create_app
from db import init_db


class CliTestCase(unittest.TestCase):
    def create_test_app(self):
        database_file = tempfile.NamedTemporaryFile(delete=False)
        database_file.close()
        self.addCleanup(os.unlink, database_file.name)
        return create_app(
            {
                "TESTING": True,
                "DATABASE": database_file.name,
                "SECRET_KEY": "test-secret-key",
            }
        )

    def test_check_database_reports_railway_volume(self):
        app = self.create_test_app()

        with patch.dict(
            os.environ,
            {"RAILWAY_VOLUME_MOUNT_PATH": "/app/data"},
            clear=True,
        ):
            result = app.test_cli_runner().invoke(args=["check-database"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("Railway volume: /app/data", result.output)

    def test_check_database_allows_explicit_database_path(self):
        app = self.create_test_app()

        with patch.dict(
            os.environ,
            {"DATABASE": "/app/data/database.db"},
            clear=True,
        ):
            result = app.test_cli_runner().invoke(args=["check-database"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("Database path is set explicitly.", result.output)

    def test_check_database_fails_on_railway_without_persistent_path(self):
        app = self.create_test_app()

        with patch.dict(
            os.environ,
            {"RAILWAY_ENVIRONMENT": "production"},
            clear=True,
        ):
            result = app.test_cli_runner().invoke(args=["check-database"])

        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("has no persistent database path", result.output)

    def test_check_database_allows_local_environment(self):
        app = self.create_test_app()

        with patch.dict(os.environ, {}, clear=True):
            result = app.test_cli_runner().invoke(args=["check-database"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("using the local database path", result.output)

    def test_migrate_stamps_current_schema(self):
        app = self.create_test_app()
        init_db(app)

        result = app.test_cli_runner().invoke(args=["migrate"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("Migration complete.", result.output)
        with app.app_context():
            rows = db.query(
                """
                SELECT filename
                FROM schema_migrations
                ORDER BY filename
                """
            )
        self.assertEqual(len(rows), 13)
        self.assertEqual(rows[-1]["filename"], "013_vocabulary_ai_assessment.sql")

    def test_migrate_skips_recorded_migrations(self):
        app = self.create_test_app()
        init_db(app)
        first_result = app.test_cli_runner().invoke(args=["migrate"])

        second_result = app.test_cli_runner().invoke(args=["migrate"])

        self.assertEqual(first_result.exit_code, 0)
        self.assertEqual(second_result.exit_code, 0)
        self.assertIn("No pending migrations.", second_result.output)

    def test_domain_expansion_migration_preserves_data_and_allows_new_values(self):
        app = self.create_test_app()
        init_db(app)
        with app.app_context():
            user_id = db.execute(
                """
                INSERT INTO users (username, password_hash, account_category)
                VALUES (?, ?, ?)
                """,
                ["domain-test", "not-used", "admin"],
            ).lastrowid
            vocabulary_id = db.execute(
                """
                INSERT INTO vocabulary_entries
                    (word, definition, context, created_by)
                VALUES (?, ?, ?, ?)
                """,
                ["reason", "A basis for thought.", "General", user_id],
            ).lastrowid
            db.execute(
                """
                INSERT INTO vocabulary_domains
                    (vocabulary_id, domain, domain_order)
                VALUES (?, ?, ?)
                """,
                [vocabulary_id, "cognition", 1],
            )

        result = app.test_cli_runner().invoke(args=["migrate"])

        self.assertEqual(result.exit_code, 0)
        with app.app_context():
            db.execute(
                """
                INSERT INTO vocabulary_domains
                    (vocabulary_id, domain, domain_order)
                VALUES (?, ?, ?)
                """,
                [vocabulary_id, "reasoning", 2],
            )
            domains = [
                row["domain"]
                for row in db.query(
                    """
                    SELECT domain
                    FROM vocabulary_domains
                    WHERE vocabulary_id = ?
                    ORDER BY domain_order
                    """,
                    [vocabulary_id],
                )
            ]
        self.assertEqual(domains, ["cognition", "reasoning"])


if __name__ == "__main__":
    unittest.main()
