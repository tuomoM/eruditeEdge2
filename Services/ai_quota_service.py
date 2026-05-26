from Services.user_service import ACCOUNT_CATEGORY_ADMIN
from Repositories.ai_generation_repository import (
    ai_generation_repository as default_ai_generation_repository,
)


class AiQuotaService:
    def __init__(self, ai_generation_repository=default_ai_generation_repository):
        self._ai_generation_repository = ai_generation_repository

    def record_generation_if_allowed(self, user, trusted_daily_quota):
        if user["account_category"] == ACCOUNT_CATEGORY_ADMIN:
            return True, None

        quota = max(int(trusted_daily_quota), 0)
        if self._ai_generation_repository.try_record_generation(user["id"], quota):
            return True, None

        return False, f"Daily AI generation quota reached ({quota})"

    def usage_by_user(self):
        return self._ai_generation_repository.generation_counts()

    def reset_user_usage(self, user_id):
        self._ai_generation_repository.reset_generation_count(user_id)

    def refund_generation(self, user):
        if user["account_category"] == ACCOUNT_CATEGORY_ADMIN:
            return
        self._ai_generation_repository.refund_generation(user["id"])


ai_quota_service = AiQuotaService()
