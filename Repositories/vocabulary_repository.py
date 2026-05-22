from sqlite3 import IntegrityError

import db


class VocabularyRepository:
    def create_entry(self, word, definition, context, synonyms, examples, user_id):
        try:
            cursor = db.execute(
                """
                INSERT INTO vocabulary_entries (word, definition, context, created_by)
                VALUES (?, ?, ?, ?)
                """,
                [word, definition, context, user_id],
            )
        except IntegrityError:
            return None

        vocabulary_id = cursor.lastrowid
        self._save_synonyms(vocabulary_id, synonyms)
        self._save_examples(vocabulary_id, examples)
        return vocabulary_id

    def update_entry(self, vocabulary_id, word, definition, context, synonyms, examples):
        try:
            cursor = db.execute(
                """
                UPDATE vocabulary_entries
                SET word = ?, definition = ?, context = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                [word, definition, context, vocabulary_id],
            )
        except IntegrityError:
            return False

        if cursor.rowcount == 0:
            return False

        db.execute("DELETE FROM vocabulary_synonyms WHERE vocabulary_id = ?", [vocabulary_id])
        db.execute("DELETE FROM vocabulary_examples WHERE vocabulary_id = ?", [vocabulary_id])
        self._save_synonyms(vocabulary_id, synonyms)
        self._save_examples(vocabulary_id, examples)
        return True

    def get_entry(self, vocabulary_id):
        rows = db.query(
            """
            SELECT id, word, definition, context, created_by, created_at, updated_at
            FROM vocabulary_entries
            WHERE id = ?
            """,
            [vocabulary_id],
        )
        if not rows:
            return None

        entry = dict(rows[0])
        entry["synonyms"] = [
            row["synonym"]
            for row in db.query(
                """
                SELECT synonym
                FROM vocabulary_synonyms
                WHERE vocabulary_id = ?
                ORDER BY synonym
                """,
                [vocabulary_id],
            )
        ]
        entry["examples"] = [
            row["example_sentence"]
            for row in db.query(
                """
                SELECT example_sentence
                FROM vocabulary_examples
                WHERE vocabulary_id = ?
                ORDER BY example_order
                """,
                [vocabulary_id],
            )
        ]
        return entry

    def search_by_word(self, search_term):
        rows = db.query(
            """
            SELECT id
            FROM vocabulary_entries
            WHERE word LIKE ? COLLATE NOCASE
            ORDER BY word, context
            """,
            [search_term],
        )
        return [self.get_entry(row["id"]) for row in rows]

    def list_entries(self):
        rows = db.query(
            """
            SELECT id
            FROM vocabulary_entries
            ORDER BY word, context
            """
        )
        return [self.get_entry(row["id"]) for row in rows]

    def _save_synonyms(self, vocabulary_id, synonyms):
        for synonym in synonyms:
            db.execute(
                """
                INSERT INTO vocabulary_synonyms (vocabulary_id, synonym)
                VALUES (?, ?)
                """,
                [vocabulary_id, synonym],
            )

    def _save_examples(self, vocabulary_id, examples):
        for index, example in enumerate(examples, start=1):
            db.execute(
                """
                INSERT INTO vocabulary_examples
                    (vocabulary_id, example_sentence, example_order)
                VALUES (?, ?, ?)
                """,
                [vocabulary_id, example, index],
            )


vocabulary_repository = VocabularyRepository()
