import os
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


_PLACEHOLDER_SECRETS = {"", "change-this-secret", "replace_with_a_long_random_secret"}


def load_jwt_secret() -> str:
    """Refuse to start with a missing, placeholder, or short JWT secret.

    Every service verifies login tokens with this one shared secret, so anyone
    who knows it can forge a token for any user. Generate a strong one with:
        python scripts/setup_env.py
    """
    secret = os.getenv("JWT_SECRET", "")
    if secret in _PLACEHOLDER_SECRETS or len(secret) < 32:
        raise RuntimeError(
            "JWT_SECRET is missing, a known placeholder, or shorter than 32 characters. "
            "Run 'python scripts/setup_env.py' to generate a strong secret."
        )
    return secret


class Settings:
    db_host: str = os.getenv("DB_HOST", "localhost")
    db_port: int = int(os.getenv("DB_PORT", "3306"))
    db_name: str = os.getenv("DB_NAME", "expense_tracker")
    db_user: str = os.getenv("DB_USER", "root")
    db_password: str = os.getenv("DB_PASSWORD", "")
    jwt_secret: str = load_jwt_secret()
    jwt_algorithm: str = "HS256"
    # Where to reach the Notification Service. "127.0.0.1" only works when every service runs on the
    # same machine; in Docker/Kubernetes this becomes a service name (e.g. http://notification-service:8006).
    notification_service_url: str = os.getenv("NOTIFICATION_SERVICE_URL", "http://127.0.0.1:8006")
    downstream_timeout_seconds: float = float(os.getenv("DOWNSTREAM_TIMEOUT_SECONDS", "2"))

    @property
    def database_url(self) -> str:
        return (
            f"mysql+pymysql://{quote_plus(self.db_user)}:{quote_plus(self.db_password)}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}?charset=utf8mb4"
        )


settings = Settings()