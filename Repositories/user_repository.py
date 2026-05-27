from sqlite3 import IntegrityError
from datetime import datetime, timezone

import db


class UserRepository:
    def create_user_with_invite_code(
        self,
        username,
        password_hash,
        invite_code,
        account_category="basic",
    ):
        now = datetime.now(timezone.utc).isoformat()
        connection = db.get_connection()
        try:
            invite_rows = connection.execute(
                """
                SELECT id
                FROM invite_codes
                WHERE code = ?
                    AND used_by IS NULL
                    AND expires_at > ?
                """,
                [invite_code, now],
            ).fetchall()
            if not invite_rows:
                connection.rollback()
                return None, "Invite code is invalid or expired"

            cursor = connection.execute(
                """
                INSERT INTO users (username, password_hash, account_category)
                VALUES (?, ?, ?)
                """,
                [username, password_hash, account_category],
            )
            user_id = cursor.lastrowid
            cursor = connection.execute(
                """
                UPDATE invite_codes
                SET used_by = ?, used_at = ?
                WHERE id = ? AND used_by IS NULL
                """,
                [user_id, now, invite_rows[0]["id"]],
            )
            if cursor.rowcount == 0:
                connection.rollback()
                return None, "Invite code is invalid or expired"

            connection.commit()
            return user_id, None
        except IntegrityError:
            connection.rollback()
            return None, "User id already exists"
        except Exception:
            connection.rollback()
            raise

    def find_by_username(self, username):
        result = db.query(
            """
            SELECT id, username, password_hash, account_category
            FROM users
            WHERE username = ?
            """,
            [username],
        )
        if result:
            return result[0]
        return None

    def find_by_id(self, user_id):
        result = db.query(
            """
            SELECT id, username, password_hash, account_category
            FROM users
            WHERE id = ?
            """,
            [user_id],
        )
        if result:
            return result[0]
        return None

    def user_exists(self, username):
        return self.find_by_username(username) is not None

    def user_count(self):
        result = db.query("SELECT COUNT(*) AS count FROM users")
        return result[0]["count"]

    def list_users(self):
        return [
            dict(row)
            for row in db.query(
                """
                SELECT
                    users.id,
                    users.username,
                    users.account_category,
                    users.created_at,
                    COUNT(vocabulary_entries.id) AS vocabulary_count
                FROM users
                LEFT JOIN vocabulary_entries
                    ON vocabulary_entries.created_by = users.id
                GROUP BY users.id
                ORDER BY users.username
                """
            )
        ]

    def update_account_category(self, user_id, account_category):
        cursor = db.execute(
            """
            UPDATE users
            SET account_category = ?
            WHERE id = ?
            """,
            [account_category, user_id],
        )
        return cursor.rowcount > 0

    def replace_admins_with_new_admin(self, username, password_hash):
        connection = db.get_connection()
        try:
            connection.execute(
                """
                UPDATE users
                SET account_category = 'trusted'
                WHERE account_category = 'admin'
                """
            )
            cursor = connection.execute(
                """
                INSERT INTO users (username, password_hash, account_category)
                VALUES (?, ?, 'admin')
                """,
                [username, password_hash],
            )
            connection.commit()
            return cursor.lastrowid
        except IntegrityError:
            connection.rollback()
            return None
        except Exception:
            connection.rollback()
            raise


user_repository = UserRepository()
