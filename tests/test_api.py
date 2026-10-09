import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import app, login_limiter, submit_limiter, track_limiter


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "test.sqlite3"))
    monkeypatch.setattr(config, "CASE_PEPPER", "test-only-pepper-with-enough-entropy")
    monkeypatch.setattr(config, "JWT_SECRET", "test-only-jwt-secret-with-enough-entropy")
    monkeypatch.setattr(config, "MOD_USERNAME", "test-moderator")
    monkeypatch.setattr(config, "MOD_PASSWORD", "test-password-not-for-production")
    submit_limiter.reset()
    login_limiter.reset()
    track_limiter.reset()
    with TestClient(app) as test_client:
        yield test_client
    submit_limiter.reset()
    login_limiter.reset()
    track_limiter.reset()


def submit(client, description="The access door does not lock after 6pm."):
    response = client.post(
        "/reports",
        json={
            "category": "Security",
            "description": description,
            "evidence_url": "https://example.com/evidence",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["case_code"]


def moderator_headers(client):
    response = client.post(
        "/moderator/login",
        json={"username": "test-moderator", "password": "test-password-not-for-production"},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_anonymous_submit_and_track(client):
    code = submit(client)
    response = client.get("/reports/track", headers={"X-Case-Code": code})
    assert response.status_code == 200
    data = response.json()
    assert data["category"] == "Security"
    assert data["status"] == "SUBMITTED"
    assert data["updates"] == []


def test_invalid_case_code_and_missing_header(client):
    assert client.get("/reports/track", headers={"X-Case-Code": "not-a-real-code"}).status_code == 404
    assert client.get("/reports/track").status_code == 400


def test_report_validation_rejects_invalid_category_and_url(client):
    bad_category = client.post(
        "/reports",
        json={"category": "Other-ish", "description": "A sufficiently long description."},
    )
    assert bad_category.status_code == 422
    bad_url = client.post(
        "/reports",
        json={
            "category": "Other",
            "description": "A sufficiently long description.",
            "evidence_url": "javascript:alert(1)",
        },
    )
    assert bad_url.status_code == 422


def test_moderator_routes_require_authentication(client):
    response = client.get("/moderator/reports")
    assert response.status_code == 401


def test_status_workflow_and_reporter_updates(client):
    code = submit(client)
    headers = moderator_headers(client)
    listing = client.get("/moderator/reports", headers=headers)
    assert listing.status_code == 200
    report_id = listing.json()["results"][0]["id"]

    invalid_first_transition = client.patch(
        f"/moderator/reports/{report_id}/status",
        headers=headers,
        json={"status": "RESOLVED"},
    )
    assert invalid_first_transition.status_code == 409

    moved = client.patch(
        f"/moderator/reports/{report_id}/status",
        headers=headers,
        json={"status": "UNDER_REVIEW", "message": "A moderator is reviewing this."},
    )
    assert moved.status_code == 200
    assert moved.json()["status"] == "UNDER_REVIEW"

    update = client.post(
        f"/moderator/reports/{report_id}/updates",
        headers=headers,
        json={"message": "We have requested more information."},
    )
    assert update.status_code == 201

    tracked = client.get("/reports/track", headers={"X-Case-Code": code})
    assert tracked.status_code == 200
    assert tracked.json()["status"] == "UNDER_REVIEW"
    assert [item["message"] for item in tracked.json()["updates"]] == [
        "A moderator is reviewing this.",
        "We have requested more information.",
    ]

    resolved = client.patch(
        f"/moderator/reports/{report_id}/status",
        headers=headers,
        json={"status": "RESOLVED", "message": "Issue fixed."},
    )
    assert resolved.status_code == 200
    final_transition = client.patch(
        f"/moderator/reports/{report_id}/status",
        headers=headers,
        json={"status": "UNDER_REVIEW"},
    )
    assert final_transition.status_code == 409


def test_login_rejects_wrong_password(client):
    response = client.post(
        "/moderator/login",
        json={"username": "test-moderator", "password": "wrong-password"},
    )
    assert response.status_code == 401
