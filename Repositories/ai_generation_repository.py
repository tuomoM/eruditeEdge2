from datetime import date
import db


class AiGenerationRepository:
    def generation_count(self, user_id, generation_date=None):
        generation_date = generation_date or date.today().isoformat()
        rows = db.query(
            """
            SELECT generation_count
            FROM ai_generation_usage
            WHERE user_id = ? AND generation_date = ?
            """,
            [user_id, generation_date],
        )
        if not rows:
            return 0
        return rows[0]["generation_count"]

    def generation_counts(self, generation_date=None):
        generation_date = generation_date or date.today().isoformat()
        rows = db.query(
            """
            SELECT user_id, generation_count
            FROM ai_generation_usage
            WHERE generation_date = ?
            """,
            [generation_date],
        )
        return {
            row["user_id"]: row["generation_count"]
            for row in rows
        }

    def reset_generation_count(self, user_id, generation_date=None):
        generation_date = generation_date or date.today().isoformat()
        cursor = db.execute(
            """
            DELETE FROM ai_generation_usage
            WHERE user_id = ? AND generation_date = ?
            """,
            [user_id, generation_date],
        )
        return cursor.rowcount

    def refund_generation(self, user_id, generation_date=None):
        generation_date = generation_date or date.today().isoformat()
        cursor = db.execute(
            """
            UPDATE ai_generation_usage
            SET generation_count = generation_count - 1
            WHERE user_id = ?
                AND generation_date = ?
                AND generation_count > 0
            """,
            [user_id, generation_date],
        )
        return cursor.rowcount > 0

    def try_record_generation(self, user_id, quota, generation_date=None):
        generation_date = generation_date or date.today().isoformat()
        connection = db.get_connection()
        try:
            connection.execute(
                """
                INSERT OR IGNORE INTO ai_generation_usage
                    (user_id, generation_date, generation_count)
                VALUES (?, ?, 0)
                """,
                [user_id, generation_date],
            )
            cursor = connection.execute(
                """
                UPDATE ai_generation_usage
                SET generation_count = generation_count + 1
                WHERE user_id = ?
                    AND generation_date = ?
                    AND generation_count < ?
                """,
                [user_id, generation_date, quota],
            )
            connection.commit()
            return cursor.rowcount > 0
        except Exception:
            connection.rollback()
            raise


ai_generation_repository = AiGenerationRepository()
