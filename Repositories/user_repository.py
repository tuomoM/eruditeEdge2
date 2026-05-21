from sqlite3 import IntegrityError

import db


class UserRepository:
    def create_user(self, username, password_hash):
        try:
            cursor = db.execute(
                "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                [username, password_hash],
            )
            return cursor.lastrowid
        except IntegrityError:
            return None

    def find_by_username(self, username):
        result = db.query(
            "SELECT id, username, password_hash FROM users WHERE username = ?",
            [username],
        )
        if result:
            return result[0]
        return None

    def user_exists(self, username):
        return self.find_by_username(username) is not None


user_repository = UserRepository()
