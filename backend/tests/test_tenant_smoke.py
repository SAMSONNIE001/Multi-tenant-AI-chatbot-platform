from io import BytesIO
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app


def _unique(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:8]}"


def test_tenant_smoke_onboard_login_bots_and_knowledge(monkeypatch):
    # Keep upload/reindex paths offline and deterministic in CI.
    monkeypatch.setattr("app.rag.service.embed_text", lambda _text: [0.0] * 1536)

    tenant_name = f"Smoke Tenant {_unique('name')}"
    admin_local = _unique("admin")
    admin_email = f"{admin_local}@example.com"
    password = "StrongPass123!"

    with TestClient(app) as client:
        onboard_resp = client.post(
            "/api/v1/tenant/onboard",
            json={
                "tenant_name": tenant_name,
                "admin_email": admin_email,
                "admin_password": password,
                "compliance_level": "standard",
                "bot_name": "Main Website Bot",
                "allowed_origins": ["https://example.com"],
            },
        )
        assert onboard_resp.status_code == 200
        onboard = onboard_resp.json()

        tenant_id = onboard["tenant"]["id"]
        bot_id = onboard["bot_id"]
        access_token = onboard["access_token"]

        assert onboard["tenant"]["name"] == tenant_name
        assert onboard["admin"]["tenant_id"] == tenant_id
        assert onboard["admin"]["email"] == admin_email
        assert onboard["bot_api_key"]
        assert onboard["refresh_token"]

        login_resp = client.post(
            "/api/v1/auth/login",
            json={
                "tenant_id": tenant_id,
                "email": admin_email,
                "password": password,
            },
        )
        assert login_resp.status_code == 200
        login = login_resp.json()
        assert login["access_token"]
        assert login["refresh_token"]

        # Tenant ID is optional when email maps to a single tenant.
        login_email_only_resp = client.post(
            "/api/v1/auth/login",
            json={
                "email": admin_email,
                "password": password,
            },
        )
        assert login_email_only_resp.status_code == 200
        login_email_only = login_email_only_resp.json()
        assert login_email_only["access_token"]
        assert login_email_only["refresh_token"]

        headers = {"Authorization": f"Bearer {access_token}"}

        list_resp = client.get("/api/v1/tenant/bots", headers=headers)
        assert list_resp.status_code == 200
        bots = list_resp.json()
        assert any(b["id"] == bot_id for b in bots)

        create_resp = client.post(
            "/api/v1/tenant/bots",
            headers=headers,
            json={
                "name": "Support Bot 2",
                "allowed_origins": ["https://docs.example.com"],
            },
        )
        assert create_resp.status_code == 200
        created = create_resp.json()
        created_bot_id = created["id"]
        assert created["tenant_id"] == tenant_id
        assert created["api_key"]

        patch_resp = client.patch(
            f"/api/v1/tenant/bots/{created_bot_id}",
            headers=headers,
            json={
                "name": "Support Bot Updated",
                "allowed_origins": ["https://help.example.com"],
                "is_active": True,
            },
        )
        assert patch_resp.status_code == 200
        patched = patch_resp.json()
        assert patched["id"] == created_bot_id
        assert patched["name"] == "Support Bot Updated"
        assert patched["allowed_origins"] == ["https://help.example.com"]
        assert patched["is_active"] is True

        file_payload = BytesIO(b"Order status FAQ: Your order ships in 2 business days.")
        upload_resp = client.post(
            "/api/v1/tenant/knowledge/upload",
            headers=headers,
            files={"file": ("faq.txt", file_payload, "text/plain")},
        )
        assert upload_resp.status_code == 200
        upload = upload_resp.json()
        assert upload["tenant_id"] == tenant_id
        assert upload["filename"] == "faq.txt"
        assert upload["document_id"]
        assert upload["chunk_count"] >= 1

        status_resp = client.get("/api/v1/tenant/knowledge/status", headers=headers)
        assert status_resp.status_code == 200
        status = status_resp.json()
        assert status["tenant_id"] == tenant_id
        assert status["document_count"] >= 1
        assert status["chunk_count"] >= 1
        assert status["latest_document_id"] == upload["document_id"]


def test_login_email_only_requires_tenant_hint_when_email_is_ambiguous():
    shared_email = f"{_unique('shared')}@example.com"
    password = "StrongPass123!"

    with TestClient(app) as client:
        for idx in (1, 2):
            onboard_resp = client.post(
                "/api/v1/tenant/onboard",
                json={
                    "tenant_id": f"t_amb_{idx}_{uuid4().hex[:8]}",
                    "tenant_name": f"Ambiguous Tenant {idx}",
                    "admin_id": f"u_amb_{idx}_{uuid4().hex[:8]}",
                    "admin_email": shared_email,
                    "admin_password": password,
                    "compliance_level": "standard",
                    "bot_name": f"Bot {idx}",
                    "allowed_origins": ["https://example.com"],
                },
            )
            assert onboard_resp.status_code == 200

        login_resp = client.post(
            "/api/v1/auth/login",
            json={
                "email": shared_email,
                "password": password,
            },
        )
        assert login_resp.status_code == 409
        assert "Provide tenant_id" in login_resp.json()["detail"]


def test_tenant_integrations_status_reflects_live_channels():
    tenant_name = f"Integrations Tenant {_unique('name')}"
    admin_local = _unique("admin")
    admin_email = f"{admin_local}@example.com"
    password = "StrongPass123!"

    with TestClient(app) as client:
        onboard_resp = client.post(
            "/api/v1/tenant/onboard",
            json={
                "tenant_name": tenant_name,
                "admin_email": admin_email,
                "admin_password": password,
                "compliance_level": "standard",
                "bot_name": "Main Website Bot",
                "allowed_origins": ["https://example.com"],
            },
        )
        assert onboard_resp.status_code == 200
        access_token = onboard_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}

        status_initial = client.get("/api/v1/tenant/integrations/status", headers=headers)
        assert status_initial.status_code == 200
        data_initial = status_initial.json()
        assert data_initial["website_live_chat"]["enabled"] is True
        assert data_initial["whatsapp_business"]["configured"] is False
        assert data_initial["facebook_messenger"]["configured"] is False
        assert data_initial["telegram"]["supported"] is False

        wa_create = client.post(
            "/api/v1/admin/channels/accounts",
            headers=headers,
            json={
                "channel_type": "whatsapp",
                "name": "WhatsApp Main",
                "access_token": "wa_dummy_access_token_12345",
                "app_secret": "wa_dummy_app_secret",
                "phone_number_id": "1234567890",
            },
        )
        assert wa_create.status_code == 200

        fb_create = client.post(
            "/api/v1/admin/channels/accounts",
            headers=headers,
            json={
                "channel_type": "facebook",
                "name": "Facebook Main",
                "access_token": "fb_dummy_access_token_12345",
                "app_secret": "fb_dummy_app_secret",
                "page_id": "112233445566778",
            },
        )
        assert fb_create.status_code == 200

        status_after = client.get("/api/v1/tenant/integrations/status", headers=headers)
        assert status_after.status_code == 200
        data_after = status_after.json()
        assert data_after["whatsapp_business"]["enabled"] is True
        assert data_after["facebook_messenger"]["enabled"] is True
        assert data_after["instagram"]["configured"] is False
