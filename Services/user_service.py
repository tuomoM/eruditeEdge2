import re

from werkzeug.security import check_password_hash, generate_password_hash

from Repositories.user_repository import user_repository as default_user_repository


USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_]+$")


class UserService:
    def __init__(self, user_repository=default_user_repository):
        self._user_repository = user_repository

    def validate_username(self, username):
        if username is None:
            return "User id is required"
        username = username.strip()
        if len(username) < 2:
            return "User id must be at least 2 characters"
        if not USERNAME_PATTERN.fullmatch(username):
            return "User id may only contain letters, numbers and underscores"
        return None

    def validate_password(self, username, password):
        if not password:
            return "Password is required"
        if password == username:
            return "Password cannot be same as user id"
        if len(password) < 4:
            return "Password must be at least 4 characters"
        return None

    def register(self, username, password):
        username = (username or "").strip()
        username_error = self.validate_username(username)
        if username_error:
            return None, username_error

        password_error = self.validate_password(username, password)
        if password_error:
            return None, password_error

        if self._user_repository.user_exists(username):
            return None, "User id already exists"

        password_hash = generate_password_hash(password)
        user_id = self._user_repository.create_user(username, password_hash)
        if user_id is None:
            return None, "User id already exists"
        return user_id, None

    def login(self, username, password):
        username = (username or "").strip()
        username_error = self.validate_username(username)
        if username_error:
            return None, "Incorrect user id or password"
        if not password:
            return None, "Incorrect user id or password"

        user = self._user_repository.find_by_username(username)
        if user and check_password_hash(user["password_hash"], password):
            return user["id"], None
        return None, "Incorrect user id or password"


user_service = UserService()
