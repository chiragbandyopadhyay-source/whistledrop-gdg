import hashlib
import hmac
import secrets
import time
from collections import defaultdict, deque
from datetime import datetime, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from . import config

# No 0/O/1/I so codes are easy to read out and copy by hand
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def generate_case_code():
    raw = "".join(secrets.choice(_ALPHABET) for _ in range(16))
    return "WD-" + "-".join(raw[i:i + 4] for i in range(0, 16, 4))


def normalize_case_code(code):
    return code.strip().upper()


def hash_case_code(code):
    return hmac.new(
        config.CASE_PEPPER.encode(),
        normalize_case_code(code).encode(),
        hashlib.sha256,
    ).hexdigest()


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def coarse_now_iso():
    return datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) \
        .isoformat(timespec="seconds")


class RateLimiter:
    def __init__(self, max_events, window):
        self.max = max_events
        self.window = window
        self._hits = defaultdict(deque)

    def allow(self, key):
        k = hashlib.sha256((config.CASE_PEPPER + key).encode()).hexdigest()
        now = time.monotonic()
        q = self._hits[k]
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.max:
            return False
        q.append(now)
        return True

    def reset(self):
        self._hits.clear()


submit_limiter = RateLimiter(config.RATE_LIMIT_MAX, config.RATE_LIMIT_WINDOW)
login_limiter = RateLimiter(10, 600)

_bearer = HTTPBearer(auto_error=False)


def verify_credentials(username, password):
    ok_user = hmac.compare_digest(username.encode(), config.MOD_USERNAME.encode())
    ok_pass = hmac.compare_digest(password.encode(), config.MOD_PASSWORD.encode())
    return ok_user and ok_pass


def create_token(username):
    now = int(time.time())
    return jwt.encode(
        {"sub": username, "role": "moderator", "iat": now,
         "exp": now + config.JWT_TTL_SECONDS},
        config.JWT_SECRET, algorithm="HS256")


def require_moderator(creds: HTTPAuthorizationCredentials = Depends(_bearer)):
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token",
                            headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = jwt.decode(creds.credentials, config.JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token",
                            headers={"WWW-Authenticate": "Bearer"})
    if payload.get("role") != "moderator":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Moderator role required")
    return payload["sub"]
