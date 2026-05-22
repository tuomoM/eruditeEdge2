import db


class TrainingRepository:
    def create_training_session(self, user_id, vocabulary_ids):
        cursor = db.execute(
            "INSERT INTO training_sessions (user_id) VALUES (?)",
            [user_id],
        )
        training_session_id = cursor.lastrowid

        for index, vocabulary_id in enumerate(vocabulary_ids, start=1):
            db.execute(
                """
                INSERT INTO training_items
                    (training_session_id, vocabulary_id, item_order)
                VALUES (?, ?, ?)
                """,
                [training_session_id, vocabulary_id, index],
            )

        return training_session_id

    def get_training_session(self, training_session_id, user_id):
        rows = db.query(
            """
            SELECT id, user_id, created_at
            FROM training_sessions
            WHERE id = ? AND user_id = ?
            """,
            [training_session_id, user_id],
        )
        if not rows:
            return None

        session = dict(rows[0])
        session["vocabulary_ids"] = [
            row["vocabulary_id"]
            for row in db.query(
                """
                SELECT vocabulary_id
                FROM training_items
                WHERE training_session_id = ?
                ORDER BY item_order
                """,
                [training_session_id],
            )
        ]
        return session


training_repository = TrainingRepository()
