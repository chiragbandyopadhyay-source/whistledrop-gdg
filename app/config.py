import os
import secrets

ENVIRONMENT = os.getenv("WD_ENV", "development").strip().lower()
if ENVIRONMENT not in {"development", "test", "production"}:
    raise RuntimeError("WD_ENV must be development, test, or production")


def _production_secret(name: str, *, min_length: int = 32) -> str:
    value = os.getenv(name, "")
    if len(value) < min_length:
        raise RuntimeError(
            f"{name} must be explicitly configured with at least {min_length} characters "
            "when WD_ENV=production"
        )
    return value


if ENVIRONMENT == "production":
    JWT_SECRET = _production_secret("WD_JWT_SECRET")
    CASE_PEPPER = _production_secret("WD_CASE_PEPPER")
    MOD_USERNAME = os.getenv("WD_MOD_USERNAME", "")
    MOD_PASSWORD = _production_secret("WD_MOD_PASSWORD", min_length=16)
    if not MOD_USERNAME.strip():
        raise RuntimeError("WD_MOD_USERNAME must be set when WD_ENV=production")
    if MOD_PASSWORD == "moderator-demo-password":
        raise RuntimeError("The demo moderator password is not allowed in production")
else:
    # Convenient local defaults only. Set WD_ENV=production in deployed environments.
    JWT_SECRET = os.getenv("WD_JWT_SECRET") or secrets.token_hex(32)
    CASE_PEPPER = os.getenv("WD_CASE_PEPPER") or "dev-only-pepper-change-me"
    MOD_USERNAME = os.getenv("WD_MOD_USERNAME", "moderator")
    MOD_PASSWORD = os.getenv("WD_MOD_PASSWORD", "moderator-demo-password")

DB_PATH = os.getenv("WD_DB_PATH", "whistledrop.db")
JWT_TTL_SECONDS = 60 * 60

CATEGORIES = ["Security", "Harassment", "Corruption", "Technical", "Other"]
STATUSES = ["SUBMITTED", "UNDER_REVIEW", "RESOLVED", "DISMISSED"]
TRANSITIONS = {
    "SUBMITTED": {"UNDER_REVIEW"},
    "UNDER_REVIEW": {"RESOLVED", "DISMISSED"},
    "RESOLVED": set(),
    "DISMISSED": set(),
}
RATE_LIMIT_MAX = int(os.getenv("WD_RATE_LIMIT_MAX", "5"))
RATE_LIMIT_WINDOW = int(os.getenv("WD_RATE_LIMIT_WINDOW", "600"))
