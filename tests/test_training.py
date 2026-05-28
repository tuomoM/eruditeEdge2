import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime, timedelta, timezone

import db
from app import create_app
from csrf import CSRF_SESSION_KEY
from db import init_db
from Repositories.training_repository import TrainingRepository


class PositioningRandomizer:
    def __init__(self, correct_vocabulary_id, correct_position):
        self._correct_vocabulary_id = correct_vocabulary_id
        self._correct_position = correct_position

    def shuffle(self, values):
        values.remove(self._correct_vocabulary_id)
        values.insert(self._correct_position, self._correct_vocabulary_id)


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
        invite_code = self.create_invite_code()
        self.client.post(
            "/register",
            json={
                "username": "tuomo",
                "password": "safe-password",
                "invite_code": invite_code,
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
            headers=self.registration_csrf_headers(),
        )

    def registration_csrf_headers(self):
        with self.client.session_transaction() as session:
            session[CSRF_SESSION_KEY] = "test-registration-csrf-token"
        return {"X-CSRF-Token": "test-registration-csrf-token"}

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

    def valid_entry(self, word):
        return {
            "word": word,
            "definition": f"Definition for {word}",
            "context": "Training",
            "synonyms": [f"{word} synonym"],
            "examples": [f"{word} appears in this sentence."],
        }

    def sample_words(self):
        return [
            "Ubiquitous",
            "curfew",
            "myopic",
            "indignation",
            "predillection",
        ]

    def create_sample_vocabs(self):
        vocabulary_ids = []
        for word in self.sample_words():
            response = self.client.post("/vocabulary", json=self.valid_entry(word))
            vocabulary_ids.append(response.get_json()["id"])
        return vocabulary_ids

    def create_vocab_with_unique_word(self, index):
        word = f"word{index}"
        response = self.client.post("/vocabulary", json=self.valid_entry(word))
        return response.get_json()["id"]

    def definitions_by_id(self, vocabulary_ids):
        return {
            str(vocabulary_id): self.valid_entry(word)["definition"]
            for vocabulary_id, word in zip(vocabulary_ids, self.sample_words())
        }

    def definitions_by_word(self):
        return {
            word: self.valid_entry(word)["definition"]
            for word in self.sample_words()
        }

    def correct_answers_from_quiz(self, training):
        definitions_by_word = self.definitions_by_word()
        answers = {}
        for question in training["questions"]:
            correct_definition = definitions_by_word[question["vocab"]["word"]]
            answers[question["token"]] = next(
                option["token"]
                for option in question["options"]
                if option["definition"] == correct_definition
            )
        return answers

    def _option_set_signature(self, training):
        return {
            question["vocab"]["word"]: tuple(
                sorted(option["definition"] for option in question["options"])
            )
            for question in training["questions"]
        }

    def create_training(self, vocabulary_ids):
        return self.client.post(
            "/training",
            json={"vocabulary_ids": vocabulary_ids},
        )

    def submit_training(self, training_session_id, answers):
        return self.client.post(
            f"/training/{training_session_id}/submit",
            json={"answers": answers},
        )

    def test_training_selection_requires_login(self):
        response = self.create_training([1])

        self.assertEqual(response.status_code, 401)

    def test_training_creation_rejects_malformed_json(self):
        self.login_user()

        response = self.client.post("/training", json=["not-a-dict"])

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "Invalid request")

    def test_training_creation_rejects_string_vocabulary_ids(self):
        self.login_user()

        response = self.client.post("/training", json={"vocabulary_ids": "12"})

        self.assertEqual(response.status_code, 400)

    def test_training_creation_rejects_integer_vocabulary_ids(self):
        self.login_user()

        response = self.client.post("/training", json={"vocabulary_ids": 12})

        self.assertEqual(response.status_code, 400)

    def test_training_creation_rejects_object_vocabulary_ids(self):
        self.login_user()

        response = self.client.post("/training", json={"vocabulary_ids": {"1": True}})

        self.assertEqual(response.status_code, 400)

    def test_training_creation_rejects_bool_and_float_vocabulary_ids(self):
        self.login_user()

        bool_response = self.client.post("/training", json={"vocabulary_ids": [True]})
        float_response = self.client.post("/training", json={"vocabulary_ids": [1.9]})

        self.assertEqual(bool_response.status_code, 400)
        self.assertEqual(float_response.status_code, 400)

    def test_training_creation_allows_maximum_selection_size(self):
        self.login_user()
        vocabulary_ids = [
            self.create_vocab_with_unique_word(index)
            for index in range(50)
        ]

        response = self.create_training(vocabulary_ids)

        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(response.get_json()["questions"]), 50)

    def test_training_creation_rejects_more_than_maximum_selection_size(self):
        self.login_user()
        vocabulary_ids = [
            self.create_vocab_with_unique_word(index)
            for index in range(51)
        ]

        response = self.create_training(vocabulary_ids)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.get_json()["error"],
            "Choose at most 50 vocabulary entries",
        )

    def test_one_vocab_can_be_chosen_for_training(self):
        self.login_user()
        vocabulary_ids = self.create_sample_vocabs()

        response = self.create_training(vocabulary_ids[:1])

        self.assertEqual(response.status_code, 201)
        body = response.get_json()
        self.assertNotIn("vocabulary_ids", body)
        self.assertEqual(len(body["questions"]), 1)

    def test_two_vocabs_can_be_chosen_for_training(self):
        self.login_user()
        vocabulary_ids = self.create_sample_vocabs()

        response = self.create_training(vocabulary_ids[:2])

        self.assertEqual(response.status_code, 201)
        body = response.get_json()
        self.assertNotIn("vocabulary_ids", body)
        self.assertEqual(len(body["questions"]), 2)

    def test_two_vocabs_can_be_chosen_from_html_form(self):
        self.login_user()
        vocabulary_ids = self.create_sample_vocabs()

        response = self.client.post(
            "/training",
            data={"vocabulary_ids": [str(vocabulary_ids[0]), str(vocabulary_ids[1])]},
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"2 vocabulary entries selected.", response.data)

    def test_training_selection_preselects_latest_training_vocabs(self):
        self.login_user()
        vocabulary_ids = self.create_sample_vocabs()
        self.create_training(vocabulary_ids[:1])
        self.create_training([vocabulary_ids[2], vocabulary_ids[4]])

        response = self.client.get("/training/select")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertNotRegex(html, rf'value="{vocabulary_ids[0]}"[^>]*checked')
        self.assertRegex(html, rf'value="{vocabulary_ids[2]}"[^>]*checked')
        self.assertRegex(html, rf'value="{vocabulary_ids[4]}"[^>]*checked')

    def test_five_vocabs_can_be_chosen_for_training(self):
        self.login_user()
        vocabulary_ids = self.create_sample_vocabs()

        response = self.create_training(vocabulary_ids)

        self.assertEqual(response.status_code, 201)
        body = response.get_json()
        self.assertNotIn("vocabulary_ids", body)
        self.assertEqual(len(body["questions"]), 5)
        for question in body["questions"]:
            self.assertEqual(len(question["options"]), 5)

    def test_more_than_five_vocabs_limit_each_question_to_five_options(self):
        self.login_user()
        vocabulary_ids = [
            self.create_vocab_with_unique_word(index)
            for index in range(6)
        ]

        response = self.create_training(vocabulary_ids)

        self.assertEqual(response.status_code, 201)
        training = response.get_json()
        self.assertEqual(len(training["questions"]), 6)
        for question in training["questions"]:
            option_definitions = [
                option["definition"]
                for option in question["options"]
            ]
            self.assertEqual(len(option_definitions), 5)
            self.assertEqual(len(set(option_definitions)), 5)
            self.assertIn(
                f"Definition for {question['vocab']['word']}",
                option_definitions,
            )

    def test_more_than_five_vocabs_randomize_option_sets_between_sessions(self):
        self.login_user()
        vocabulary_ids = [
            self.create_vocab_with_unique_word(index)
            for index in range(8)
        ]

        first_response = self.create_training(vocabulary_ids)
        second_response = self.create_training(vocabulary_ids)

        self.assertEqual(first_response.status_code, 201)
        self.assertEqual(second_response.status_code, 201)
        first_signature = self._option_set_signature(first_response.get_json())
        second_signature = self._option_set_signature(second_response.get_json())
        self.assertNotEqual(first_signature, second_signature)

    def test_training_creation_does_not_return_answer_key(self):
        self.login_user()
        vocabulary_ids = self.create_sample_vocabs()[:2]

        response = self.create_training(vocabulary_ids)

        self.assertEqual(response.status_code, 201)
        body = response.get_json()
        self.assertEqual(set(body.keys()), {"id", "submitted_at", "questions"})
        self.assertNotIn("vocabs", body)
        self.assertNotIn("vocabulary_ids", body)
        self.assertNotIn("id", body["questions"][0]["vocab"])
        self.assertNotIn("definition", body["questions"][0]["vocab"])
        self.assertNotIn("vocabulary_id", body["questions"][0]["options"][0])

    def test_training_option_shuffle_allows_correct_answer_in_every_position(self):
        repository = TrainingRepository()
        vocabulary_ids = [1, 2, 3, 4, 5]
        correct_vocabulary_id = 3

        observed_positions = []
        for position in range(len(vocabulary_ids)):
            randomizer = PositioningRandomizer(correct_vocabulary_id, position)
            with patch(
                "Repositories.training_repository.secrets.SystemRandom",
                return_value=randomizer,
            ):
                option_ids = repository._select_option_vocabulary_ids(
                    vocabulary_ids,
                    correct_vocabulary_id,
                )
            observed_positions.append(option_ids.index(correct_vocabulary_id))

        self.assertEqual(observed_positions, [0, 1, 2, 3, 4])

    def test_training_submit_scores_all_correct_answers(self):
        self.login_user()
        vocabulary_ids = self.create_sample_vocabs()[:2]
        training_response = self.create_training(vocabulary_ids)
        training = training_response.get_json()
        answers = self.correct_answers_from_quiz(training)

        response = self.submit_training(training["id"], answers)

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["score"], 2)
        self.assertEqual(body["total"], 2)
        self.assertEqual(body["incorrect_vocabs"], [])

    def test_training_submit_persists_result(self):
        self.login_user()
        vocabulary_ids = self.create_sample_vocabs()[:2]
        training_response = self.create_training(vocabulary_ids)
        training = training_response.get_json()
        definitions_by_word = self.definitions_by_word()
        first_definition = definitions_by_word[self.sample_words()[0]]
        answers = {
            training["questions"][0]["token"]: next(
                option["token"]
                for option in training["questions"][0]["options"]
                if option["definition"] == first_definition
            ),
            training["questions"][1]["token"]: next(
                option["token"]
                for option in training["questions"][1]["options"]
                if option["definition"] == first_definition
            ),
        }

        self.submit_training(training["id"], answers)

        with self.app.app_context():
            rows = db.query(
                """
                SELECT score, total
                FROM training_sessions
                WHERE id = ?
                """,
                [training["id"]],
            )
            incorrect_rows = db.query(
                """
                SELECT vocabulary_id
                FROM training_incorrect_answers
                WHERE training_session_id = ?
                """,
                [training["id"]],
            )

        self.assertEqual(rows[0]["score"], 1)
        self.assertEqual(rows[0]["total"], 2)
        self.assertEqual(len(incorrect_rows), 1)

    def test_training_submit_returns_incorrect_vocab_list(self):
        self.login_user()
        vocabulary_ids = self.create_sample_vocabs()[:2]
        training_response = self.create_training(vocabulary_ids)
        training = training_response.get_json()
        definitions = self.definitions_by_id(vocabulary_ids)
        second_vocab_id = str(vocabulary_ids[1])
        definitions_by_word = self.definitions_by_word()
        first_definition = definitions_by_word[self.sample_words()[0]]
        answers = {
            training["questions"][0]["token"]: next(
                option["token"]
                for option in training["questions"][0]["options"]
                if option["definition"] == first_definition
            ),
            training["questions"][1]["token"]: next(
                option["token"]
                for option in training["questions"][1]["options"]
                if option["definition"] == first_definition
            ),
        }

        response = self.submit_training(training["id"], answers)

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["score"], 1)
        self.assertEqual(body["total"], 2)
        self.assertEqual(len(body["incorrect_vocabs"]), 1)
        self.assertEqual(body["incorrect_vocabs"][0]["word"], self.sample_words()[1])
        self.assertEqual(
            body["incorrect_vocabs"][0]["correct_definition"],
            definitions[second_vocab_id],
        )

    def test_training_submit_rejects_missing_answers(self):
        self.login_user()
        vocabulary_ids = self.create_sample_vocabs()[:1]
        training_response = self.create_training(vocabulary_ids)
        training = training_response.get_json()

        response = self.submit_training(training["id"], {})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "Invalid answers")

    def test_training_submit_rejects_malformed_answers(self):
        self.login_user()
        vocabulary_ids = self.create_sample_vocabs()[:1]
        training_response = self.create_training(vocabulary_ids)
        training = training_response.get_json()

        response = self.client.post(
            f"/training/{training['id']}/submit",
            json={"answers": ["not-a-dict"]},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "Invalid answers")

    def test_training_submit_rejects_nested_answer_values(self):
        self.login_user()
        vocabulary_ids = self.create_sample_vocabs()[:1]
        training_response = self.create_training(vocabulary_ids)
        training = training_response.get_json()

        response = self.client.post(
            f"/training/{training['id']}/submit",
            json={"answers": {training["questions"][0]["token"]: ["not-a-string"]}},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "Invalid answers")

    def test_training_submit_rejects_answer_not_in_training_options(self):
        self.login_user()
        vocabulary_ids = self.create_sample_vocabs()[:1]
        training_response = self.create_training(vocabulary_ids)
        training = training_response.get_json()

        response = self.submit_training(training["id"], {training["questions"][0]["token"]: "999"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "Invalid answers")

    def test_training_submit_rejects_bool_and_float_answer_values(self):
        self.login_user()
        vocabulary_ids = self.create_sample_vocabs()[:1]
        training_response = self.create_training(vocabulary_ids)
        training = training_response.get_json()

        bool_response = self.submit_training(
            training["id"],
            {training["questions"][0]["token"]: True},
        )
        float_response = self.submit_training(
            training["id"],
            {training["questions"][0]["token"]: 1.9},
        )

        self.assertEqual(bool_response.status_code, 400)
        self.assertEqual(bool_response.get_json()["error"], "Invalid answers")
        self.assertEqual(float_response.status_code, 400)
        self.assertEqual(float_response.get_json()["error"], "Invalid answers")

    def test_training_submit_rejects_malformed_json(self):
        self.login_user()
        vocabulary_ids = self.create_sample_vocabs()[:1]
        training_response = self.create_training(vocabulary_ids)
        training = training_response.get_json()

        response = self.client.post(
            f"/training/{training['id']}/submit",
            json=["not-a-dict"],
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "Invalid request")

    def test_training_submit_cannot_be_repeated(self):
        self.login_user()
        vocabulary_ids = self.create_sample_vocabs()[:1]
        training_response = self.create_training(vocabulary_ids)
        training = training_response.get_json()
        answers = self.correct_answers_from_quiz(training)

        first_response = self.submit_training(training["id"], answers)
        second_response = self.submit_training(training["id"], answers)

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 400)
        self.assertEqual(
            second_response.get_json()["error"],
            "Training session has already been submitted",
        )

    def test_training_page_shows_result_after_submission(self):
        self.login_user()
        vocabulary_ids = self.create_sample_vocabs()[:1]
        training_response = self.create_training(vocabulary_ids)
        training = training_response.get_json()
        answers = self.correct_answers_from_quiz(training)
        self.submit_training(training["id"], answers)

        response = self.client.get(f"/training/{training['id']}")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Training result", response.data)

    def test_training_submit_requires_session_owner(self):
        self.login_user()
        vocabulary_ids = self.create_sample_vocabs()[:1]
        training_response = self.create_training(vocabulary_ids)
        training = training_response.get_json()
        self.logout_user()
        self.login_second_user()

        response = self.submit_training(training["id"], {})

        self.assertEqual(response.status_code, 404)

    def test_training_can_include_global_vocab_created_by_another_user(self):
        self.login_user()
        vocabulary_ids = self.create_sample_vocabs()
        self.logout_user()
        self.login_second_user()

        response = self.create_training([vocabulary_ids[0]])

        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(response.get_json()["questions"]), 1)

    def test_training_selection_rejects_duplicate_definitions(self):
        self.login_user()
        first = self.valid_entry("duplicateone")
        second = self.valid_entry("duplicatetwo")
        first["definition"] = "Shared definition"
        second["definition"] = "Shared definition"
        first_id = self.client.post("/vocabulary", json=first).get_json()["id"]
        second_id = self.client.post("/vocabulary", json=second).get_json()["id"]

        response = self.create_training([first_id, second_id])

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.get_json()["error"],
            "Training selection contains duplicate definitions",
        )

    def test_training_result_save_is_atomic(self):
        self.login_user()
        vocabulary_ids = self.create_sample_vocabs()[:2]
        training_response = self.create_training(vocabulary_ids)
        training = training_response.get_json()
        answers = self.correct_answers_from_quiz(training)
        self.submit_training(training["id"], answers)

        with self.app.app_context():
            saved = db.query(
                "SELECT score, total FROM training_sessions WHERE id = ?",
                [training["id"]],
            )[0]
            from Repositories.training_repository import training_repository

            result = training_repository.save_training_result(
                training["id"],
                0,
                2,
                [],
            )
            current = db.query(
                "SELECT score, total FROM training_sessions WHERE id = ?",
                [training["id"]],
            )[0]

        self.assertFalse(result)
        self.assertEqual(current["score"], saved["score"])
        self.assertEqual(current["total"], saved["total"])

    def test_training_quiz_uses_snapshot_after_vocab_edit(self):
        self.login_user()
        vocabulary_ids = self.create_sample_vocabs()[:2]
        training_response = self.create_training(vocabulary_ids)
        training = training_response.get_json()
        original_first_definition = self.definitions_by_word()[self.sample_words()[0]]
        updated_entry = self.valid_entry(self.sample_words()[0])
        updated_entry["definition"] = "Changed after training creation"

        self.client.put(f"/vocabulary/{vocabulary_ids[0]}", json=updated_entry)
        refreshed_training = self.client.get(f"/training/{training['id']}")

        self.assertEqual(refreshed_training.status_code, 200)
        self.assertIn(original_first_definition.encode(), refreshed_training.data)
        self.assertNotIn(b"Changed after training creation", refreshed_training.data)

    def test_training_result_uses_snapshot_after_vocab_edit(self):
        self.login_user()
        vocabulary_ids = self.create_sample_vocabs()[:2]
        training_response = self.create_training(vocabulary_ids)
        training = training_response.get_json()
        definitions_by_word = self.definitions_by_word()
        first_definition = definitions_by_word[self.sample_words()[0]]
        answers = {
            training["questions"][0]["token"]: next(
                option["token"]
                for option in training["questions"][0]["options"]
                if option["definition"] == first_definition
            ),
            training["questions"][1]["token"]: next(
                option["token"]
                for option in training["questions"][1]["options"]
                if option["definition"] == first_definition
            ),
        }

        self.submit_training(training["id"], answers)
        updated_entry = self.valid_entry("changedword")
        updated_entry["definition"] = "Changed after training result"
        self.client.put(f"/vocabulary/{vocabulary_ids[1]}", json=updated_entry)
        result_page = self.client.get(f"/training/{training['id']}")

        self.assertEqual(result_page.status_code, 200)
        self.assertIn(self.sample_words()[1].encode(), result_page.data)
        self.assertIn(self.valid_entry(self.sample_words()[1])["definition"].encode(), result_page.data)
        self.assertNotIn(b"changedword", result_page.data)
        self.assertNotIn(b"Changed after training result", result_page.data)

    def test_sqlite_foreign_keys_are_enforced(self):
        with self.app.app_context():
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute(
                    """
                    INSERT INTO training_items
                        (
                            training_session_id,
                            vocabulary_id,
                            question_token,
                            item_order
                        )
                    VALUES (?, ?, ?, ?)
                    """,
                    [999, 999, "foreign-key-test-token", 1],
                )


if __name__ == "__main__":
    unittest.main()
