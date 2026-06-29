import json
import sqlite3

import db


class BackgroundJobRepository:
    def enqueue(self, job_type, payload):
        try:
            cursor = db.execute(
                """
                INSERT INTO background_jobs (job_type, payload)
                VALUES (?, ?)
                """,
                [job_type, json.dumps(payload, sort_keys=True)],
            )
            return cursor.lastrowid
        except sqlite3.OperationalError as error:
            if "no such table: background_jobs" in str(error):
                return None
            raise

    def list_pending(self, limit=10):
        rows = db.query(
            """
            SELECT id, job_type, status, payload, attempts, last_error, created_at, updated_at
            FROM background_jobs
            WHERE status = 'pending'
            ORDER BY created_at, id
            LIMIT ?
            """,
            [limit],
        )
        return [self._to_job(row) for row in rows]

    def mark_running(self, job_id):
        cursor = db.execute(
            """
            UPDATE background_jobs
            SET status = 'running',
                attempts = attempts + 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND status = 'pending'
            """,
            [job_id],
        )
        return cursor.rowcount > 0

    def delete(self, job_id):
        db.execute("DELETE FROM background_jobs WHERE id = ?", [job_id])

    def mark_failed(self, job_id, error):
        db.execute(
            """
            UPDATE background_jobs
            SET status = 'failed',
                last_error = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            [str(error), job_id],
        )

    def count_by_status(self):
        rows = db.query(
            """
            SELECT status, COUNT(*) AS count
            FROM background_jobs
            GROUP BY status
            """
        )
        return {row["status"]: row["count"] for row in rows}

    def _to_job(self, row):
        job = dict(row)
        job["payload"] = json.loads(job["payload"])
        return job


background_job_repository = BackgroundJobRepository()
