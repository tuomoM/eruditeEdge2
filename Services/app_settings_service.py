from Repositories.app_setting_repository import (
    app_setting_repository as default_app_setting_repository,
)


AUTO_TRUST_NEW_USERS_KEY = "auto_trust_new_users"


class AppSettingsService:
    def __init__(self, app_setting_repository=default_app_setting_repository):
        self._app_setting_repository = app_setting_repository

    def auto_trust_new_users_enabled(self):
        value = self._app_setting_repository.get_value(AUTO_TRUST_NEW_USERS_KEY)
        if value is None:
            return True
        return value == "true"

    def set_auto_trust_new_users_enabled(self, enabled):
        value = "true" if enabled else "false"
        self._app_setting_repository.set_value(AUTO_TRUST_NEW_USERS_KEY, value)
        return self.auto_trust_new_users_enabled()


app_settings_service = AppSettingsService()
