from sqlite3 import OperationalError
from datetime import datetime, timezone

import db


class AppSettingRepository:
    def get_value(self, key):
        try:
            rows = db.query(
                """
                SELECT value
                FROM app_settings
                WHERE key = ?
                """,
                [key],
            )
        except OperationalError:
            return None
        if not rows:
            return None
        return rows[0]["value"]

    def set_value(self, key, value):
        updated_at = datetime.now(timezone.utc).isoformat()
        db.execute(
            """
            INSERT INTO app_settings (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = excluded.updated_at
            """,
            [key, value, updated_at],
        )


app_setting_repository = AppSettingRepository()
