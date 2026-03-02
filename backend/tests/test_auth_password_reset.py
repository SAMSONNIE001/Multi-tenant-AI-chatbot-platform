from fastapi.testclient import TestClient

from app.main import app


def test_password_reset_flow(monkeypatch):
    captured: dict[str, str] = {}

    def fake_send_email(*, to_email: str, tenant_id: str, reset_token: str, code: str, expires_minutes: int) -> bool:
        captured["to_email"] = to_email
        captured["tenant_id"] = tenant_id
        captured["reset_token"] = reset_token
        captured["code"] = code
        captured["expires_minutes"] = str(expires_minutes)
        return True

    monkeypatch.setattr("app.auth.router._send_password_reset_email", fake_send_email)

    email = "reset_admin@example.com"
    old_password = "StrongPass123!"
    new_password = "NewStrongPass123!"

    with TestClient(app) as client:
        onboard_resp = client.post(
            "/api/v1/tenant/onboard",
            json={
                "tenant_name": "Reset Flow Tenant",
                "admin_email": email,
                "admin_password": old_password,
                "compliance_level": "standard",
                "bot_name": "Reset Bot",
                "allowed_origins": ["https://example.com"],
            },
        )
        assert onboard_resp.status_code == 200
        tenant_id = onboard_resp.json()["tenant"]["id"]

        forgot_resp = client.post(
            "/api/v1/auth/password/forgot",
            json={"tenant_id": tenant_id, "email": email},
        )
        assert forgot_resp.status_code == 200
        assert forgot_resp.json()["ok"] is True
        assert captured["to_email"] == email
        assert captured["tenant_id"] == tenant_id
        assert captured["reset_token"]
        assert captured["code"]

        reset_resp = client.post(
            "/api/v1/auth/password/reset",
            json={
                "reset_token": captured["reset_token"],
                "code": captured["code"],
                "new_password": new_password,
            },
        )
        assert reset_resp.status_code == 200
        assert reset_resp.json()["ok"] is True

        old_login = client.post(
            "/api/v1/auth/login",
            json={"tenant_id": tenant_id, "email": email, "password": old_password},
        )
        assert old_login.status_code == 401

        new_login = client.post(
            "/api/v1/auth/login",
            json={"tenant_id": tenant_id, "email": email, "password": new_password},
        )
        assert new_login.status_code == 200
        assert new_login.json()["access_token"]


def test_password_reset_rejects_invalid_code(monkeypatch):
    captured: dict[str, str] = {}

    def fake_send_email(*, to_email: str, tenant_id: str, reset_token: str, code: str, expires_minutes: int) -> bool:
        captured["reset_token"] = reset_token
        return True

    monkeypatch.setattr("app.auth.router._send_password_reset_email", fake_send_email)

    email = "reset_invalid@example.com"
    password = "StrongPass123!"

    with TestClient(app) as client:
        onboard_resp = client.post(
            "/api/v1/tenant/onboard",
            json={
                "tenant_name": "Reset Invalid Code Tenant",
                "admin_email": email,
                "admin_password": password,
                "compliance_level": "standard",
                "bot_name": "Reset Bot",
                "allowed_origins": ["https://example.com"],
            },
        )
        assert onboard_resp.status_code == 200
        tenant_id = onboard_resp.json()["tenant"]["id"]

        forgot_resp = client.post(
            "/api/v1/auth/password/forgot",
            json={"tenant_id": tenant_id, "email": email},
        )
        assert forgot_resp.status_code == 200

        reset_resp = client.post(
            "/api/v1/auth/password/reset",
            json={
                "reset_token": captured["reset_token"],
                "code": "000000",
                "new_password": "NewStrongPass123!",
            },
        )
        assert reset_resp.status_code == 400
        assert "Invalid reset code" in reset_resp.json()["detail"]


def test_forgot_password_rate_limit_returns_generic_success(monkeypatch):
    sent: dict[str, int] = {"count": 0}

    def fake_send_email(*, to_email: str, tenant_id: str, reset_token: str, code: str, expires_minutes: int) -> bool:
        sent["count"] += 1
        return True

    monkeypatch.setattr("app.auth.router._send_password_reset_email", fake_send_email)

    email = "reset_limit@example.com"
    password = "StrongPass123!"

    with TestClient(app) as client:
        onboard_resp = client.post(
            "/api/v1/tenant/onboard",
            json={
                "tenant_name": "Reset Limit Tenant",
                "admin_email": email,
                "admin_password": password,
                "compliance_level": "standard",
                "bot_name": "Reset Bot",
                "allowed_origins": ["https://example.com"],
            },
        )
        assert onboard_resp.status_code == 200
        tenant_id = onboard_resp.json()["tenant"]["id"]

        for _ in range(4):
            forgot_resp = client.post(
                "/api/v1/auth/password/forgot",
                json={"tenant_id": tenant_id, "email": email},
            )
            assert forgot_resp.status_code == 200
            assert forgot_resp.json()["ok"] is True
        assert sent["count"] == 3


def test_password_reset_blocks_after_too_many_invalid_codes(monkeypatch):
    captured: dict[str, str] = {}

    def fake_send_email(*, to_email: str, tenant_id: str, reset_token: str, code: str, expires_minutes: int) -> bool:
        captured["reset_token"] = reset_token
        captured["code"] = code
        return True

    monkeypatch.setattr("app.auth.router._send_password_reset_email", fake_send_email)

    email = "reset_fail_limit@example.com"
    password = "StrongPass123!"

    with TestClient(app) as client:
        onboard_resp = client.post(
            "/api/v1/tenant/onboard",
            json={
                "tenant_name": "Reset Fail Limit Tenant",
                "admin_email": email,
                "admin_password": password,
                "compliance_level": "standard",
                "bot_name": "Reset Bot",
                "allowed_origins": ["https://example.com"],
            },
        )
        assert onboard_resp.status_code == 200
        tenant_id = onboard_resp.json()["tenant"]["id"]

        forgot_resp = client.post(
            "/api/v1/auth/password/forgot",
            json={"tenant_id": tenant_id, "email": email},
        )
        assert forgot_resp.status_code == 200

        for _ in range(5):
            bad_reset = client.post(
                "/api/v1/auth/password/reset",
                json={
                    "reset_token": captured["reset_token"],
                    "code": "000000",
                    "new_password": "NewStrongPass123!",
                },
            )
            assert bad_reset.status_code == 400

        blocked_reset = client.post(
            "/api/v1/auth/password/reset",
            json={
                "reset_token": captured["reset_token"],
                "code": captured["code"],
                "new_password": "NewStrongPass123!",
            },
        )
        assert blocked_reset.status_code == 429
