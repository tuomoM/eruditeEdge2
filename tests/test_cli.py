import os
import tempfile
import unittest
from unittest.mock import patch

import db
from app import create_app
from db import init_db
from Services.vocabulary_service import vocabulary_service
from Services.vocabulary_synonym_link_service import vocabulary_synonym_link_service


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
                "OPENAI_API_KEY": "test-api-key",
                "OPENAI_MODEL": "test-model",
                "SYNONYM_NET_CLOZE_JOBS_ENABLED": False,
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
        self.assertEqual(len(rows), 16)
        self.assertEqual(rows[-1]["filename"], "016_vocabulary_senses_and_frequency.sql")

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

    def test_generate_synonym_cloze_command_replaces_linked_net_cloze(self):
        app = self.create_test_app()
        init_db(app)
        with app.app_context():
            user_id = db.execute(
                """
                INSERT INTO users (username, password_hash, account_category)
                VALUES (?, ?, ?)
                """,
                ["cli-admin", "not-used", "admin"],
            ).lastrowid
            contumacious, error = vocabulary_service.create_entry(
                self.valid_cloze_entry(
                    "contumacious",
                    "Stubbornly disobedient to authority.",
                    [],
                ),
                user_id,
            )
            self.assertIsNone(error)
            recalcitrant, error = vocabulary_service.create_entry(
                self.valid_cloze_entry(
                    "recalcitrant",
                    "Resistant to authority or control.",
                    ["contumacious"],
                ),
                user_id,
            )
            self.assertIsNone(error)
            vocabulary_synonym_link_service.link_vocabulary_synonyms(recalcitrant["id"])
            generated_data = {
                "entries": [
                    {
                        "vocabulary_id": contumacious["id"],
                        "cloze_sentences": [
                            "The ____ defendant openly defied the judge.",
                            "Her ____ refusal challenged lawful authority.",
                        ],
                        "needs_attention": "",
                        "confidence_score": 92,
                    },
                    {
                        "vocabulary_id": recalcitrant["id"],
                        "cloze_sentences": [
                            "The ____ machine resisted every adjustment.",
                            "The ____ witness would not comply with the order.",
                        ],
                        "needs_attention": "",
                        "confidence_score": 89,
                    },
                ]
            }

        with patch(
            "cli.synonym_net_cloze_service._vocabulary_ai_service.generate_synonym_net_cloze_data",
            return_value=(generated_data, None),
        ):
            result = app.test_cli_runner().invoke(
                args=["generate-synonym-cloze", str(contumacious["id"])],
            )

        self.assertEqual(result.exit_code, 0)
        self.assertIn("Generated synonym-specific cloze data for 2 entries.", result.output)
        with app.app_context():
            updated = vocabulary_service.get_entry(contumacious["id"])
        self.assertEqual(
            updated["cloze_sentences"],
            generated_data["entries"][0]["cloze_sentences"],
        )

    def test_generate_synonym_cloze_command_reports_missing_entry(self):
        app = self.create_test_app()
        init_db(app)

        result = app.test_cli_runner().invoke(args=["generate-synonym-cloze", "999"])

        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("Vocabulary entry was not found", result.output)

    def valid_cloze_entry(self, word, definition, synonyms):
        return {
            "word": word,
            "definition": definition,
            "context": "Admin",
            "part_of_speech": "adjective",
            "domains": ["attitude", "power"],
            "synonyms": synonyms,
            "examples": [f"The {word} response was memorable."],
            "cloze_sentences": [
                "The ____ person resisted.",
                "A ____ reply followed.",
            ],
            "needs_attention": "",
            "confidence_score": 90,
        }


if __name__ == "__main__":
    unittest.main()
