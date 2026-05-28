import db


ACCESS_REQUEST_DUPLICATE_EMAIL = "duplicate_email"
ACCESS_REQUEST_IP_LIMIT_EXCEEDED = "ip_limit_exceeded"


class AccessRequestRepository:
    def create_access_request_with_guardrails(
        self,
        name,
        email,
        message,
        ip_address,
        queue_limit,
        daily_ip_limit,
    ):
        connection = db.get_connection()
        connection.execute("BEGIN IMMEDIATE")
        try:
            if self._email_exists(connection, email):
                connection.rollback()
                return None, ACCESS_REQUEST_DUPLICATE_EMAIL

            if self._ip_request_count_today(connection, ip_address) >= daily_ip_limit:
                connection.rollback()
                return None, ACCESS_REQUEST_IP_LIMIT_EXCEEDED

            self._delete_oldest_for_queue_limit(connection, queue_limit)
            cursor = connection.execute(
                """
                INSERT INTO access_requests (name, email, message, ip_address)
                VALUES (?, ?, ?, ?)
                """,
                [name, email, message, ip_address],
            )
            connection.commit()
            return cursor.lastrowid, None
        except Exception:
            connection.rollback()
            raise

    def get_access_request(self, access_request_id):
        rows = db.query(
            """
            SELECT id, name, email, message, ip_address, created_at
            FROM access_requests
            WHERE id = ?
            """,
            [access_request_id],
        )
        if not rows:
            return None
        return dict(rows[0])

    def list_access_requests(self):
        return [
            dict(row)
            for row in db.query(
                """
                SELECT id, name, email, message, ip_address, created_at
                FROM access_requests
                ORDER BY created_at DESC, id DESC
                """
            )
        ]

    def delete_access_request(self, access_request_id):
        cursor = db.execute(
            """
            DELETE FROM access_requests
            WHERE id = ?
            """,
            [access_request_id],
        )
        return cursor.rowcount > 0

    def _email_exists(self, connection, email):
        rows = connection.execute(
            """
            SELECT id
            FROM access_requests
            WHERE email = ?
            LIMIT 1
            """,
            [email],
        ).fetchall()
        return bool(rows)

    def _ip_request_count_today(self, connection, ip_address):
        row = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM access_requests
            WHERE ip_address = ? AND DATE(created_at) = DATE('now')
            """,
            [ip_address],
        ).fetchone()
        return row["count"]

    def _delete_oldest_for_queue_limit(self, connection, queue_limit):
        row = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM access_requests
            """
        ).fetchone()
        delete_count = row["count"] - queue_limit + 1

        if delete_count <= 0:
            return 0
        cursor = connection.execute(
            """
            DELETE FROM access_requests
            WHERE id IN (
                SELECT id
                FROM access_requests
                ORDER BY created_at ASC, id ASC
                LIMIT ?
            )
            """,
            [delete_count],
        )
        return cursor.rowcount


access_request_repository = AccessRequestRepository()
