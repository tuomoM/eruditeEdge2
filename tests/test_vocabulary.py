import json
import os
import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime, timedelta, timezone

import db
from app import create_app
from csrf import CSRF_SESSION_KEY
from db import init_db
from Services.app_settings_service import app_settings_service
from Services.synonym_net_cloze_service import synonym_net_cloze_service


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
                "SYNONYM_NET_CLOZE_JOBS_ENABLED": False,
                "TRUSTED_AI_DAILY_QUOTA": 2,
            }
        )
        init_db(self.app)
        self.client = self.app.test_client()

    def tearDown(self):
        os.unlink(self.database_file.name)

    def login_user(self):
        invite_code = self.create_invite_code()
        self.client.post(
            "/register",
            json={
                "username": "tuomo",
                "password": "safe-password",
                "invite_code": invite_code,
            },
            headers=self.csrf_headers(),
        )
        self.set_user_category("tuomo", "trusted")

    def logout_user(self):
        self.client.post("/logout", json={})

    def login_second_user(self):
        invite_code = self.create_invite_code()
        self.client.post(
            "/register",
            json={
                "username": "anna",
                "password": "safe-password",
                "invite_code": invite_code,
            },
            headers=self.csrf_headers(),
        )

    def login_basic_second_user(self):
        self.login_second_user()
        self.set_user_category("anna", "basic")

    def login_existing_second_user(self):
        self.client.post(
            "/login",
            json={"username": "anna", "password": "safe-password"},
        )

    def make_user_trusted(self, username):
        self.set_user_category(username, "trusted")

    def set_user_category(self, username, account_category):
        with self.app.app_context():
            db.execute(
                """
                UPDATE users
                SET account_category = ?
                WHERE username = ?
                """,
                [account_category, username],
            )

    def set_auto_trust_new_users(self, enabled):
        with self.app.app_context():
            app_settings_service.set_auto_trust_new_users_enabled(enabled)

    def invite_creator_id(self):
        with self.app.app_context():
            rows = db.query("SELECT id FROM users ORDER BY id LIMIT 1")
            if rows:
                return rows[0]["id"]
            cursor = db.execute(
                """
                INSERT INTO users (username, password_hash, account_category)
                VALUES (?, ?, ?)
                """,
                ["invite_issuer", "not-used", "admin"],
            )
            return cursor.lastrowid

    def create_invite_code(self):
        creator_id = self.invite_creator_id()
        expires_at = datetime.now(timezone.utc) + timedelta(days=5)
        with self.app.app_context():
            count = db.query("SELECT COUNT(*) AS count FROM invite_codes")[0]["count"]
            code = f"test-invite-code-{count + 1}"
            db.execute(
                """
                INSERT INTO invite_codes (code, created_by, expires_at)
                VALUES (?, ?, ?)
                """,
                [code, creator_id, expires_at.isoformat()],
            )
        return code

    def csrf_headers(self):
        with self.client.session_transaction() as session:
            session[CSRF_SESSION_KEY] = "test-csrf-token"
        return {"X-CSRF-Token": "test-csrf-token"}

    def ai_generation_count(self, username):
        with self.app.app_context():
            rows = db.query(
                """
                SELECT ai_generation_usage.generation_count
                FROM ai_generation_usage
                JOIN users ON users.id = ai_generation_usage.user_id
                WHERE users.username = ? AND generation_date = DATE('now')
                """,
                [username],
            )
        if not rows:
            return 0
        return rows[0]["generation_count"]

    def ai_generation_total_count(self, username):
        with self.app.app_context():
            rows = db.query(
                """
                SELECT COALESCE(SUM(ai_generation_usage.generation_count), 0) AS count
                FROM ai_generation_usage
                JOIN users ON users.id = ai_generation_usage.user_id
                WHERE users.username = ?
                """,
                [username],
            )
        return rows[0]["count"]

    def valid_entry(self):
        return {
            "word": "operation",
            "definition": "A planned activity or procedure",
            "context": "Technical; Science; Medical",
            "synonyms": ["procedure", "process"],
            "examples": [
                "The operation required careful preparation.",
                "The doctor explained the operation to the patient.",
            ],
        }

    def create_entry(self, data=None, include_csrf=True):
        headers = self.csrf_headers() if include_csrf else {}
        return self.client.post(
            "/vocabulary",
            json=data or self.valid_entry(),
            headers=headers,
        )

    def create_entry_with_word(self, word):
        data = self.valid_entry()
        data["word"] = word
        data["definition"] = f"Definition for {word}"
        data["examples"] = [f"{word} appears in this sentence."]
        return self.create_entry(data)

    def generate_entry(self, word, include_csrf=True, usage_clue=None):
        headers = self.csrf_headers() if include_csrf else {}
        payload = {"word": word}
        if usage_clue is not None:
            payload["usage_clue"] = usage_clue
        return self.client.post(
            "/vocabulary/generate",
            json=payload,
            headers=headers,
        )

    def practice_usage(self, vocabulary_id, sentence, include_csrf=True):
        headers = self.csrf_headers() if include_csrf else {}
        return self.client.post(
            f"/vocabulary/{vocabulary_id}/practice-usage",
            json={"sentence": sentence},
            headers=headers,
        )

    def update_entry(self, vocabulary_id, data=None, include_csrf=True):
        headers = self.csrf_headers() if include_csrf else {}
        return self.client.put(
            f"/vocabulary/{vocabulary_id}",
            json=data or self.valid_entry(),
            headers=headers,
        )

    def search_entries(self, word):
        return self.client.get("/vocabulary/search", query_string={"word": word})

    def test_create_vocabulary_requires_login(self):
        response = self.create_entry()

        self.assertEqual(response.status_code, 401)

    def test_create_vocabulary_rejects_missing_csrf_token(self):
        self.login_user()

        response = self.create_entry(include_csrf=False)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "Invalid CSRF token")

    def test_create_vocabulary_succeeds_when_logged_in(self):
        self.login_user()

        response = self.create_entry()

        self.assertEqual(response.status_code, 201)
        body = response.get_json()
        self.assertEqual(body["word"], "operation")
        self.assertEqual(body["context"], "Technical; Science; Medical")
        self.assertEqual(body["synonyms"], ["procedure", "process"])
        self.assertEqual(len(body["examples"]), 2)
        self.assertEqual(body["sources"], [])

    def test_create_vocabulary_normalizes_multiple_contexts(self):
        self.login_user()
        data = self.valid_entry()
        data["context"] = "General / Formal, Literary; formal"

        response = self.create_entry(data)

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["context"], "Formal; Literary")
        self.assertEqual(response.get_json()["contexts"], ["Formal", "Literary"])

    def test_create_vocabulary_marks_gregmat_membership(self):
        self.login_user()
        data = self.valid_entry()
        data["word"] = "abound"
        data["definition"] = "To exist in large numbers."
        data["examples"] = ["Wildflowers abound in the meadow."]

        response = self.create_entry(data)

        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.get_json()["word_lists"],
            [{"list_key": "gregmat", "name": "GregMat", "category": "GRE"}],
        )

    def test_vocabulary_page_filters_by_gregmat_list(self):
        self.login_user()
        gregmat_data = self.valid_entry()
        gregmat_data["word"] = "abound"
        gregmat_data["definition"] = "To exist in large numbers."
        gregmat_data["examples"] = ["Wildflowers abound in the meadow."]
        other_data = self.valid_entry()
        other_data["word"] = "plainword"
        other_data["definition"] = "An ordinary test word."
        other_data["examples"] = ["This is a plainword example."]
        self.create_entry(gregmat_data)
        self.create_entry(other_data)

        response = self.client.get("/vocabulary", query_string={"gre_list": "gregmat"})

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"abound", response.data)
        self.assertNotIn(b"plainword", response.data)
        self.assertIn(b"GRE lists: GregMat", response.data)
        self.assertIn(b"GRE: GregMat", response.data)

    def test_update_vocabulary_refreshes_gregmat_membership(self):
        self.login_user()
        vocabulary_id = self.create_entry().get_json()["id"]
        data = self.valid_entry()
        data["word"] = "abound"
        data["definition"] = "To exist in large numbers."
        data["examples"] = ["Wildflowers abound in the meadow."]

        response = self.update_entry(vocabulary_id, data)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["word_lists"][0]["name"], "GregMat")

    def test_context_filter_matches_entry_with_multiple_contexts(self):
        self.login_user()
        data = self.valid_entry()
        data["word"] = "stultify"
        data["definition"] = "To make ineffective."
        data["context"] = "Business; Formal"
        self.create_entry(data)

        response = self.client.get(
            "/vocabulary",
            query_string={"context": "Formal"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"stultify", response.data)

    def test_create_vocabulary_saves_sources_without_creator_identity(self):
        self.login_user()
        data = self.valid_entry()
        data["sources"] = [
            {
                "name": "The Crossing",
                "author": "Cormac McCarthy",
                "note": "chapter 1",
            },
            "Blood Meridian; Cormac McCarthy; opening pages",
        ]

        response = self.create_entry(data)

        self.assertEqual(response.status_code, 201)
        body = response.get_json()
        self.assertEqual(
            body["sources"],
            [
                {
                    "id": body["sources"][0]["id"],
                    "name": "The Crossing",
                    "author": "Cormac McCarthy",
                    "source_type": "other",
                    "note": "chapter 1",
                },
                {
                    "id": body["sources"][1]["id"],
                    "name": "Blood Meridian",
                    "author": "Cormac McCarthy",
                    "source_type": "other",
                    "note": "opening pages",
                },
            ],
        )
        self.assertNotIn("created_by", body["sources"][0])

    def test_sources_are_reused_across_entries_without_showing_user_identity(self):
        self.login_user()
        first_data = self.valid_entry()
        first_data["sources"] = ["The Crossing; Cormac McCarthy; chapter 1"]
        first_source_id = self.create_entry(first_data).get_json()["sources"][0]["id"]
        second_data = self.valid_entry()
        second_data["word"] = "gingerly"
        second_data["definition"] = "In a careful or cautious manner."
        second_data["examples"] = ["He stepped gingerly over the stones."]
        second_data["sources"] = ["the crossing; Cormac McCarthy; chapter 2"]

        second_response = self.create_entry(second_data)

        self.assertEqual(second_response.status_code, 201)
        self.assertEqual(second_response.get_json()["sources"][0]["id"], first_source_id)
        self.assertNotIn("created_by", second_response.get_json()["sources"][0])

    def test_create_vocabulary_queues_synonym_link_job(self):
        self.login_user()

        response = self.create_entry()

        self.assertEqual(response.status_code, 201)
        with self.app.app_context():
            rows = db.query(
                """
                SELECT job_type, status, payload
                FROM background_jobs
                """
            )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["job_type"], "link_vocabulary_synonyms")
        self.assertEqual(rows[0]["status"], "pending")
        self.assertIn('"vocabulary_id"', rows[0]["payload"])

    def test_background_job_links_synonyms_bidirectionally_and_deletes_completed_job(self):
        self.login_user()
        stagger_data = self.valid_entry()
        stagger_data["word"] = "stagger"
        stagger_data["definition"] = "To walk or move unsteadily."
        stagger_data["synonyms"] = []
        stagger_data["examples"] = ["The tired runner began to stagger."]
        stagger_id = self.create_entry(stagger_data).get_json()["id"]
        totter_data = self.valid_entry()
        totter_data["word"] = "totter"
        totter_data["definition"] = "To move in a shaky way."
        totter_data["synonyms"] = ["stagger"]
        totter_data["examples"] = ["The stack began to totter."]
        totter_id = self.create_entry(totter_data).get_json()["id"]

        result = self.app.test_cli_runner().invoke(args=["run-background-jobs", "--limit", "10"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("completed 2", result.output)
        with self.app.app_context():
            job_count = db.query("SELECT COUNT(*) AS count FROM background_jobs")[0]["count"]
            totter_synonym = db.query(
                """
                SELECT linked_vocabulary_id
                FROM vocabulary_synonyms
                WHERE vocabulary_id = ? AND synonym = ?
                """,
                [totter_id, "stagger"],
            )[0]
            stagger_synonym = db.query(
                """
                SELECT synonym, linked_vocabulary_id
                FROM vocabulary_synonyms
                WHERE vocabulary_id = ? AND synonym = ?
                """,
                [stagger_id, "totter"],
            )[0]
        self.assertEqual(job_count, 0)
        self.assertEqual(totter_synonym["linked_vocabulary_id"], stagger_id)
        self.assertEqual(stagger_synonym["synonym"], "totter")
        self.assertEqual(stagger_synonym["linked_vocabulary_id"], totter_id)

    def test_synonym_link_job_queues_synonym_net_cloze_job_when_enabled(self):
        self.app.config["SYNONYM_NET_CLOZE_JOBS_ENABLED"] = True
        self.login_user()
        stagger_data = self.valid_entry()
        stagger_data["word"] = "stagger"
        stagger_data["definition"] = "To walk or move unsteadily."
        stagger_data["synonyms"] = []
        stagger_data["examples"] = ["The tired runner began to stagger."]
        stagger_id = self.create_entry(stagger_data).get_json()["id"]
        totter_data = self.valid_entry()
        totter_data["word"] = "totter"
        totter_data["definition"] = "To move in a shaky way."
        totter_data["synonyms"] = ["stagger"]
        totter_data["examples"] = ["The stack began to totter."]
        totter_id = self.create_entry(totter_data).get_json()["id"]

        result = self.app.test_cli_runner().invoke(args=["run-background-jobs", "--limit", "10"])

        self.assertEqual(result.exit_code, 0)
        with self.app.app_context():
            rows = db.query(
                """
                SELECT job_type, status, payload
                FROM background_jobs
                """
            )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["job_type"], "generate_synonym_net_cloze")
        self.assertEqual(rows[0]["status"], "pending")
        payload = json.loads(rows[0]["payload"])
        self.assertIn(payload["vocabulary_id"], {stagger_id, totter_id})

    def test_background_job_links_existing_synonym_to_new_word_with_other_links(self):
        self.login_user()
        obstinate_data = self.valid_entry()
        obstinate_data["word"] = "obstinate"
        obstinate_data["definition"] = "Stubbornly refusing to change."
        obstinate_data["synonyms"] = []
        obstinate_data["examples"] = ["The obstinate child refused to move."]
        obstinate_id = self.create_entry(obstinate_data).get_json()["id"]
        recalcitrant_data = self.valid_entry()
        recalcitrant_data["word"] = "recalcitrant"
        recalcitrant_data["definition"] = "Resistant to authority or control."
        recalcitrant_data["synonyms"] = ["obstinate"]
        recalcitrant_data["examples"] = ["The recalcitrant witness ignored the question."]
        recalcitrant_id = self.create_entry(recalcitrant_data).get_json()["id"]
        self.app.test_cli_runner().invoke(args=["run-background-jobs", "--limit", "10"])
        contumacious_data = self.valid_entry()
        contumacious_data["word"] = "contumacious"
        contumacious_data["definition"] = "Stubbornly disobedient to authority."
        contumacious_data["synonyms"] = ["defiant", "recalcitrant"]
        contumacious_data["examples"] = ["The contumacious defendant refused to answer."]
        contumacious_id = self.create_entry(contumacious_data).get_json()["id"]

        result = self.app.test_cli_runner().invoke(args=["run-background-jobs", "--limit", "10"])

        self.assertEqual(result.exit_code, 0)
        with self.app.app_context():
            recalcitrant_to_obstinate = db.query(
                """
                SELECT linked_vocabulary_id
                FROM vocabulary_synonyms
                WHERE vocabulary_id = ? AND synonym = ?
                """,
                [recalcitrant_id, "obstinate"],
            )[0]
            contumacious_to_recalcitrant = db.query(
                """
                SELECT linked_vocabulary_id
                FROM vocabulary_synonyms
                WHERE vocabulary_id = ? AND synonym = ?
                """,
                [contumacious_id, "recalcitrant"],
            )[0]
            recalcitrant_to_contumacious = db.query(
                """
                SELECT linked_vocabulary_id
                FROM vocabulary_synonyms
                WHERE vocabulary_id = ? AND synonym = ?
                """,
                [recalcitrant_id, "contumacious"],
            )[0]
        self.assertEqual(recalcitrant_to_obstinate["linked_vocabulary_id"], obstinate_id)
        self.assertEqual(contumacious_to_recalcitrant["linked_vocabulary_id"], recalcitrant_id)
        self.assertEqual(recalcitrant_to_contumacious["linked_vocabulary_id"], contumacious_id)

    def test_background_job_runner_repairs_stale_synonym_links_without_pending_jobs(self):
        self.login_user()
        recalcitrant_data = self.valid_entry()
        recalcitrant_data["word"] = "recalcitrant"
        recalcitrant_data["definition"] = "Resistant to authority or control."
        recalcitrant_data["synonyms"] = []
        recalcitrant_data["examples"] = ["The recalcitrant witness ignored the question."]
        recalcitrant_id = self.create_entry(recalcitrant_data).get_json()["id"]
        contumacious_data = self.valid_entry()
        contumacious_data["word"] = "contumacious"
        contumacious_data["definition"] = "Stubbornly disobedient to authority."
        contumacious_data["synonyms"] = ["recalcitrant"]
        contumacious_data["examples"] = ["The contumacious defendant refused to answer."]
        contumacious_id = self.create_entry(contumacious_data).get_json()["id"]
        with self.app.app_context():
            db.execute("DELETE FROM background_jobs")
            db.execute(
                """
                UPDATE vocabulary_synonyms
                SET linked_vocabulary_id = NULL
                WHERE vocabulary_id = ? AND synonym = ?
                """,
                [contumacious_id, "recalcitrant"],
            )

        result = self.app.test_cli_runner().invoke(args=["run-background-jobs", "--limit", "10"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("Synonym repair checked", result.output)
        with self.app.app_context():
            contumacious_to_recalcitrant = db.query(
                """
                SELECT linked_vocabulary_id
                FROM vocabulary_synonyms
                WHERE vocabulary_id = ? AND synonym = ?
                """,
                [contumacious_id, "recalcitrant"],
            )[0]
            recalcitrant_to_contumacious = db.query(
                """
                SELECT linked_vocabulary_id
                FROM vocabulary_synonyms
                WHERE vocabulary_id = ? AND synonym = ?
                """,
                [recalcitrant_id, "contumacious"],
            )[0]
        self.assertEqual(contumacious_to_recalcitrant["linked_vocabulary_id"], recalcitrant_id)
        self.assertEqual(recalcitrant_to_contumacious["linked_vocabulary_id"], contumacious_id)

    def test_synonym_net_cloze_generation_replaces_whole_net_cloze_sentences(self):
        self.login_user()
        first = self.valid_entry()
        first["word"] = "contumacious"
        first["definition"] = "Stubbornly disobedient to authority."
        first["part_of_speech"] = "adjective"
        first["cloze_sentences"] = ["The ____ person resisted.", "A ____ reply followed."]
        first_id = self.create_entry(first).get_json()["id"]
        second = self.valid_entry()
        second["word"] = "recalcitrant"
        second["definition"] = "Resistant to authority or control."
        second["part_of_speech"] = "adjective"
        second["synonyms"] = ["contumacious"]
        second["cloze_sentences"] = ["The ____ person resisted.", "A ____ reply followed."]
        second_id = self.create_entry(second).get_json()["id"]
        self.app.test_cli_runner().invoke(args=["run-background-jobs", "--limit", "10"])
        generated_data = {
            "entries": [
                {
                    "vocabulary_id": first_id,
                    "cloze_sentences": [
                        "The ____ defendant defied the judge's order.",
                        "Her ____ refusal challenged the court's authority.",
                    ],
                    "needs_attention": "",
                    "confidence_score": 90,
                },
                {
                    "vocabulary_id": second_id,
                    "cloze_sentences": [
                        "The ____ equipment resisted every repair attempt.",
                        "The ____ witness would not comply with the subpoena.",
                    ],
                    "needs_attention": "",
                    "confidence_score": 88,
                },
            ]
        }

        with patch(
            "Services.synonym_net_cloze_service.synonym_net_cloze_service._vocabulary_ai_service.generate_synonym_net_cloze_data",
            return_value=(generated_data, None),
        ):
            with self.app.app_context():
                result, error = synonym_net_cloze_service.generate_for_vocabulary(
                    first_id,
                    "test-key",
                    "test-model",
                )

        self.assertIsNone(error)
        self.assertEqual(result["updated"], 2)
        first_entry = self.client.get(f"/vocabulary/{first_id}").get_json()
        second_entry = self.client.get(f"/vocabulary/{second_id}").get_json()
        self.assertEqual(first_entry["cloze_sentences"], generated_data["entries"][0]["cloze_sentences"])
        self.assertEqual(second_entry["cloze_sentences"], generated_data["entries"][1]["cloze_sentences"])
        self.assertEqual(first_entry["confidence_score"], 90)
        self.assertEqual(second_entry["confidence_score"], 88)

    def test_synonym_net_cloze_generation_rejects_partial_ai_output_without_replacing(self):
        self.login_user()
        first = self.valid_entry()
        first["word"] = "contumacious"
        first["definition"] = "Stubbornly disobedient to authority."
        first["cloze_sentences"] = [
            "The ____ person resisted.",
            "A ____ reply followed.",
        ]
        first_id = self.create_entry(first).get_json()["id"]
        second = self.valid_entry()
        second["word"] = "recalcitrant"
        second["definition"] = "Resistant to authority or control."
        second["synonyms"] = ["contumacious"]
        second["cloze_sentences"] = [
            "The ____ witness resisted.",
            "A ____ machine resisted.",
        ]
        self.create_entry(second)
        self.app.test_cli_runner().invoke(args=["run-background-jobs", "--limit", "10"])
        generated_data = {
            "entries": [
                {
                    "vocabulary_id": first_id,
                    "cloze_sentences": [
                        "The ____ defendant defied the judge's order.",
                        "Her ____ refusal challenged the court's authority.",
                    ],
                    "needs_attention": "",
                    "confidence_score": 90,
                }
            ]
        }

        with patch(
            "Services.synonym_net_cloze_service.synonym_net_cloze_service._vocabulary_ai_service.generate_synonym_net_cloze_data",
            return_value=(generated_data, None),
        ):
            with self.app.app_context():
                result, error = synonym_net_cloze_service.generate_for_vocabulary(
                    first_id,
                    "test-key",
                    "test-model",
                )

        self.assertIsNone(result)
        self.assertEqual(error, "OpenAI returned incomplete synonym net cloze data")
        first_entry = self.client.get(f"/vocabulary/{first_id}").get_json()
        self.assertEqual(first_entry["cloze_sentences"], first["cloze_sentences"])

    def test_vocabulary_detail_links_linked_synonyms(self):
        self.login_user()
        stagger_data = self.valid_entry()
        stagger_data["word"] = "stagger"
        stagger_data["definition"] = "To walk or move unsteadily."
        stagger_data["synonyms"] = []
        stagger_data["examples"] = ["The tired runner began to stagger."]
        stagger_id = self.create_entry(stagger_data).get_json()["id"]
        totter_data = self.valid_entry()
        totter_data["word"] = "totter"
        totter_data["definition"] = "To move in a shaky way."
        totter_data["synonyms"] = ["stagger"]
        totter_data["examples"] = ["The stack began to totter."]
        totter_id = self.create_entry(totter_data).get_json()["id"]
        self.app.test_cli_runner().invoke(args=["run-background-jobs", "--limit", "10"])

        response = self.client.get(f"/vocabulary/{totter_id}/page")

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            f'href="/vocabulary/{stagger_id}/page">stagger</a>'.encode(),
            response.data,
        )

    def test_vocabulary_detail_shows_sources_without_user_identity(self):
        self.login_user()
        data = self.valid_entry()
        data["word"] = "gingerly"
        data["definition"] = "In a careful or cautious manner."
        data["examples"] = ["He stepped gingerly over the stones."]
        data["sources"] = ["The Crossing; Cormac McCarthy; chapter 1"]
        vocabulary_id = self.create_entry(data).get_json()["id"]

        response = self.client.get(f"/vocabulary/{vocabulary_id}/page")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Sources", response.data)
        self.assertIn(b"The Crossing", response.data)
        self.assertIn(b"Cormac McCarthy", response.data)
        self.assertIn(b"chapter 1", response.data)
        self.assertNotIn(b"tuomo", response.data)

    def test_public_word_page_is_visible_without_login(self):
        self.login_user()
        data = self.valid_entry()
        data["word"] = "recalcitrant"
        data["definition"] = "Stubbornly resistant to authority or guidance."
        data["synonyms"] = ["stubborn", "defiant"]
        data["examples"] = ["The recalcitrant student refused to revise the essay."]
        self.create_entry(data)
        self.logout_user()

        response = self.client.get("/words/recalcitrant")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'<h1 class="word-title">Recalcitrant</h1>', response.data)
        self.assertIn(
            b"Recalcitrant means stubbornly resistant to authority or guidance.",
            response.data,
        )
        self.assertIn(b"Recalcitrant Definition", response.data)
        self.assertIn(b"Recalcitrant Synonyms", response.data)
        self.assertIn(b"How To Use Recalcitrant In A Sentence", response.data)
        self.assertIn(b"Stubbornly resistant to authority or guidance.", response.data)
        self.assertIn(b"recalcitrant student", response.data)
        self.assertIn(b"Recalcitrant Meaning, Definition, Synonyms, and Examples", response.data)
        self.assertIn(b'rel="canonical"', response.data)
        self.assertIn(b'application/ld+json', response.data)
        self.assertNotIn(b"Edit", response.data)
        self.assertNotIn(b"Practice usage", response.data)

    def test_public_word_page_shows_gre_list_context(self):
        self.login_user()
        data = self.valid_entry()
        data["word"] = "abound"
        data["definition"] = "To exist in large numbers."
        data["examples"] = ["Wildflowers abound in the meadow."]
        self.create_entry(data)
        self.logout_user()

        response = self.client.get("/words/abound")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"GRE: GregMat", response.data)
        self.assertIn(b"Abound appears in", response.data)
        self.assertIn(b"GregMat", response.data)

    def test_public_word_page_uses_readable_part_of_speech_copy(self):
        self.login_user()
        data = self.valid_entry()
        data["word"] = "recalcitrant"
        data["definition"] = "Stubbornly resistant to authority or guidance."
        data["part_of_speech"] = "adjective"
        self.create_entry(data)
        self.logout_user()

        response = self.client.get("/words/recalcitrant")

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            b"Recalcitrant is an adjective that means stubbornly resistant to authority or guidance.",
            response.data,
        )
        self.assertIn(b"Recalcitrant is an adjective.", response.data)
        self.assertNotIn(b"Recalcitrant is a adjective", response.data)

    def test_public_word_meaning_url_redirects_to_canonical_word_page(self):
        self.login_user()
        self.create_entry_with_word("recalcitrant")
        self.logout_user()

        response = self.client.get("/words/recalcitrant-meaning")

        self.assertEqual(response.status_code, 301)
        self.assertEqual(response.headers["Location"], "/words/recalcitrant")

    def test_public_words_page_lists_vocabulary_without_login(self):
        self.login_user()
        self.create_entry_with_word("recalcitrant")
        self.logout_user()

        response = self.client.get("/words")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Vocabulary Meanings", response.data)
        self.assertIn(b'href="/words/recalcitrant"', response.data)
        self.assertNotIn(b"Add word", response.data)

    def test_sitemap_lists_public_word_pages(self):
        self.login_user()
        self.create_entry_with_word("recalcitrant")
        self.logout_user()

        response = self.client.get("/sitemap.xml", base_url="https://example.com")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/xml")
        self.assertIn(b"https://example.com/words/recalcitrant", response.data)

    def test_robots_txt_points_to_sitemap(self):
        response = self.client.get("/robots.txt", base_url="https://example.com")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "text/plain")
        self.assertIn(b"User-agent: *", response.data)
        self.assertIn(b"Sitemap: https://example.com/sitemap.xml", response.data)

    def test_vocabulary_page_lists_entries_without_login(self):
        self.login_user()
        vocabulary_id = self.create_entry_with_word("recalcitrant").get_json()["id"]
        self.logout_user()

        response = self.client.get("/vocabulary")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"recalcitrant", response.data)
        self.assertIn(b'href="/words/recalcitrant"', response.data)
        self.assertNotIn(f'href="/vocabulary/{vocabulary_id}/page"'.encode(), response.data)
        self.assertNotIn(b"Add word", response.data)
        self.assertNotIn(b"Edit", response.data)
        self.assertNotIn(b'data-filter-toggle', response.data)

    def test_vocabulary_page_keeps_app_detail_links_for_logged_in_user(self):
        self.login_user()
        vocabulary_id = self.create_entry_with_word("recalcitrant").get_json()["id"]

        response = self.client.get("/vocabulary")

        self.assertEqual(response.status_code, 200)
        self.assertIn(f'href="/vocabulary/{vocabulary_id}/page"'.encode(), response.data)

    def test_create_vocabulary_persists_up_to_four_domains_in_order(self):
        self.login_user()
        data = self.valid_entry()
        data["domains"] = ["cognition", "communication", "society", "power"]

        response = self.create_entry(data)

        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.get_json()["domains"],
            ["cognition", "communication", "society", "power"],
        )

    def test_new_vocabulary_form_saves_sources(self):
        self.login_user()

        response = self.client.post(
            "/vocabulary/new",
            data={
                "word": "gingerly",
                "definition": "In a careful or cautious manner.",
                "context": "Literary",
                "part_of_speech": "adverb",
                "synonyms": "carefully",
                "examples": "He stepped gingerly over the stones.",
                "sources": "The Crossing; Cormac McCarthy; chapter 1",
            },
            headers=self.csrf_headers(),
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"The Crossing", response.data)
        self.assertIn(b"Cormac McCarthy", response.data)
        self.assertIn(b"chapter 1", response.data)

    def test_new_vocabulary_form_rejects_missing_csrf_token(self):
        self.login_user()

        response = self.client.post(
            "/vocabulary/new",
            data={
                "word": "gingerly",
                "definition": "In a careful or cautious manner.",
                "context": "Literary",
                "part_of_speech": "adverb",
                "examples": "He stepped gingerly over the stones.",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "Invalid CSRF token")

    def test_source_parser_keeps_pipe_separator_compatibility(self):
        self.login_user()
        data = self.valid_entry()
        data["sources"] = ["The Crossing | Cormac McCarthy | chapter 1"]

        response = self.create_entry(data)

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["sources"][0]["name"], "The Crossing")
        self.assertEqual(response.get_json()["sources"][0]["author"], "Cormac McCarthy")
        self.assertEqual(response.get_json()["sources"][0]["note"], "chapter 1")

    def test_new_vocabulary_form_preserves_ordered_domain_field(self):
        self.login_user()

        response = self.client.post(
            "/vocabulary/new",
            data={
                "word": "totter",
                "definition": "To move in a feeble, unsteady, or shaky way.",
                "context": "General",
                "part_of_speech": "verb",
                "domains": ["quality", "movement"],
                "domains_order": "movement,quality",
                "synonyms": "stagger, wobble",
                "examples": "\n".join(
                    [
                        "The exhausted hiker began to totter near the summit.",
                        "The old table seemed to totter on the uneven floor.",
                    ]
                ),
                "cloze_sentences": "\n".join(
                    [
                        "The exhausted hiker began to ____ near the summit.",
                        "The old table seemed to ____ on the uneven floor.",
                    ]
                ),
            },
            headers=self.csrf_headers(),
        )

        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            vocabulary_id = db.query(
                "SELECT id FROM vocabulary_entries WHERE word = ?",
                ["totter"],
            )[0]["id"]
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
        self.assertEqual(domains, ["movement", "quality"])

    def test_create_vocabulary_persists_ai_assessment(self):
        self.login_user()
        data = self.valid_entry()
        data.update(
            {
                "domains": ["cognition", "communication", "reasoning"],
                "needs_attention": "The context label may need review.",
                "confidence_score": 81,
                "gre_rating": "high",
            }
        )

        response = self.create_entry(data)

        self.assertEqual(response.status_code, 201)
        body = response.get_json()
        self.assertEqual(body["needs_attention"], "The context label may need review.")
        self.assertEqual(body["confidence_score"], 81)
        self.assertEqual(body["gre_rating"], "high")
        self.assertEqual(body["confidence_obsolete"], 0)

    def test_vocabulary_page_filters_by_gre_rating(self):
        self.login_user()
        high_data = self.valid_entry()
        high_data["word"] = "abstruse"
        high_data["definition"] = "Difficult to understand."
        high_data["examples"] = ["The lecture was abstruse."]
        high_data["gre_rating"] = "high"
        low_data = self.valid_entry()
        low_data["word"] = "plainword"
        low_data["definition"] = "An ordinary test word."
        low_data["examples"] = ["This is a plainword example."]
        low_data["gre_rating"] = "low"
        self.create_entry(high_data)
        self.create_entry(low_data)

        response = self.client.get("/vocabulary", query_string={"gre_rating": "high"})

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"abstruse", response.data)
        self.assertNotIn(b"plainword", response.data)
        self.assertIn(b"GRE: high", response.data)

    def test_create_vocabulary_rejects_invalid_ai_assessment(self):
        self.login_user()
        data = self.valid_entry()
        data["needs_attention"] = "x" * 201
        data["confidence_score"] = 101

        response = self.create_entry(data)

        self.assertEqual(response.status_code, 400)

    def test_create_vocabulary_accepts_expanded_domain_catalog(self):
        self.login_user()
        data = self.valid_entry()
        data["domains"] = ["quality", "relation", "judgment", "truth"]

        response = self.create_entry(data)

        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.get_json()["domains"],
            ["quality", "relation", "judgment", "truth"],
        )

    def test_create_vocabulary_rejects_more_than_four_domains(self):
        self.login_user()
        data = self.valid_entry()
        data["domains"] = [
            "emotion",
            "attitude",
            "cognition",
            "communication",
            "morality",
        ]

        response = self.create_entry(data)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.get_json()["error"],
            "Vocabulary entry must have at most 4 domains",
        )

    def test_create_vocabulary_rejects_unknown_domain(self):
        self.login_user()
        data = self.valid_entry()
        data["domains"] = ["technology"]

        response = self.create_entry(data)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "Vocabulary domain is invalid")

    def test_different_users_cannot_create_duplicate_global_word_sense(self):
        self.login_user()
        first_response = self.create_entry()
        self.logout_user()
        self.login_second_user()
        self.make_user_trusted("anna")
        self.logout_user()
        self.login_existing_second_user()

        second_response = self.create_entry()

        self.assertEqual(first_response.status_code, 201)
        self.assertEqual(second_response.status_code, 400)
        self.assertEqual(
            second_response.get_json()["error"],
            "Vocabulary entry already exists for this word sense",
        )

    def test_create_vocabulary_allows_same_word_with_different_sense(self):
        self.login_user()
        noun_data = self.valid_entry()
        noun_data["word"] = "hobble"
        noun_data["definition"] = "A restraint used to limit an animal's movement."
        noun_data["part_of_speech"] = "noun"
        noun_data["context"] = "Literary"
        verb_data = self.valid_entry()
        verb_data["word"] = "hobble"
        verb_data["definition"] = "To walk in an awkward or impaired way."
        verb_data["part_of_speech"] = "verb"
        verb_data["context"] = "Literary"

        noun_response = self.create_entry(noun_data)
        verb_response = self.create_entry(verb_data)

        self.assertEqual(noun_response.status_code, 201)
        self.assertEqual(verb_response.status_code, 201)
        self.assertEqual(noun_response.get_json()["word"], "hobble")
        self.assertEqual(verb_response.get_json()["word"], "hobble")

    def test_create_vocabulary_allows_sql_statement_text(self):
        self.login_user()
        data = self.valid_entry()
        data["word"] = "operation'; DROP TABLE users; --"

        response = self.create_entry(data)

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["word"], "operation'; DROP TABLE users; --")

    def test_generate_vocabulary_requires_login(self):
        response = self.generate_entry("operation")

        self.assertEqual(response.status_code, 401)

    def test_generate_vocabulary_rejects_missing_csrf_token(self):
        self.login_user()

        response = self.generate_entry("operation", include_csrf=False)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "Invalid CSRF token")

    def test_generate_vocabulary_rejects_invalid_csrf_token(self):
        self.login_user()
        with self.client.session_transaction() as session:
            session[CSRF_SESSION_KEY] = "valid-token"

        response = self.client.post(
            "/vocabulary/generate",
            json={"word": "operation"},
            headers={"X-CSRF-Token": "wrong-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "Invalid CSRF token")

    def test_generate_vocabulary_succeeds_when_logged_in(self):
        self.login_user()
        generated_entry = self.valid_entry()

        with patch(
            "Views.vocabulary.vocabulary_ai_service.generate_entry",
            return_value=(generated_entry, None),
        ) as generate_entry:
            response = self.generate_entry("operation")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json(),
            {
                **generated_entry,
                "part_of_speech": "other",
                "frequency_band": None,
                "frequency_note": None,
                "gre_rating": None,
                "domains": [],
                "cloze_sentences": [],
                "needs_attention": None,
                "confidence_score": None,
            },
        )
        generate_entry.assert_called_once_with(
            "operation",
            "test-api-key",
            "test-model",
            None,
        )

    def test_generate_vocabulary_accepts_semicolons_in_generated_prose(self):
        self.login_user()
        generated_entry = self.valid_entry()
        generated_entry["word"] = "stultify"
        generated_entry["definition"] = (
            "To cause someone to lose enthusiasm or initiative; to make ineffective."
        )
        generated_entry["examples"] = [
            "The rigid process stultified the team; it left no room for judgment."
        ]

        with patch(
            "Views.vocabulary.vocabulary_ai_service.generate_entry",
            return_value=(generated_entry, None),
        ):
            response = self.generate_entry("stultify")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json(),
            {
                **generated_entry,
                "part_of_speech": "other",
                "frequency_band": None,
                "frequency_note": None,
                "gre_rating": None,
                "domains": [],
                "cloze_sentences": [],
                "needs_attention": None,
                "confidence_score": None,
            },
        )

    def test_generate_vocabulary_passes_usage_clue_to_ai(self):
        self.login_user()
        generated_entry = self.valid_entry()
        generated_entry["word"] = "hobble"
        generated_entry["part_of_speech"] = "noun"
        generated_entry["frequency_band"] = "specialized"
        generated_entry["frequency_note"] = "A riding-related noun sense."

        with patch(
            "Views.vocabulary.vocabulary_ai_service.generate_entry",
            return_value=(generated_entry, None),
        ) as generate_entry:
            response = self.generate_entry(
                "hobble",
                usage_clue="He loosened the horse's (hobble).",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["part_of_speech"], "noun")
        self.assertEqual(response.get_json()["frequency_band"], "specialized")
        generate_entry.assert_called_once_with(
            "hobble",
            "test-api-key",
            "test-model",
            "He loosened the horse's (hobble).",
        )

    def test_generate_vocabulary_rejects_sql_injection(self):
        self.login_user()

        response = self.generate_entry("operation'; DROP TABLE users; --")

        self.assertEqual(response.status_code, 400)

    def test_generate_vocabulary_accepts_sql_keyword_as_word(self):
        self.login_user()
        generated_entry = self.valid_entry()
        generated_entry["word"] = "DROP"

        with patch(
            "Views.vocabulary.vocabulary_ai_service.generate_entry",
            return_value=(generated_entry, None),
        ) as generate_entry:
            response = self.generate_entry("DROP")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json(),
            {
                **generated_entry,
                "part_of_speech": "other",
                "frequency_band": None,
                "frequency_note": None,
                "gre_rating": None,
                "domains": [],
                "cloze_sentences": [],
                "needs_attention": None,
                "confidence_score": None,
            },
        )
        generate_entry.assert_called_once_with("DROP", "test-api-key", "test-model", None)

    def test_generate_vocabulary_rejects_more_than_one_word(self):
        self.login_user()

        response = self.generate_entry("two words")

        self.assertEqual(response.status_code, 400)

    def test_generate_vocabulary_rejects_html_tags(self):
        self.login_user()

        response = self.generate_entry("<b>word</b>")

        self.assertEqual(response.status_code, 400)

    def test_trusted_user_cannot_generate_more_than_daily_quota(self):
        self.login_user()
        generated_entry = self.valid_entry()

        with patch(
            "Views.vocabulary.vocabulary_ai_service.generate_entry",
            return_value=(generated_entry, None),
        ) as generate_entry:
            first_response = self.generate_entry("first")
            second_response = self.generate_entry("second")
            third_response = self.generate_entry("third")

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 200)
        self.assertEqual(third_response.status_code, 429)
        self.assertEqual(
            third_response.get_json()["error"],
            "Daily AI generation quota reached (2)",
        )
        self.assertEqual(generate_entry.call_count, 2)

    def test_admin_user_has_unlimited_ai_generation_quota(self):
        self.login_user()
        self.set_user_category("tuomo", "admin")
        generated_entry = self.valid_entry()

        with patch(
            "Views.vocabulary.vocabulary_ai_service.generate_entry",
            return_value=(generated_entry, None),
        ) as generate_entry:
            responses = [
                self.generate_entry("first"),
                self.generate_entry("second"),
                self.generate_entry("third"),
            ]

        self.assertEqual([response.status_code for response in responses], [200, 200, 200])
        self.assertEqual(generate_entry.call_count, 3)

    def test_invalid_ai_generation_request_does_not_use_daily_quota(self):
        self.login_user()
        invalid_response = self.generate_entry("two words")
        generated_entry = self.valid_entry()

        with patch(
            "Views.vocabulary.vocabulary_ai_service.generate_entry",
            return_value=(generated_entry, None),
        ) as generate_entry:
            first_response = self.generate_entry("first")
            second_response = self.generate_entry("second")

        self.assertEqual(invalid_response.status_code, 400)
        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 200)
        self.assertEqual(generate_entry.call_count, 2)

    def test_failed_ai_generation_does_not_use_daily_quota(self):
        self.login_user()

        with patch(
            "Views.vocabulary.vocabulary_ai_service.generate_entry",
            return_value=(None, "OpenAI request failed: TimeoutError"),
        ) as generate_entry:
            failed_response = self.generate_entry("first")

        self.assertEqual(failed_response.status_code, 400)
        self.assertEqual(generate_entry.call_count, 1)
        self.assertEqual(self.ai_generation_count("tuomo"), 0)

    def test_invalid_generated_entry_does_not_use_daily_quota(self):
        self.login_user()
        generated_entry = self.valid_entry()
        generated_entry["definition"] = "<b>unsafe</b>"

        with patch(
            "Views.vocabulary.vocabulary_ai_service.generate_entry",
            return_value=(generated_entry, None),
        ) as generate_entry:
            failed_response = self.generate_entry("first")

        self.assertEqual(failed_response.status_code, 400)
        self.assertEqual(generate_entry.call_count, 1)
        self.assertEqual(self.ai_generation_count("tuomo"), 0)

    def test_basic_user_cannot_create_vocabulary(self):
        self.login_user()
        self.logout_user()
        self.login_basic_second_user()

        response = self.create_entry()

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()["error"], "Trusted account is required")

    def test_basic_user_cannot_open_new_vocabulary_page(self):
        self.login_user()
        self.logout_user()
        self.login_basic_second_user()

        response = self.client.get("/vocabulary/new", follow_redirects=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Trusted account is required", response.data)

    def test_search_page_add_word_link_passes_search_word(self):
        self.login_user()
        self.logout_user()
        self.client.post(
            "/login",
            json={"username": "tuomo", "password": "safe-password"},
        )

        response = self.client.get("/vocabulary", query_string={"word": "stultify"})

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'href="/vocabulary/new?word=stultify"', response.data)

    def test_vocabulary_page_marks_own_entries_without_usernames(self):
        self.login_user()
        self.create_entry_with_word("firstword")
        self.logout_user()
        self.login_second_user()
        self.make_user_trusted("anna")
        self.create_entry_with_word("secondword")

        response = self.client.get("/vocabulary")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertRegex(html, r'data-owned="false"[\s\S]*firstword')
        self.assertRegex(html, r'data-owned="true"[\s\S]*secondword')
        self.assertNotIn("tuomo", html)
        self.assertNotIn("anna", html)

    def test_vocabulary_page_marks_own_entries_when_session_user_id_is_string(self):
        self.login_user()
        self.create_entry_with_word("firstword")
        with self.client.session_transaction() as session:
            session["user_id"] = str(session["user_id"])

        response = self.client.get("/vocabulary")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'data-filter-toggle', response.data)
        self.assertIn(b'data-owned="true"', response.data)

    def test_vocabulary_page_hides_ownership_filter_when_user_has_no_own_entries(self):
        self.login_user()
        self.create_entry_with_word("firstword")
        self.logout_user()
        self.login_second_user()

        response = self.client.get("/vocabulary")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"firstword", response.data)
        self.assertNotIn(b'data-filter-toggle', response.data)
        self.assertNotIn(b"Own</button>", response.data)

    def test_new_vocabulary_page_prefills_word_from_search_query(self):
        self.login_user()

        response = self.client.get("/vocabulary/new", query_string={"word": "stultify"})

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'id="word" name="word" value="stultify"', response.data)

    def test_new_vocabulary_page_includes_csrf_token(self):
        self.login_user()

        response = self.client.get("/vocabulary/new")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'name="csrf_token"', response.data)

    def test_new_vocabulary_page_collapses_optional_ai_example_sentence(self):
        self.login_user()

        response = self.client.get("/vocabulary/new")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Add optional example sentence for AI", response.data)
        self.assertIn(b'id="usage-clue-panel" class="optional-ai-example-panel" hidden', response.data)
        self.assertIn(b'id="usage_clue" name="usage_clue"', response.data)

    def test_vocabulary_page_filters_by_source_and_author(self):
        self.login_user()
        crossing_data = self.valid_entry()
        crossing_data["word"] = "hobble"
        crossing_data["definition"] = "A restraint used to limit an animal's movement."
        crossing_data["part_of_speech"] = "noun"
        crossing_data["sources"] = ["The Crossing; Cormac McCarthy; chapter 1"]
        medical_data = self.valid_entry()
        medical_data["word"] = "anodyne"
        medical_data["definition"] = "Something that relieves pain."
        medical_data["context"] = "Medical"
        medical_data["sources"] = ["Medical Notes; Ada Lovelace"]
        self.create_entry(crossing_data)
        self.create_entry(medical_data)

        response = self.client.get(
            "/vocabulary",
            query_string={
                "source_name": "Crossing",
                "source_author": "McCarthy",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"hobble", response.data)
        self.assertNotIn(b"anodyne", response.data)
        self.assertIn(b"Filters (2)", response.data)
        self.assertIn(b"source name: Crossing", response.data)
        self.assertNotIn(b'id="advanced-filter-panel" class="advanced-filter-panel" hidden', response.data)

    def test_vocabulary_page_hides_advanced_filters_by_default(self):
        self.login_user()
        self.create_entry_with_word("operation")

        response = self.client.get("/vocabulary")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Filters", response.data)
        self.assertIn(b"Book or article title", response.data)
        self.assertIn(b"Author name", response.data)
        self.assertNotIn(b'placeholder="The Crossing"', response.data)
        self.assertNotIn(b'placeholder="Cormac McCarthy"', response.data)
        html = response.get_data(as_text=True)
        self.assertLess(html.index('for="frequency_band"'), html.index('for="source_name"'))
        self.assertRegex(
            html,
            r'id="advanced-filter-panel"[\s\S]*class="advanced-filter-panel"[\s\S]*hidden',
        )

    def test_admin_new_vocabulary_page_renders_domain_controls(self):
        self.login_user()
        self.set_user_category("tuomo", "admin")

        response = self.client.get("/vocabulary/new")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'data-domain-selection-list', response.data)
        self.assertIn(b"No domains selected.", response.data)
        self.assertIn(b'name="domains"', response.data)
        self.assertIn(b'name="domains_order"', response.data)
        self.assertIn(b'value="emotion"', response.data)

    def test_trusted_user_new_vocabulary_page_hides_domain_editor(self):
        self.login_user()

        response = self.client.get("/vocabulary/new")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertNotIn('class="field field-wide domain-fieldset"', html)
        self.assertNotIn('<legend>Domains</legend>', html)
        self.assertNotIn('No domains selected.', html)
        self.assertNotIn('<input\n                            type="checkbox"\n                            name="domains"', html)
        self.assertIn('name="domains_order"', html)

    def test_trusted_user_vocabulary_pages_hide_domain_chips(self):
        self.login_user()
        entry_data = self.valid_entry()
        entry_data["domains"] = ["body"]
        create_response = self.create_entry(entry_data)
        entry_id = create_response.get_json()["id"]

        list_response = self.client.get("/vocabulary")
        detail_response = self.client.get(f"/vocabulary/{entry_id}/page")

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(detail_response.status_code, 200)
        self.assertNotIn(b'<span class="meta-chip">body</span>', list_response.data)
        self.assertNotIn(b'<span class="meta-chip">body</span>', detail_response.data)

    def test_admin_vocabulary_pages_show_domain_chips(self):
        self.login_user()
        entry_data = self.valid_entry()
        entry_data["domains"] = ["body"]
        create_response = self.create_entry(entry_data)
        entry_id = create_response.get_json()["id"]
        self.set_user_category("tuomo", "admin")

        list_response = self.client.get("/vocabulary")
        detail_response = self.client.get(f"/vocabulary/{entry_id}/page")

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(detail_response.status_code, 200)
        self.assertIn(b'<span class="meta-chip">body</span>', list_response.data)
        self.assertIn(b'<span class="meta-chip">body</span>', detail_response.data)

    def test_trusted_user_new_vocabulary_page_hides_ai_setup_check(self):
        self.login_user()

        response = self.client.get("/vocabulary/new")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b"Check AI setup", response.data)
        self.assertNotIn(b'id="check-ai-button"', response.data)

    def test_admin_new_vocabulary_page_shows_ai_setup_check(self):
        self.login_user()
        self.set_user_category("tuomo", "admin")

        response = self.client.get("/vocabulary/new")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Check AI setup", response.data)
        self.assertIn(b'id="check-ai-button"', response.data)

    def test_basic_user_cannot_generate_vocabulary_with_ai(self):
        self.login_user()
        self.logout_user()
        self.login_basic_second_user()

        response = self.generate_entry("operation")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()["error"], "Trusted account is required")

    def test_stale_trusted_session_cannot_create_vocabulary_after_demoted_in_database(self):
        self.login_user()
        self.set_user_category("tuomo", "basic")

        response = self.create_entry()

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()["error"], "Trusted account is required")

    def test_basic_user_cannot_check_ai_status(self):
        self.login_user()
        self.logout_user()
        self.login_basic_second_user()

        response = self.client.get("/vocabulary/generate/status")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()["error"], "Admin account is required")

    def test_trusted_user_cannot_check_ai_status(self):
        self.login_user()

        response = self.client.get("/vocabulary/generate/status")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()["error"], "Admin account is required")

    def test_admin_user_can_check_ai_status(self):
        self.login_user()
        self.set_user_category("tuomo", "admin")

        response = self.client.get("/vocabulary/generate/status")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json(),
            {
                "openai_api_key_present": True,
                "openai_api_key_prefix": "test-ap",
                "openai_model": "test-model",
            },
        )

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

    def test_view_vocabulary_succeeds_without_login(self):
        self.login_user()
        create_response = self.create_entry()
        vocabulary_id = create_response.get_json()["id"]
        self.logout_user()

        response = self.client.get(f"/vocabulary/{vocabulary_id}")

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["word"], "operation")
        self.assertNotIn("created_by", body)

    def test_view_vocabulary_succeeds_when_logged_in(self):
        self.login_user()
        create_response = self.create_entry()
        vocabulary_id = create_response.get_json()["id"]

        response = self.client.get(f"/vocabulary/{vocabulary_id}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["word"], "operation")

    def test_view_vocabulary_shows_another_users_entry_because_vocabs_are_global(self):
        self.login_user()
        create_response = self.create_entry()
        vocabulary_id = create_response.get_json()["id"]
        self.logout_user()
        self.login_second_user()

        response = self.client.get(f"/vocabulary/{vocabulary_id}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["word"], "operation")

    def test_vocabulary_page_shows_usage_practice_for_trusted_user(self):
        self.login_user()
        create_response = self.create_entry()
        vocabulary_id = create_response.get_json()["id"]

        response = self.client.get(f"/vocabulary/{vocabulary_id}/page")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Practice usage", response.data)
        self.assertIn(b'id="practice-toggle"', response.data)
        self.assertIn(b'aria-expanded="false"', response.data)
        self.assertIn(b'aria-controls="practice-panel"', response.data)
        self.assertIn(b'id="practice-panel" class="practice-panel" hidden', response.data)
        self.assertIn(b'id="practice-sentence"', response.data)
        self.assertIn(b"Validate sentence", response.data)

    def test_vocabulary_page_hides_usage_practice_for_basic_user(self):
        self.login_user()
        create_response = self.create_entry()
        vocabulary_id = create_response.get_json()["id"]
        self.logout_user()
        self.login_basic_second_user()

        response = self.client.get(f"/vocabulary/{vocabulary_id}/page")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b"Practice usage", response.data)
        self.assertNotIn(b'id="practice-sentence"', response.data)

    def test_vocabulary_page_hides_usage_practice_for_anonymous_user(self):
        self.login_user()
        create_response = self.create_entry()
        vocabulary_id = create_response.get_json()["id"]
        self.logout_user()

        response = self.client.get(f"/vocabulary/{vocabulary_id}/page")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"operation", response.data)
        self.assertNotIn(b"Practice usage", response.data)
        self.assertNotIn(b'id="practice-sentence"', response.data)
        self.assertNotIn(b"Edit", response.data)

    def test_vocabulary_detail_page_for_anonymous_user_canonicalizes_to_public_word(self):
        self.login_user()
        vocabulary_id = self.create_entry_with_word("recalcitrant").get_json()["id"]
        self.logout_user()

        response = self.client.get(f"/vocabulary/{vocabulary_id}/page")

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            b'<link rel="canonical" href="http://localhost/words/recalcitrant">',
            response.data,
        )
        self.assertIn(b'<meta name="robots" content="noindex,follow">', response.data)

    def test_vocabulary_detail_page_for_logged_in_user_has_canonical_without_noindex(self):
        self.login_user()
        vocabulary_id = self.create_entry_with_word("recalcitrant").get_json()["id"]

        response = self.client.get(f"/vocabulary/{vocabulary_id}/page")

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            b'<link rel="canonical" href="http://localhost/words/recalcitrant">',
            response.data,
        )
        self.assertNotIn(b'<meta name="robots" content="noindex,follow">', response.data)

    def test_view_vocabulary_does_not_allow_sql_injection(self):
        self.login_user()

        response = self.client.get("/vocabulary/1 OR 1=1")

        self.assertEqual(response.status_code, 404)

    def test_search_vocabulary_succeeds_without_login(self):
        self.login_user()
        self.create_entry_with_word("operation")
        self.logout_user()

        response = self.search_entries("oper*")

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual([entry["word"] for entry in body], ["operation"])
        self.assertNotIn("created_by", body[0])

    def test_search_vocabulary_supports_wildcard_at_end(self):
        self.login_user()
        self.create_entry_with_word("operation")
        self.create_entry_with_word("operate")
        self.create_entry_with_word("cooperate")

        response = self.search_entries("oper*")

        self.assertEqual(response.status_code, 200)
        words = [entry["word"] for entry in response.get_json()]
        self.assertEqual(words, ["operate", "operation"])

    def test_search_vocabulary_supports_wildcard_at_beginning(self):
        self.login_user()
        self.create_entry_with_word("operation")
        self.create_entry_with_word("cooperation")
        self.create_entry_with_word("operate")

        response = self.search_entries("*tion")

        self.assertEqual(response.status_code, 200)
        words = [entry["word"] for entry in response.get_json()]
        self.assertEqual(words, ["cooperation", "operation"])

    def test_search_vocabulary_supports_wildcard_in_middle(self):
        self.login_user()
        self.create_entry_with_word("operation")
        self.create_entry_with_word("opinion")
        self.create_entry_with_word("option")

        response = self.search_entries("op*ion")

        self.assertEqual(response.status_code, 200)
        words = [entry["word"] for entry in response.get_json()]
        self.assertEqual(words, ["operation", "opinion", "option"])

    def test_search_vocabulary_rejects_sql_injection(self):
        self.login_user()

        response = self.search_entries("operation'; DROP TABLE users; --")

        self.assertEqual(response.status_code, 400)

    def test_search_vocabulary_accepts_sql_keyword_as_word(self):
        self.login_user()
        self.create_entry_with_word("select")

        response = self.search_entries("select")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()[0]["word"], "select")

    def test_search_vocabulary_does_not_crash_when_nothing_is_found(self):
        self.login_user()
        self.create_entry_with_word("operation")

        response = self.search_entries("missing*")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), [])

    def test_search_vocabulary_returns_another_users_entry_because_vocabs_are_global(self):
        self.login_user()
        self.create_entry_with_word("operation")
        self.logout_user()
        self.login_second_user()

        response = self.search_entries("oper*")

        self.assertEqual(response.status_code, 200)
        self.assertEqual([entry["word"] for entry in response.get_json()], ["operation"])

    def test_practice_usage_requires_login(self):
        response = self.client.post(
            "/vocabulary/1/practice-usage",
            json={"sentence": "The operation was careful."},
            headers=self.csrf_headers(),
        )

        self.assertEqual(response.status_code, 401)

    def test_practice_usage_rejects_missing_csrf_token(self):
        self.login_user()
        create_response = self.create_entry()
        vocabulary_id = create_response.get_json()["id"]

        response = self.practice_usage(
            vocabulary_id,
            "The operation was careful.",
            include_csrf=False,
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "Invalid CSRF token")

    def test_basic_user_cannot_practice_usage(self):
        self.login_user()
        create_response = self.create_entry()
        vocabulary_id = create_response.get_json()["id"]
        self.logout_user()
        self.login_basic_second_user()

        response = self.practice_usage(vocabulary_id, "The operation was careful.")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()["error"], "Trusted account is required")

    def test_practice_usage_returns_correct_result(self):
        self.login_user()
        create_response = self.create_entry()
        vocabulary_id = create_response.get_json()["id"]

        with patch(
            "Views.vocabulary.vocabulary_ai_service.validate_usage",
            return_value=({"result": "correct", "hint": ""}, None),
        ) as validate_usage:
            response = self.practice_usage(
                vocabulary_id,
                "The operation was carefully planned.",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"result": "correct", "hint": ""})
        validate_usage.assert_called_once()
        self.assertEqual(validate_usage.call_args.args[1], "The operation was carefully planned.")
        self.assertEqual(validate_usage.call_args.args[2], "test-api-key")
        self.assertEqual(validate_usage.call_args.args[3], "test-model")
        self.assertEqual(self.ai_generation_total_count("tuomo"), 1)

    def test_practice_usage_returns_incorrect_result_with_hint(self):
        self.login_user()
        create_response = self.create_entry()
        vocabulary_id = create_response.get_json()["id"]

        with patch(
            "Views.vocabulary.vocabulary_ai_service.validate_usage",
            return_value=(
                {
                    "result": "incorrect",
                    "hint": "Use operation to describe an action or procedure.",
                },
                None,
            ),
        ):
            response = self.practice_usage(vocabulary_id, "The operation was blue.")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json(),
            {
                "result": "incorrect",
                "hint": "Use operation to describe an action or procedure.",
            },
        )

    def test_failed_practice_usage_does_not_use_daily_quota(self):
        self.login_user()
        create_response = self.create_entry()
        vocabulary_id = create_response.get_json()["id"]

        with patch(
            "Views.vocabulary.vocabulary_ai_service.validate_usage",
            return_value=(None, "OpenAI returned invalid usage validation data"),
        ):
            response = self.practice_usage(vocabulary_id, "The operation was careful.")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.ai_generation_total_count("tuomo"), 0)

    def test_trusted_user_cannot_practice_usage_more_than_daily_quota(self):
        self.login_user()
        create_response = self.create_entry()
        vocabulary_id = create_response.get_json()["id"]

        with patch(
            "Views.vocabulary.vocabulary_ai_service.validate_usage",
            return_value=({"result": "correct", "hint": ""}, None),
        ) as validate_usage:
            first_response = self.practice_usage(vocabulary_id, "The operation was first.")
            second_response = self.practice_usage(vocabulary_id, "The operation was second.")
            third_response = self.practice_usage(vocabulary_id, "The operation was third.")

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 200)
        self.assertEqual(third_response.status_code, 429)
        self.assertEqual(validate_usage.call_count, 2)

    def test_admin_user_has_unlimited_practice_usage_quota(self):
        self.login_user()
        self.set_user_category("tuomo", "admin")
        create_response = self.create_entry()
        vocabulary_id = create_response.get_json()["id"]

        with patch(
            "Views.vocabulary.vocabulary_ai_service.validate_usage",
            return_value=({"result": "correct", "hint": ""}, None),
        ) as validate_usage:
            responses = [
                self.practice_usage(vocabulary_id, "The operation was first."),
                self.practice_usage(vocabulary_id, "The operation was second."),
                self.practice_usage(vocabulary_id, "The operation was third."),
            ]

        self.assertEqual([response.status_code for response in responses], [200, 200, 200])
        self.assertEqual(validate_usage.call_count, 3)

    def test_update_vocabulary_requires_login(self):
        response = self.client.put("/vocabulary/1", json=self.valid_entry())

        self.assertEqual(response.status_code, 401)

    def test_update_vocabulary_rejects_missing_csrf_token(self):
        self.login_user()
        create_response = self.create_entry()
        vocabulary_id = create_response.get_json()["id"]

        response = self.update_entry(
            vocabulary_id,
            self.valid_entry(),
            include_csrf=False,
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "Invalid CSRF token")

    def test_update_vocabulary_succeeds_when_logged_in(self):
        self.login_user()
        create_data = self.valid_entry()
        create_data["gre_rating"] = "high"
        create_response = self.create_entry(create_data)
        vocabulary_id = create_response.get_json()["id"]
        data = self.valid_entry()
        data["definition"] = "A controlled activity"
        data["synonyms"] = ["activity"]
        data["examples"] = ["The operation was successful."]

        response = self.update_entry(vocabulary_id, data)

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["definition"], "A controlled activity")
        self.assertEqual(body["synonyms"], ["activity"])
        self.assertEqual(body["examples"], ["The operation was successful."])
        self.assertEqual(body["gre_rating"], "high")

    def test_update_vocabulary_replaces_domains(self):
        self.login_user()
        data = self.valid_entry()
        data["domains"] = ["body", "movement"]
        vocabulary_id = self.create_entry(data).get_json()["id"]
        data["domains"] = ["communication", "society"]

        response = self.update_entry(vocabulary_id, data)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["domains"], ["communication", "society"])

    def test_manual_vocabulary_update_marks_confidence_obsolete(self):
        self.login_user()
        data = self.valid_entry()
        data.update(
            {
                "domains": ["cognition", "communication", "reasoning"],
                "needs_attention": "",
                "confidence_score": 93,
            }
        )
        vocabulary_id = self.create_entry(data).get_json()["id"]
        data["definition"] = "An updated definition"

        response = self.update_entry(vocabulary_id, data)

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["confidence_score"], 93)
        self.assertEqual(body["confidence_obsolete"], 1)

    def test_update_vocabulary_can_update_another_users_entry_because_vocabs_are_global(self):
        self.login_user()
        create_response = self.create_entry()
        vocabulary_id = create_response.get_json()["id"]
        self.logout_user()
        self.login_second_user()
        self.make_user_trusted("anna")
        self.logout_user()
        self.login_existing_second_user()
        data = self.valid_entry()
        data["definition"] = "Updated global definition"

        response = self.update_entry(vocabulary_id, data)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["definition"], "Updated global definition")

    def test_basic_user_cannot_update_vocabulary(self):
        self.login_user()
        create_response = self.create_entry()
        vocabulary_id = create_response.get_json()["id"]
        self.logout_user()
        self.login_basic_second_user()
        data = self.valid_entry()
        data["definition"] = "Updated global definition"

        response = self.update_entry(vocabulary_id, data)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()["error"], "Trusted account is required")

    def test_basic_user_cannot_open_edit_vocabulary_page(self):
        self.login_user()
        create_response = self.create_entry()
        vocabulary_id = create_response.get_json()["id"]
        self.logout_user()
        self.login_basic_second_user()

        response = self.client.get(
            f"/vocabulary/{vocabulary_id}/edit",
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Trusted account is required", response.data)

    def test_edit_vocabulary_form_rejects_missing_csrf_token(self):
        self.login_user()
        create_response = self.create_entry()
        vocabulary_id = create_response.get_json()["id"]

        response = self.client.post(
            f"/vocabulary/{vocabulary_id}/edit",
            data={
                "word": "operation",
                "definition": "Updated by forged form",
                "context": "Technical",
                "part_of_speech": "other",
                "examples": "The operation was carefully planned.",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "Invalid CSRF token")

    def test_edit_vocabulary_form_succeeds_with_csrf_token(self):
        self.login_user()
        create_response = self.create_entry()
        vocabulary_id = create_response.get_json()["id"]

        response = self.client.post(
            f"/vocabulary/{vocabulary_id}/edit",
            data={
                "word": "operation",
                "definition": "Updated from the edit form.",
                "context": "Technical",
                "part_of_speech": "other",
                "examples": "The operation was carefully planned.",
            },
            headers=self.csrf_headers(),
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Updated from the edit form.", response.data)

    def test_update_vocabulary_allows_sql_statement_text(self):
        self.login_user()
        create_response = self.create_entry()
        vocabulary_id = create_response.get_json()["id"]
        data = self.valid_entry()
        data["context"] = "Medical'; DROP TABLE users; --"

        response = self.update_entry(vocabulary_id, data)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["context"], "")

    def test_update_vocabulary_rejects_html_tags(self):
        self.login_user()
        create_response = self.create_entry()
        vocabulary_id = create_response.get_json()["id"]
        data = self.valid_entry()
        data["examples"] = ["<script>alert('x')</script>"]

        response = self.update_entry(vocabulary_id, data)

        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
