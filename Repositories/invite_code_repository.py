import db


class InviteCodeRepository:
    def create_invite_code(self, code, created_by, expires_at):
        cursor = db.execute(
            """
            INSERT INTO invite_codes (code, created_by, expires_at)
            VALUES (?, ?, ?)
            """,
            [code, created_by, expires_at],
        )
        return cursor.lastrowid

    def delete_expired_invite_codes(self, now):
        db.execute(
            """
            DELETE FROM invite_codes
            WHERE expires_at <= ?
            """,
            [now],
        )

    def get_invite_code(self, invite_code_id):
        rows = db.query(
            """
            SELECT id, code, created_by, created_at, expires_at, used_by, used_at
            FROM invite_codes
            WHERE id = ?
            """,
            [invite_code_id],
        )
        if not rows:
            return None
        return dict(rows[0])

    def list_invite_codes(self, now):
        return [
            dict(row)
            for row in db.query(
                """
                SELECT
                    invite_codes.id,
                    invite_codes.code,
                    invite_codes.created_by,
                    users.username AS created_by_username,
                    invite_codes.created_at,
                    invite_codes.expires_at,
                    invite_codes.used_by,
                    used_users.username AS used_by_username,
                    invite_codes.used_at
                FROM invite_codes
                JOIN users ON users.id = invite_codes.created_by
                LEFT JOIN users AS used_users ON used_users.id = invite_codes.used_by
                WHERE invite_codes.used_by IS NULL
                    AND invite_codes.expires_at > ?
                ORDER BY invite_codes.created_at DESC, invite_codes.id DESC
                """,
                [now],
            )
        ]


invite_code_repository = InviteCodeRepository()
