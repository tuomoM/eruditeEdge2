import secrets

import db


MAX_OPTIONS_PER_QUESTION = 5


class TrainingRepository:
    def create_training_session(self, user_id, vocabs):
        connection = db.get_connection()
        try:
            cursor = connection.execute(
                "INSERT INTO training_sessions (user_id) VALUES (?)",
                [user_id],
            )
            training_session_id = cursor.lastrowid
            vocabs_by_id = {vocab["id"]: vocab for vocab in vocabs}
            vocabulary_ids = [vocab["id"] for vocab in vocabs]

            for index, vocab in enumerate(vocabs, start=1):
                vocabulary_id = vocab["id"]
                question_token = secrets.token_urlsafe(24)
                connection.execute(
                    """
                    INSERT INTO training_items
                        (
                            training_session_id,
                            vocabulary_id,
                            question_token,
                            word,
                            context,
                            definition,
                            item_order
                        )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        training_session_id,
                        vocabulary_id,
                        question_token,
                        vocab["word"],
                        vocab["context"],
                        vocab["definition"],
                        index,
                    ],
                )
                option_vocabulary_ids = self._select_option_vocabulary_ids(
                    vocabulary_ids,
                    vocabulary_id,
                )
                for option_order, option_vocabulary_id in enumerate(option_vocabulary_ids, start=1):
                    option_vocab = vocabs_by_id[option_vocabulary_id]
                    connection.execute(
                        """
                        INSERT INTO training_answer_options
                            (
                                training_session_id,
                                question_token,
                                option_token,
                                option_vocabulary_id,
                                option_definition,
                                option_order
                            )
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        [
                            training_session_id,
                            question_token,
                            secrets.token_urlsafe(24),
                            option_vocabulary_id,
                            option_vocab["definition"],
                            option_order,
                        ],
                    )
            connection.commit()
            return training_session_id
        except Exception:
            connection.rollback()
            raise

    def get_training_session(self, training_session_id, user_id):
        rows = db.query(
            """
            SELECT id, user_id, created_at, submitted_at, score, total
            FROM training_sessions
            WHERE id = ? AND user_id = ?
            """,
            [training_session_id, user_id],
        )
        if not rows:
            return None

        session = dict(rows[0])
        session["items"] = [
            {
                "vocabulary_id": row["vocabulary_id"],
                "question_token": row["question_token"],
                "word": row["word"],
                "context": row["context"],
                "definition": row["definition"],
            }
            for row in db.query(
                """
                SELECT vocabulary_id, question_token, word, context, definition
                FROM training_items
                WHERE training_session_id = ?
                ORDER BY item_order
                """,
                [training_session_id],
            )
        ]
        session["vocabulary_ids"] = [
            item["vocabulary_id"]
            for item in session["items"]
        ]
        session["answer_options"] = [
            dict(row)
            for row in db.query(
                """
                SELECT
                    question_token,
                    option_token,
                    option_vocabulary_id,
                    option_definition
                FROM training_answer_options
                WHERE training_session_id = ?
                ORDER BY question_token, option_order
                """,
                [training_session_id],
            )
        ]
        return session

    def save_training_result(self, training_session_id, score, total, incorrect_vocabs):
        connection = db.get_connection()
        try:
            cursor = connection.execute(
                """
                UPDATE training_sessions
                SET submitted_at = CURRENT_TIMESTAMP, score = ?, total = ?
                WHERE id = ? AND submitted_at IS NULL
                """,
                [score, total, training_session_id],
            )
            if cursor.rowcount == 0:
                connection.rollback()
                return False

            connection.execute(
                "DELETE FROM training_incorrect_answers WHERE training_session_id = ?",
                [training_session_id],
            )
            for vocab in incorrect_vocabs:
                connection.execute(
                    """
                    INSERT INTO training_incorrect_answers
                        (
                            training_session_id,
                            vocabulary_id,
                            word,
                            correct_definition,
                            selected_definition
                        )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    [
                        training_session_id,
                        vocab["id"],
                        vocab["word"],
                        vocab["correct_definition"],
                        vocab["selected_definition"],
                    ],
                )
            connection.commit()
            return True
        except Exception:
            connection.rollback()
            raise

    def get_training_result(self, training_session_id, user_id):
        rows = db.query(
            """
            SELECT id, score, total
            FROM training_sessions
            WHERE id = ? AND user_id = ? AND submitted_at IS NOT NULL
            """,
            [training_session_id, user_id],
        )
        if not rows:
            return None

        result = {
            "training_session_id": rows[0]["id"],
            "score": rows[0]["score"],
            "total": rows[0]["total"],
            "incorrect_vocabs": [],
        }
        result["incorrect_vocabs"] = [
            dict(row)
            for row in db.query(
                """
                SELECT
                    vocabulary_id AS id,
                    word,
                    correct_definition,
                    selected_definition
                FROM training_incorrect_answers
                WHERE training_session_id = ?
                ORDER BY training_incorrect_answers.id
                """,
                [training_session_id],
            )
        ]
        return result

    def _select_option_vocabulary_ids(self, vocabulary_ids, question_vocabulary_id):
        if len(vocabulary_ids) <= MAX_OPTIONS_PER_QUESTION:
            option_vocabulary_ids = vocabulary_ids[:]
        else:
            randomizer = secrets.SystemRandom()
            distractor_ids = [
                vocabulary_id
                for vocabulary_id in vocabulary_ids
                if vocabulary_id != question_vocabulary_id
            ]
            option_vocabulary_ids = [
                question_vocabulary_id,
                *randomizer.sample(distractor_ids, MAX_OPTIONS_PER_QUESTION - 1),
            ]

        self._shuffle_options(option_vocabulary_ids)
        return option_vocabulary_ids

    def _shuffle_options(self, option_vocabulary_ids):
        if len(option_vocabulary_ids) <= 1:
            return

        secrets.SystemRandom().shuffle(option_vocabulary_ids)


training_repository = TrainingRepository()
