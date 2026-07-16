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
                "OPENAI_MAINTENANCE_MODEL": "test-maintenance-model",
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
        self.assertEqual(len(rows), 19)
        self.assertEqual(rows[-1]["filename"], "019_relax_vocabulary_domain_catalog.sql")

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

    def test_create_vocabulary_maintenance_run_dry_run_materializes_nothing(self):
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
            vocabulary_service.create_entry(
                self.valid_cloze_entry("awning", "A rooflike cover.", []),
                user_id,
            )

        result = app.test_cli_runner().invoke(
            args=[
                "create-vocabulary-maintenance-run",
                "--name",
                "domain-frequency-v2",
                "--scope",
                "all",
                "--max-estimated-cost",
                "10",
                "--dry-run",
            ]
        )

        self.assertEqual(result.exit_code, 0)
        self.assertIn("Selected entries: 1", result.output)
        self.assertIn("AI model: test-maintenance-model", result.output)
        self.assertIn("Mode: dry-run", result.output)
        self.assertIn("No maintenance run created.", result.output)
        with app.app_context():
            run_count = db.query(
                "SELECT COUNT(*) AS count FROM vocabulary_maintenance_runs"
            )[0]["count"]
        self.assertEqual(run_count, 0)

    def test_create_vocabulary_maintenance_run_creates_items_with_snapshots(self):
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
            vocabulary_service.create_entry(
                self.valid_cloze_entry("awning", "A rooflike cover.", []),
                user_id,
            )
            vocabulary_service.create_entry(
                self.valid_cloze_entry("loam", "Rich soil.", []),
                user_id,
            )

        result = app.test_cli_runner().invoke(
            args=[
                "create-vocabulary-maintenance-run",
                "--name",
                "domain-frequency-v2",
                "--scope",
                "all",
                "--max-items",
                "1",
                "--max-estimated-cost",
                "10",
            ]
        )

        self.assertEqual(result.exit_code, 0)
        self.assertIn("Created vocabulary maintenance run #1.", result.output)
        with app.app_context():
            runs = db.query("SELECT * FROM vocabulary_maintenance_runs")
            items = db.query("SELECT * FROM vocabulary_maintenance_items")
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["status"], "ready")
        self.assertEqual(runs[0]["selected_count"], 1)
        self.assertEqual(runs[0]["ai_model"], "test-maintenance-model")
        self.assertIn("domain-frequency-v2", runs[0]["name"])
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["item_status"], "pending")
        self.assertIn('"word":"awning"', items[0]["source_snapshot_json"])
        self.assertEqual(len(items[0]["source_snapshot_hash"]), 64)

    def test_create_vocabulary_maintenance_run_can_use_context_scope(self):
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
            literary = self.valid_cloze_entry("loam", "Rich soil.", [])
            literary["context"] = "Literary; Geography"
            vocabulary_service.create_entry(literary, user_id)
            technical = self.valid_cloze_entry("procedure", "An established method.", [])
            technical["context"] = "Technical; Medical"
            vocabulary_service.create_entry(technical, user_id)

        result = app.test_cli_runner().invoke(
            args=[
                "create-vocabulary-maintenance-run",
                "--name",
                "literary-only",
                "--scope",
                "context",
                "--context",
                "Literary",
                "--max-estimated-cost",
                "10",
            ]
        )

        self.assertEqual(result.exit_code, 0)
        self.assertIn("Selected entries: 1", result.output)
        with app.app_context():
            item = db.query("SELECT source_snapshot_json FROM vocabulary_maintenance_items")[0]
        self.assertIn('"word":"loam"', item["source_snapshot_json"])

    def test_create_vocabulary_maintenance_run_enforces_cost_limit(self):
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
            vocabulary_service.create_entry(
                self.valid_cloze_entry("awning", "A rooflike cover.", []),
                user_id,
            )

        result = app.test_cli_runner().invoke(
            args=[
                "create-vocabulary-maintenance-run",
                "--name",
                "too-cheap",
                "--scope",
                "all",
                "--max-estimated-cost",
                "0",
            ]
        )

        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("Estimated cost", result.output)

    def test_generate_vocabulary_domain_model_dry_run_does_not_call_ai(self):
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
            vocabulary_service.create_entry(
                self.valid_cloze_entry("contumacious", "Defiant toward authority.", []),
                user_id,
            )

        with patch(
            "cli.vocabulary_maintenance_service._vocabulary_ai_service.generate_domain_model"
        ) as generate_domain_model:
            result = app.test_cli_runner().invoke(
                args=[
                    "generate-vocabulary-domain-model",
                    "--name",
                    "domain-model-v2",
                    "--scope",
                    "all",
                    "--max-estimated-cost",
                    "10",
                    "--dry-run",
                ]
            )

        self.assertEqual(result.exit_code, 0)
        self.assertIn("Selected entries: 1", result.output)
        self.assertIn("Mode: dry-run", result.output)
        self.assertIn("No AI request made", result.output)
        generate_domain_model.assert_not_called()
        with app.app_context():
            proposal_count = db.query(
                "SELECT COUNT(*) AS count FROM vocabulary_domain_model_proposals"
            )[0]["count"]
        self.assertEqual(proposal_count, 0)

    def test_generate_vocabulary_domain_model_stores_ai_proposal(self):
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
            vocabulary_service.create_entry(
                self.valid_cloze_entry("contumacious", "Defiant toward authority.", []),
                user_id,
            )
            vocabulary_service.create_entry(
                self.valid_cloze_entry("totter", "To move unsteadily.", []),
                user_id,
            )
        proposal = {
            "domains": [
                {
                    "key": "authority_resistance",
                    "label": "Authority Resistance",
                    "definition": "Defiance and resistance to authority.",
                    "include": ["defiance"],
                    "exclude": ["formal register"],
                    "example_words": ["contumacious"],
                    "replaces_current_domains": ["attitude", "power"],
                },
                {
                    "key": "physical_motion",
                    "label": "Physical Motion",
                    "definition": "Movement and bodily motion.",
                    "include": ["unstable movement"],
                    "exclude": ["visual perception"],
                    "example_words": ["totter"],
                    "replaces_current_domains": ["movement"],
                },
                {
                    "key": "evaluation_quality",
                    "label": "Evaluation Quality",
                    "definition": "Judgments of qualities and traits.",
                    "include": ["qualities"],
                    "exclude": ["register"],
                    "example_words": ["sturdy"],
                    "replaces_current_domains": ["quality"],
                },
            ],
            "domain_edges": [
                {
                    "source_key": "authority_resistance",
                    "target_key": "evaluation_quality",
                    "relation": "near",
                    "rationale": "Traits can express social resistance.",
                }
            ],
            "retired_domains": [],
            "context_boundary_rules": ["Formal is a context label."],
            "rationale": "A graphable semantic model.",
            "review_notes": [],
        }

        with patch(
            "cli.vocabulary_maintenance_service._vocabulary_ai_service.generate_domain_model",
            return_value=(proposal, None),
        ) as generate_domain_model:
            result = app.test_cli_runner().invoke(
                args=[
                    "generate-vocabulary-domain-model",
                    "--name",
                    "domain-model-v2",
                    "--scope",
                    "all",
                    "--max-estimated-cost",
                    "10",
                ]
            )

        self.assertEqual(result.exit_code, 0)
        self.assertIn("Created vocabulary domain model proposal #1.", result.output)
        self.assertIn("Proposed domains: 3", result.output)
        generate_domain_model.assert_called_once()
        with app.app_context():
            rows = db.query("SELECT * FROM vocabulary_domain_model_proposals")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], "domain-model-v2")
        self.assertEqual(rows[0]["selected_count"], 2)
        self.assertEqual(rows[0]["ai_model"], "test-maintenance-model")
        self.assertIn("authority_resistance", rows[0]["proposal_json"])

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
        ) as generate_cloze:
            result = app.test_cli_runner().invoke(
                args=["generate-synonym-cloze", "contumacious"],
            )

        self.assertEqual(result.exit_code, 0)
        generate_cloze.assert_called_once()
        self.assertIn("Generated synonym-specific cloze data for 2 entries.", result.output)
        with app.app_context():
            updated = vocabulary_service.get_entry(contumacious["id"])
        self.assertEqual(
            updated["cloze_sentences"],
            generated_data["entries"][0]["cloze_sentences"],
        )

    def test_generate_synonym_cloze_command_accepts_vocabulary_id(self):
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

    def test_generate_synonym_cloze_command_reports_ambiguous_word(self):
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
            noun_hobble, error = vocabulary_service.create_entry(
                self.valid_cloze_entry(
                    "hobble",
                    "A restraint used for a horse.",
                    [],
                    part_of_speech="noun",
                ),
                user_id,
            )
            self.assertIsNone(error)
            verb_hobble, error = vocabulary_service.create_entry(
                self.valid_cloze_entry(
                    "hobble",
                    "To move awkwardly or unevenly.",
                    [],
                    part_of_speech="verb",
                ),
                user_id,
            )
            self.assertIsNone(error)

        result = app.test_cli_runner().invoke(args=["generate-synonym-cloze", "hobble"])

        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("Multiple vocabulary entries match 'hobble'", result.output)
        self.assertIn(f"#{noun_hobble['id']}: hobble (noun, Formal)", result.output)
        self.assertIn(f"#{verb_hobble['id']}: hobble (verb, Formal)", result.output)

    def test_generate_synonym_cloze_command_reports_missing_entry(self):
        app = self.create_test_app()
        init_db(app)

        result = app.test_cli_runner().invoke(args=["generate-synonym-cloze", "999"])

        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("Vocabulary entry was not found", result.output)

    def valid_cloze_entry(self, word, definition, synonyms, part_of_speech="adjective"):
        return {
            "word": word,
            "definition": definition,
            "context": "Formal",
            "part_of_speech": part_of_speech,
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
