import os
import secrets

JWT_SECRET = os.getenv("WD_JWT_SECRET") or secrets.token_hex(32)
CASE_PEPPER = os.getenv("WD_CASE_PEPPER") or "dev-only-pepper-change-me"
DB_PATH = os.getenv("WD_DB_PATH", "whistledrop.db")
MOD_USERNAME = os.getenv("WD_MOD_USERNAME", "moderator")
MOD_PASSWORD = os.getenv("WD_MOD_PASSWORD", "moderator-demo-password")
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