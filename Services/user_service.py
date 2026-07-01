import re
import secrets

from werkzeug.security import check_password_hash, generate_password_hash

from Repositories.user_repository import user_repository as default_user_repository


USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_]+$")
USERNAME_CHARACTER_PATTERN = re.compile(r"[^A-Za-z0-9_]+")
ADMIN_PASSWORD_MIN_LENGTH = 12
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

    def validate_admin_password(self, username, password):
        password_error = self.validate_password(username, password)
        if password_error:
            return password_error
        if len(password) < ADMIN_PASSWORD_MIN_LENGTH:
            return f"Admin password must be at least {ADMIN_PASSWORD_MIN_LENGTH} characters"
        if not re.search(r"[a-z]", password):
            return "Admin password must include a lowercase letter"
        if not re.search(r"[A-Z]", password):
            return "Admin password must include an uppercase letter"
        if not re.search(r"\d", password):
            return "Admin password must include a number"
        if not re.search(r"[^A-Za-z0-9]", password):
            return "Admin password must include a symbol"
        return None

    def register(self, username, password, invite_code=None):
        username = (username or "").strip()
        invite_code = (invite_code or "").strip()
        username_error = self.validate_username(username)
        if username_error:
            return None, username_error

        password_error = self.validate_password(username, password)
        if password_error:
            return None, password_error

        password_hash = generate_password_hash(password)
        user_id, error = self._user_repository.create_user(
            username,
            password_hash,
            ACCOUNT_CATEGORY_BASIC,
            invite_code=invite_code,
        )
        if error:
            return None, error
        if user_id is None:
            return None, "User id already exists"
        return user_id, None

    def register_google_user(self, google_user, invite_code=None):
        invite_code = (invite_code or "").strip()

        google_sub = (google_user.get("sub") or "").strip()
        google_email = (google_user.get("email") or "").strip().lower()
        if not google_sub or not google_email or not google_user.get("email_verified"):
            return None, "Google account email could not be verified"

        if self._user_repository.find_by_google_sub(google_sub):
            return None, "Google account is already registered"

        username = self._username_from_google_email(google_email)
        password_hash = generate_password_hash(secrets.token_urlsafe(32))
        user_id, error = self._user_repository.create_user(
            username,
            password_hash,
            ACCOUNT_CATEGORY_BASIC,
            google_sub,
            google_email,
            invite_code,
        )
        if error:
            return None, error
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

    def login_google_user(self, google_user):
        google_sub = (google_user.get("sub") or "").strip()
        google_email = (google_user.get("email") or "").strip().lower()
        if not google_sub or not google_email or not google_user.get("email_verified"):
            return None, "Google account email could not be verified"

        user = self._user_repository.find_by_google_sub(google_sub)
        if not user:
            return None, "Google account is not registered"
        return user["id"], None

    def _username_from_google_email(self, email):
        local_part = email.split("@", 1)[0]
        username = USERNAME_CHARACTER_PATTERN.sub("_", local_part).strip("_")
        if len(username) < 2:
            username = f"user_{username}"
        return username[:40]

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

    def count_users_created_since(self, acting_user_id, created_since):
        acting_user = self._user_repository.find_by_id(acting_user_id)
        if not acting_user or acting_user["account_category"] != ACCOUNT_CATEGORY_ADMIN:
            return None, "Admin account is required"
        return self._user_repository.count_created_since(created_since), None

    def create_admin(self, username, password):
        username = (username or "").strip()
        if self._user_repository.admin_exists():
            return None, "Admin user already exists"

        username_error = self.validate_username(username)
        if username_error:
            return None, username_error

        password_error = self.validate_admin_password(username, password)
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

    def rotate_admin(self, current_admin_username, current_admin_password, new_admin_username):
        current_admin_username = (current_admin_username or "").strip()
        new_admin_username = (new_admin_username or "").strip()
        if current_admin_username == new_admin_username:
            return None, "New admin must be a different user"

        current_admin = self._user_repository.find_by_username(current_admin_username)
        if (
            not current_admin
            or current_admin["account_category"] != ACCOUNT_CATEGORY_ADMIN
            or not current_admin_password
            or not check_password_hash(current_admin["password_hash"], current_admin_password)
        ):
            return None, "Admin credentials are invalid"

        new_admin = self._user_repository.find_by_username(new_admin_username)
        if not new_admin:
            return None, "Trusted user was not found"
        if new_admin["account_category"] != ACCOUNT_CATEGORY_TRUSTED:
            return None, "New admin must be a trusted user"

        rotated = self._user_repository.rotate_admin(
            current_admin["id"],
            new_admin["id"],
        )
        if not rotated:
            return None, "Admin rotation failed"
        return self._user_repository.find_by_id(new_admin["id"]), None


user_service = UserService()
