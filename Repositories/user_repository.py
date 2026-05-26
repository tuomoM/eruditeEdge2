from sqlite3 import IntegrityError

import db


class UserRepository:
    def create_user(self, username, password_hash, account_category="basic"):
        try:
            cursor = db.execute(
                """
                INSERT INTO users (username, password_hash, account_category)
                VALUES (?, ?, ?)
                """,
                [username, password_hash, account_category],
            )
            return cursor.lastrowid
        except IntegrityError:
            return None

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
