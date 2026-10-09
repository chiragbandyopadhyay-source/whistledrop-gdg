import uuid
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Request, status

from .db import get_db, init_db
from .schemas import ReportIn
from .security import (coarse_now_iso, generate_case_code, hash_case_code,
                       submit_limiter, RateLimiter)
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, status

from . import config
from .db import get_db, init_db
from .schemas import LoginIn, ReportIn, StatusChangeIn, UpdateIn
from .security import (RateLimiter, coarse_now_iso, create_token, generate_case_code,
                       hash_case_code, login_limiter, now_iso, require_moderator,
                       submit_limiter, verify_credentials)

app = FastAPI(
    title="WhistleDrop",
    description="Anonymous reporting backend.",
    version="1.0.0",
)
track_limiter = RateLimiter(30, 600)


@app.on_event("startup")
def _startup():
    init_db()


@app.middleware("http")
async def _no_cache(request: Request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


def _client_key(request: Request):
    return request.client.host if request.client else "unknown"


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}


@app.post("/reports", status_code=status.HTTP_201_CREATED, tags=["reporter"])
def submit_report(body: ReportIn, request: Request):
    if not submit_limiter.allow(_client_key(request)):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            "Too many submissions, try again later")
    case_code = generate_case_code()
    report_id = uuid.uuid4().hex
    ts = coarse_now_iso()
    with get_db() as db:
        db.execute(
            "INSERT INTO reports (id, case_hash, category, description, evidence_url,"
            " status, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
            (report_id, hash_case_code(case_code), body.category, body.description,
             body.evidence_url, "SUBMITTED", ts, ts))
    return {
        "case_code": case_code,
        "status": "SUBMITTED",
        "message": "Save this case code. It cannot be recovered and is the only way "
                   "to check your report.",
    }


@app.get("/reports/track", tags=["reporter"])
def track_report(request: Request,
                 x_case_code: Optional[str] = Header(default=None, alias="X-Case-Code")):
    if not track_limiter.allow(_client_key(request)):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many requests")
    if not x_case_code:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Case-Code header is required")
    with get_db() as db:
        row = db.execute("SELECT * FROM reports WHERE case_hash = ?",
                         (hash_case_code(x_case_code),)).fetchone()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Case not found")
        updates = db.execute(
            "SELECT message, status, created_at FROM updates WHERE report_id = ? ORDER BY id",
            (row["id"],)).fetchall()
        return {
            "category": row["category"],
            "status": row["status"],
            "submitted_on": row["created_at"],
            "last_updated": row["updated_at"],
            "updates": [dict(u) for u in updates],
            }

@app.get("/moderator/reports", tags=["moderator"])
def list_reports(category: Optional[str] = Query(default=None),
                 status_: Optional[str] = Query(default=None, alias="status"),
                 search: Optional[str] = Query(default=None, max_length=100),
                 limit: int = Query(default=20, ge=1, le=100),
                 offset: int = Query(default=0, ge=0),
                 _mod: str = Depends(require_moderator)):
    if category is not None and category not in config.CATEGORIES:
        raise HTTPException(422, "category must be one of " + str(config.CATEGORIES))
    if status_ is not None and status_ not in config.STATUSES:
        raise HTTPException(422, "status must be one of " + str(config.STATUSES))
    where, params = [], []
    if category:
        where.append("category = ?")
        params.append(category)
    if status_:
        where.append("status = ?")
        params.append(status_)
    if search:
        where.append("description LIKE ?")
        params.append("%" + search + "%")
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    with get_db() as db:
        total = db.execute("SELECT COUNT(*) FROM reports " + clause, params).fetchone()[0]
        rows = db.execute(
            "SELECT id, category, status, description, evidence_url, created_at, updated_at"
            " FROM reports " + clause + " ORDER BY created_at DESC, rowid DESC LIMIT ? OFFSET ?",
            params + [limit, offset]).fetchall()
    return {"total": total, "limit": limit, "offset": offset,
            "results": [dict(r) for r in rows]}


def _get_report_or_404(db, report_id):
    row = db.execute(
        "SELECT id, category, status, description, evidence_url, created_at, updated_at"
        " FROM reports WHERE id = ?", (report_id,)).fetchone()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Report not found")
    return row


@app.get("/moderator/reports/{report_id}", tags=["moderator"])
def get_report(report_id: str, _mod: str = Depends(require_moderator)):
    with get_db() as db:
        row = _get_report_or_404(db, report_id)
        updates = db.execute(
            "SELECT message, status, created_at FROM updates WHERE report_id = ? ORDER BY id",
            (report_id,)).fetchall()
        result = dict(row)
        result["updates"] = [dict(u) for u in updates]
        return result


@app.patch("/moderator/reports/{report_id}/status", tags=["moderator"])
def change_status(report_id: str, body: StatusChangeIn,
                  _mod: str = Depends(require_moderator)):
    with get_db() as db:
        row = _get_report_or_404(db, report_id)
        current = row["status"]
        allowed = config.TRANSITIONS[current]
        if body.status not in allowed:
            raise HTTPException(status.HTTP_409_CONFLICT, {
                "error": "Cannot move from " + current + " to " + body.status,
                "allowed_transitions": sorted(allowed),
            })
        ts = now_iso()
        cur = db.execute(
            "UPDATE reports SET status = ?, updated_at = ? WHERE id = ? AND status = ?",
            (body.status, ts, report_id, current))
        if cur.rowcount == 0:
            raise HTTPException(status.HTTP_409_CONFLICT,
                                "Report status changed concurrently, reload and retry")
        message = body.message or ("Status changed to " + body.status)
        db.execute("INSERT INTO updates (report_id, message, status, created_at)"
                   " VALUES (?,?,?,?)", (report_id, message, body.status, ts))
        return {"id": report_id, "previous_status": current, "status": body.status}


@app.post("/moderator/reports/{report_id}/updates", status_code=201, tags=["moderator"])
def add_update(report_id: str, body: UpdateIn, _mod: str = Depends(require_moderator)):
    with get_db() as db:
        row = _get_report_or_404(db, report_id)
        ts = now_iso()
        db.execute("INSERT INTO updates (report_id, message, status, created_at)"
                   " VALUES (?,?,?,?)", (report_id, body.message, row["status"], ts))
        db.execute("UPDATE reports SET updated_at = ? WHERE id = ?", (ts, report_id))
        return {"id": report_id, "status": row["status"], "message": body.message,
                "created_at": ts}
@app.post("/moderator/login", tags=["moderator"])
def login(body: LoginIn, request: Request):
    if not login_limiter.allow(_client_key(request)):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts")
    if not verify_credentials(body.username, body.password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    return {"access_token": create_token(body.username), "token_type": "bearer",
            "expires_in": config.JWT_TTL_SECONDS}
