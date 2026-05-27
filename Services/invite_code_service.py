import secrets
from datetime import datetime, timedelta, timezone

from Repositories.invite_code_repository import (
    invite_code_repository as default_invite_code_repository,
)
from Services.user_service import ACCOUNT_CATEGORY_ADMIN


INVITE_CODE_VALID_DAYS = 5


class InviteCodeService:
    def __init__(self, invite_code_repository=default_invite_code_repository):
        self._invite_code_repository = invite_code_repository

    def create_invite_code(self, acting_user):
        if not acting_user or acting_user["account_category"] != ACCOUNT_CATEGORY_ADMIN:
            return None, "Admin account is required"

        code = secrets.token_urlsafe(24)
        expires_at = datetime.now(timezone.utc) + timedelta(days=INVITE_CODE_VALID_DAYS)
        invite_code_id = self._invite_code_repository.create_invite_code(
            code,
            acting_user["id"],
            expires_at.isoformat(),
        )
        return self._invite_code_repository.get_invite_code(invite_code_id), None

    def list_invite_codes(self, acting_user):
        if not acting_user or acting_user["account_category"] != ACCOUNT_CATEGORY_ADMIN:
            return None, "Admin account is required"
        return self._invite_code_repository.list_invite_codes(), None


invite_code_service = InviteCodeService()
