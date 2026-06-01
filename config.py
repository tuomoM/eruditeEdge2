import os


BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_env_file():
    env_path = os.path.join(BASE_DIR, ".env")
    if not os.path.exists(env_path):
        return

    with open(env_path, encoding="utf-8") as env_file:
        for line in env_file:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


_load_env_file()


def _default_database_path():
    if os.environ.get("DATABASE"):
        return os.environ["DATABASE"]

    railway_volume_path = os.environ.get("RAILWAY_VOLUME_MOUNT_PATH")
    if railway_volume_path:
        return os.path.join(railway_volume_path, "database.db")

    return os.path.join(BASE_DIR, "database.db")


DATABASE = _default_database_path()
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")
TRUSTED_AI_DAILY_QUOTA = int(os.environ.get("TRUSTED_AI_DAILY_QUOTA", "20"))
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_SCHEME = os.environ.get("GOOGLE_REDIRECT_SCHEME", "")
ROTATE_ADMIN_ALLOWED = os.environ.get("ROTATE_ADMIN_ALLOWED", "")
