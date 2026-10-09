# WhistleDrop

A backend for anonymous reporting. Anyone can submit a report without an account and get a secret case code to track it. Moderators review reports but do not receive reporter identity fields.

Built with Python, FastAPI and SQLite.

## Setup

Requires Python 3.10+.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

export WD_JWT_SECRET="$(python -c 'import secrets; print(secrets.token_hex(32))')"
export WD_CASE_PEPPER="$(python -c 'import secrets; print(secrets.token_hex(32))')"
export WD_MOD_USERNAME='moderator'
export WD_MOD_PASSWORD='choose-a-long-unique-password'
uvicorn app.main:app --no-access-log
```

Open http://127.0.0.1:8000/docs to try the API. For local development, the app has convenience defaults; do not use those defaults for a real deployment.

### Production configuration

Set `WD_ENV=production` before starting the service. Production startup requires explicitly configured `WD_JWT_SECRET` and `WD_CASE_PEPPER` values of at least 32 characters, a `WD_MOD_PASSWORD` of at least 16 characters, and a non-empty `WD_MOD_USERNAME`. The default demo password is rejected in production. Generate independent random secrets and store them in your deployment's secret manager; do not commit them to Git.

`--no-access-log` disables Uvicorn's access log only. If deployed behind a proxy or hosting provider, review that provider's logging and retention settings too.

## Run tests

```bash
pytest -q
```

Tests use a temporary SQLite database and do not require a running server.

## Endpoints

| Endpoint | Who | What it does |
|---|---|---|
| `POST /reports` | anyone | Submit a report and receive a case code |
| `GET /reports/track` | reporter | Check status and updates using the `X-Case-Code` header |
| `POST /moderator/login` | moderator | Get a login token |
| `GET /moderator/reports` | moderator | List reports, filter by category/status/search |
| `GET /moderator/reports/{id}` | moderator | View one report and its updates |
| `PATCH /moderator/reports/{id}/status` | moderator | Change status, with an optional message |
| `POST /moderator/reports/{id}/updates` | moderator | Add a status update |

Categories: Security, Harassment, Corruption, Technical, Other.

Status flow: `SUBMITTED -> UNDER_REVIEW -> RESOLVED` or `DISMISSED`. RESOLVED and DISMISSED are final. Invalid moves return `409 Conflict`.

## Examples

Submit a report:

```bash
curl -X POST http://127.0.0.1:8000/reports -H 'Content-Type: application/json' \
  -d '{"category":"Security","description":"Badge reader is bypassed after 10pm."}'
```

The response includes a one-time `case_code`. Save it securely; it cannot be recovered.

Check progress:

```bash
curl http://127.0.0.1:8000/reports/track \
  -H 'X-Case-Code: WD-7K2M-QX9P-4HTD-WE6R'
```

Moderator requests use `Authorization: Bearer <access_token>` with the token returned by `POST /moderator/login`.

## Screenshots

![Swagger endpoints](screenshots/swagger.png)
![Submit a report](screenshots/submit.png)
![Reporter tracks the report](screenshots/track.png)
![Moderator updates status, reporter sees it](screenshots/status_update.png)

## How anonymity is approached

- The reports table does not store reporter account, email, device, or IP fields.
- Case codes are generated with 80 bits of randomness, displayed once, and never stored directly. The database stores only a keyed HMAC-SHA256 hash of each code.
- Moderators see random report IDs, not case codes or their hashes.
- Report creation timestamps are rounded to the hour to reduce precision that could make activity correlation easier.
- The case code is sent in a header rather than a URL. This reduces URL-based leakage, but clients and infrastructure must still be configured not to log sensitive headers.
- Rate limiting uses the client's network address transiently in process memory and does not persist it to the database. This is not a guarantee of anonymity against infrastructure-level logging.
- Uvicorn access logging is disabled in the documented command, but reverse proxies, hosting platforms, and monitoring tools may have independent logs.

## Design decisions and limitations

- Status rules are centralized in `app/config.py`.
- Status changes use a conditional update to avoid silently overwriting a concurrently changed status.
- Every status change creates a reporter-visible update; moderators can also add updates without changing status.
- A lost case code cannot be recovered. This is deliberate.
- The example has one moderator account configured through environment variables. For production use, add a managed identity system, secret rotation, audit controls, and deployment-specific privacy review.
- In-memory rate limits reset on restart and are per process; multi-worker or multi-instance deployments need a shared rate limiter.
- SQLite is suitable for a small demonstration, but production availability, backups, access controls, and operational monitoring need separate planning.
