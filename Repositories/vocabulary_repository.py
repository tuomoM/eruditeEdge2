from sqlite3 import IntegrityError, OperationalError

import db


class VocabularyRepository:
    def create_entry(
        self,
        word,
        definition,
        context,
        part_of_speech,
        domains,
        synonyms,
        examples,
        cloze_sentences,
        needs_attention,
        confidence_score,
        user_id,
    ):
        try:
            cursor = db.execute(
                """
                INSERT INTO vocabulary_entries
                    (
                        word,
                        definition,
                        context,
                        part_of_speech,
                        needs_attention,
                        confidence_score,
                        confidence_obsolete,
                        created_by
                    )
                VALUES (?, ?, ?, ?, ?, ?, 0, ?)
                """,
                [
                    word,
                    definition,
                    context,
                    part_of_speech,
                    needs_attention,
                    confidence_score,
                    user_id,
                ],
            )
        except IntegrityError:
            return None

        vocabulary_id = cursor.lastrowid
        self._save_synonyms(vocabulary_id, synonyms)
        self._save_examples(vocabulary_id, examples)
        self._save_cloze_sentences(vocabulary_id, cloze_sentences)
        self._save_domains(vocabulary_id, domains)
        return vocabulary_id

    def update_entry(
        self,
        vocabulary_id,
        word,
        definition,
        context,
        part_of_speech,
        domains,
        synonyms,
        examples,
        cloze_sentences,
    ):
        try:
            cursor = db.execute(
                """
                UPDATE vocabulary_entries
                SET
                    word = ?,
                    definition = ?,
                    context = ?,
                    part_of_speech = ?,
                    confidence_obsolete = CASE
                        WHEN confidence_score IS NULL THEN 0
                        ELSE 1
                    END,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                [word, definition, context, part_of_speech, vocabulary_id],
            )
        except IntegrityError:
            return False

        if cursor.rowcount == 0:
            return False

        db.execute("DELETE FROM vocabulary_synonyms WHERE vocabulary_id = ?", [vocabulary_id])
        db.execute("DELETE FROM vocabulary_examples WHERE vocabulary_id = ?", [vocabulary_id])
        db.execute("DELETE FROM vocabulary_cloze_sentences WHERE vocabulary_id = ?", [vocabulary_id])
        db.execute("DELETE FROM vocabulary_domains WHERE vocabulary_id = ?", [vocabulary_id])
        self._save_synonyms(vocabulary_id, synonyms)
        self._save_examples(vocabulary_id, examples)
        self._save_cloze_sentences(vocabulary_id, cloze_sentences)
        self._save_domains(vocabulary_id, domains)
        return True

    def update_cloze_data(self, vocabulary_id, part_of_speech, cloze_sentences, domains):
        cursor = db.execute(
            """
            UPDATE vocabulary_entries
            SET
                part_of_speech = ?,
                confidence_obsolete = CASE
                    WHEN confidence_score IS NULL THEN 0
                    ELSE 1
                END,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            [part_of_speech, vocabulary_id],
        )
        if cursor.rowcount == 0:
            return False

        db.execute("DELETE FROM vocabulary_cloze_sentences WHERE vocabulary_id = ?", [vocabulary_id])
        db.execute("DELETE FROM vocabulary_domains WHERE vocabulary_id = ?", [vocabulary_id])
        self._save_cloze_sentences(vocabulary_id, cloze_sentences)
        self._save_domains(vocabulary_id, domains)
        return True

    def update_ai_maintenance_data(
        self,
        vocabulary_id,
        part_of_speech,
        cloze_sentences,
        domains,
        needs_attention,
        confidence_score,
    ):
        cursor = db.execute(
            """
            UPDATE vocabulary_entries
            SET
                part_of_speech = ?,
                needs_attention = ?,
                confidence_score = ?,
                confidence_obsolete = 0,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            [
                part_of_speech,
                needs_attention,
                confidence_score,
                vocabulary_id,
            ],
        )
        if cursor.rowcount == 0:
            return False

        db.execute("DELETE FROM vocabulary_cloze_sentences WHERE vocabulary_id = ?", [vocabulary_id])
        db.execute("DELETE FROM vocabulary_domains WHERE vocabulary_id = ?", [vocabulary_id])
        self._save_cloze_sentences(vocabulary_id, cloze_sentences)
        self._save_domains(vocabulary_id, domains)
        return True

    def get_entry(self, vocabulary_id):
        rows = db.query(
            """
            SELECT
                id,
                word,
                definition,
                context,
                part_of_speech,
                needs_attention,
                confidence_score,
                confidence_obsolete,
                created_by,
                created_at,
                updated_at
            FROM vocabulary_entries
            WHERE id = ?
            """,
            [vocabulary_id],
        )
        if not rows:
            return None

        entry = dict(rows[0])
        synonym_rows = self._entry_synonym_rows(vocabulary_id)
        entry["synonyms"] = [row["synonym"] for row in synonym_rows]
        entry["linked_synonyms"] = [
            {
                "id": row["id"],
                "synonym": row["synonym"],
                "linked_vocabulary_id": row["linked_vocabulary_id"],
                "linked_word": row["linked_word"],
            }
            for row in synonym_rows
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
        entry["cloze_sentences"] = [
            row["sentence"]
            for row in db.query(
                """
                SELECT sentence
                FROM vocabulary_cloze_sentences
                WHERE vocabulary_id = ?
                ORDER BY cloze_order
                """,
                [vocabulary_id],
            )
        ]
        entry["domains"] = [
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
        return entry

    def _entry_synonym_rows(self, vocabulary_id):
        try:
            return db.query(
                """
                SELECT
                    vocabulary_synonyms.id,
                    vocabulary_synonyms.synonym,
                    vocabulary_synonyms.linked_vocabulary_id,
                    linked_entries.word AS linked_word
                FROM vocabulary_synonyms
                LEFT JOIN vocabulary_entries AS linked_entries
                    ON linked_entries.id = vocabulary_synonyms.linked_vocabulary_id
                WHERE vocabulary_synonyms.vocabulary_id = ?
                ORDER BY vocabulary_synonyms.synonym
                """,
                [vocabulary_id],
            )
        except OperationalError as error:
            if "no such column: vocabulary_synonyms.linked_vocabulary_id" not in str(error):
                raise
            rows = db.query(
                """
                SELECT id, synonym
                FROM vocabulary_synonyms
                WHERE vocabulary_id = ?
                ORDER BY synonym
                """,
                [vocabulary_id],
            )
            return [
                {
                    "id": row["id"],
                    "synonym": row["synonym"],
                    "linked_vocabulary_id": None,
                    "linked_word": None,
                }
                for row in rows
            ]

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

    def count_created_since(self, created_since):
        result = db.query(
            """
            SELECT COUNT(*) AS count
            FROM vocabulary_entries
            WHERE created_at >= ?
            """,
            [created_since],
        )
        return result[0]["count"]

    def list_synonym_rows(self, vocabulary_id):
        rows = db.query(
            """
            SELECT id, vocabulary_id, synonym, linked_vocabulary_id
            FROM vocabulary_synonyms
            WHERE vocabulary_id = ?
            ORDER BY id
            """,
            [vocabulary_id],
        )
        return [dict(row) for row in rows]

    def find_entries_by_word(self, word, exclude_vocabulary_id=None):
        params = [word]
        exclude_clause = ""
        if exclude_vocabulary_id is not None:
            exclude_clause = "AND id != ?"
            params.append(exclude_vocabulary_id)
        rows = db.query(
            f"""
            SELECT id, word, context
            FROM vocabulary_entries
            WHERE word = ? COLLATE NOCASE
                {exclude_clause}
            ORDER BY id
            """,
            params,
        )
        return [dict(row) for row in rows]

    def find_synonym_rows_by_text(self, synonym, exclude_vocabulary_id=None):
        params = [synonym]
        exclude_clause = ""
        if exclude_vocabulary_id is not None:
            exclude_clause = "AND vocabulary_id != ?"
            params.append(exclude_vocabulary_id)
        rows = db.query(
            f"""
            SELECT id, vocabulary_id, synonym, linked_vocabulary_id
            FROM vocabulary_synonyms
            WHERE synonym = ? COLLATE NOCASE
                {exclude_clause}
            ORDER BY id
            """,
            params,
        )
        return [dict(row) for row in rows]

    def link_synonym(self, synonym_id, linked_vocabulary_id):
        db.execute(
            """
            UPDATE vocabulary_synonyms
            SET linked_vocabulary_id = ?
            WHERE id = ?
            """,
            [linked_vocabulary_id, synonym_id],
        )

    def ensure_synonym(self, vocabulary_id, synonym, linked_vocabulary_id=None):
        existing_rows = db.query(
            """
            SELECT id
            FROM vocabulary_synonyms
            WHERE vocabulary_id = ?
                AND synonym = ? COLLATE NOCASE
            ORDER BY id
            LIMIT 1
            """,
            [vocabulary_id, synonym],
        )
        if existing_rows:
            self.link_synonym(existing_rows[0]["id"], linked_vocabulary_id)
            return existing_rows[0]["id"]

        cursor = db.execute(
            """
            INSERT INTO vocabulary_synonyms
                (vocabulary_id, synonym, linked_vocabulary_id)
            VALUES (?, ?, ?)
            """,
            [vocabulary_id, synonym, linked_vocabulary_id],
        )
        return cursor.lastrowid

    def list_cloze_maintenance_entries(self):
        rows = db.query(
            """
            SELECT id
            FROM vocabulary_entries
            ORDER BY word, context
            """
        )
        entries = [self.get_entry(row["id"]) for row in rows]
        return [
            entry
            for entry in entries
            if entry["part_of_speech"] == "other" or len(entry["cloze_sentences"]) < 2
        ]

    def delete_entries_by_user(self, user_id):
        connection = db.get_connection()
        try:
            connection.execute(
                """
                DELETE FROM training_sessions
                WHERE id IN (
                    SELECT training_items.training_session_id
                    FROM training_items
                    JOIN vocabulary_entries
                        ON vocabulary_entries.id = training_items.vocabulary_id
                    WHERE vocabulary_entries.created_by = ?

                    UNION

                    SELECT training_answer_options.training_session_id
                    FROM training_answer_options
                    JOIN vocabulary_entries
                        ON vocabulary_entries.id = training_answer_options.option_vocabulary_id
                    WHERE vocabulary_entries.created_by = ?

                    UNION

                    SELECT training_incorrect_answers.training_session_id
                    FROM training_incorrect_answers
                    JOIN vocabulary_entries
                        ON vocabulary_entries.id = training_incorrect_answers.vocabulary_id
                    WHERE vocabulary_entries.created_by = ?
                )
                """,
                [user_id, user_id, user_id],
            )
            connection.execute(
                """
                DELETE FROM vocabulary_cloze_sentences
                WHERE vocabulary_id IN (
                    SELECT id
                    FROM vocabulary_entries
                    WHERE created_by = ?
                )
                """,
                [user_id],
            )
            connection.execute(
                """
                DELETE FROM vocabulary_domains
                WHERE vocabulary_id IN (
                    SELECT id
                    FROM vocabulary_entries
                    WHERE created_by = ?
                )
                """,
                [user_id],
            )
            cursor = connection.execute(
                "DELETE FROM vocabulary_entries WHERE created_by = ?",
                [user_id],
            )
            connection.commit()
            return cursor.rowcount
        except Exception:
            connection.rollback()
            raise

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

    def _save_cloze_sentences(self, vocabulary_id, cloze_sentences):
        for index, sentence in enumerate(cloze_sentences, start=1):
            db.execute(
                """
                INSERT INTO vocabulary_cloze_sentences
                    (vocabulary_id, sentence, cloze_order)
                VALUES (?, ?, ?)
                """,
                [vocabulary_id, sentence, index],
            )

    def _save_domains(self, vocabulary_id, domains):
        for index, domain in enumerate(domains, start=1):
            db.execute(
                """
                INSERT INTO vocabulary_domains
                    (vocabulary_id, domain, domain_order)
                VALUES (?, ?, ?)
                """,
                [vocabulary_id, domain, index],
            )


vocabulary_repository = VocabularyRepository()
