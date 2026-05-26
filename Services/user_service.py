import re

from werkzeug.security import check_password_hash, generate_password_hash

from Repositories.user_repository import user_repository as default_user_repository


USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_]+$")
ACCOUNT_CATEGORY_BASIC = "basic"
ACCOUNT_CATEGORY_TRUSTED = "trusted"
ACCOUNT_CATEGORY_ADMIN = "admin"
ACCOUNT_CATEGORIES = {
    ACCOUNT_CATEGORY_BASIC,
    ACCOUNT_CATEGORY_TRUSTED,
    ACCOUNT_CATEGORY_ADMIN,
}
ADMIN_MANAGED_ACCOUNT_CATEGORIES = {
    ACCOUNT_CATEGORY_BASIC,
    ACCOUNT_CATEGORY_TRUSTED,
}


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
        user_id = self._user_repository.create_user(
            username,
            password_hash,
            ACCOUNT_CATEGORY_BASIC,
        )
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

    def get_user(self, user_id):
        return self._user_repository.find_by_id(user_id)

    def update_account_category(self, acting_user_id, target_user_id, account_category):
        account_category = (account_category or "").strip().lower()
        if account_category not in ADMIN_MANAGED_ACCOUNT_CATEGORIES:
            return None, "Invalid account category"

        acting_user = self._user_repository.find_by_id(acting_user_id)
        if not acting_user or acting_user["account_category"] != ACCOUNT_CATEGORY_ADMIN:
            return None, "Admin account is required"

        target_user = self._user_repository.find_by_id(target_user_id)
        if not target_user:
            return None, "User was not found"
        if target_user["account_category"] == ACCOUNT_CATEGORY_ADMIN:
            return None, "Admin users cannot be changed here"

        updated = self._user_repository.update_account_category(
            target_user_id,
            account_category,
        )
        if not updated:
            return None, "User was not found"
        return self._user_repository.find_by_id(target_user_id), None

    def list_users(self, acting_user_id):
        acting_user = self._user_repository.find_by_id(acting_user_id)
        if not acting_user or acting_user["account_category"] != ACCOUNT_CATEGORY_ADMIN:
            return None, "Admin account is required"
        return self._user_repository.list_users(), None

    def create_admin(self, username, password):
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
        user_id = self._user_repository.replace_admins_with_new_admin(
            username,
            password_hash,
        )
        if user_id is None:
            return None, "User id already exists"
        return self._user_repository.find_by_id(user_id), None


user_service = UserService()
