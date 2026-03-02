from datetime import datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient

from app.channels.models import CustomerChannelHandle
from app.db.session import SessionLocal
from app.handoff.models import HandoffRequest
from app.main import app


def _unique(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:8]}"


def _onboard_and_token(client: TestClient) -> tuple[str, str]:
    tenant_name = f"Ops Tenant {_unique('name')}"
    admin_email = f"{_unique('admin')}@example.com"
    password = "StrongPass123!"
    resp = client.post(
        "/api/v1/tenant/onboard",
        json={
            "tenant_name": tenant_name,
            "admin_email": admin_email,
            "admin_password": password,
            "compliance_level": "standard",
            "bot_name": "Ops Bot",
            "allowed_origins": ["https://example.com"],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    return body["tenant"]["id"], body["access_token"]


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_admin_handoff_claim_patch_sweep_metrics_and_ops_audit():
    with TestClient(app) as client:
        tenant_id, token = _onboard_and_token(client)
        headers = _headers(token)

        create_resp = client.post(
            "/api/v1/handoff/request",
            headers=headers,
            json={"question": "I need human support", "reason": "manual_test"},
        )
        assert create_resp.status_code == 200
        created = create_resp.json()
        handoff_id = created["id"]
        request_user_id = created["user_id"]

        claim_resp = client.post(f"/api/v1/admin/handoff/{handoff_id}/claim", headers=headers, json={})
        assert claim_resp.status_code == 200
        claimed = claim_resp.json()
        assert claimed["status"] == "open"
        assert claimed["assigned_to_user_id"]

        patch_resp = client.patch(
            f"/api/v1/admin/handoff/{handoff_id}",
            headers=headers,
            json={
                "status": "pending_customer",
                "priority": "low",
                "resolution_note": "Waiting on customer response.",
                "internal_note_append": "Manual ops coverage note.",
            },
        )
        assert patch_resp.status_code == 200
        patched = patch_resp.json()
        assert patched["status"] == "pending_customer"
        assert patched["priority"] == "low"
        assert patched["resolution_note"] == "Waiting on customer response."
        assert "Manual ops coverage note." in (patched["internal_notes"] or "")

        past = datetime.utcnow() - timedelta(hours=4)
        with SessionLocal() as db:
            db.add(
                HandoffRequest(
                    id=f"ho_{uuid4().hex[:20]}",
                    tenant_id=tenant_id,
                    conversation_id=None,
                    user_id=request_user_id,
                    source_channel="api",
                    question="Breached SLA ticket",
                    reason="sla_test",
                    status="open",
                    assigned_to_user_id=None,
                    priority="normal",
                    destination=None,
                    resolution_note=None,
                    internal_notes=None,
                    first_response_due_at=past,
                    first_responded_at=None,
                    resolution_due_at=past,
                    escalation_flag=False,
                    escalated_at=None,
                    created_at=past,
                    updated_at=past,
                    resolved_at=None,
                    closed_at=None,
                )
            )
            db.commit()

        sweep_resp = client.post("/api/v1/admin/handoff/escalation/sweep", headers=headers)
        assert sweep_resp.status_code == 200
        sweep = sweep_resp.json()
        assert sweep["tenant_id"] == tenant_id
        assert sweep["scanned_tickets"] >= 2
        assert sweep["escalated_tickets"] >= 1
        assert sweep["bumped_to_high"] >= 1

        metrics_resp = client.get("/api/v1/admin/handoff/metrics", headers=headers)
        assert metrics_resp.status_code == 200
        metrics = metrics_resp.json()
        assert metrics["tenant_id"] == tenant_id
        assert metrics["totals"]["all_tickets"] >= 2
        assert metrics["totals"]["escalated_tickets"] >= 1

        ops_create_resp = client.post(
            "/api/v1/admin/ops/audit",
            headers=headers,
            json={
                "action_type": "handoff_escalation_sweep",
                "reason": "Coverage verification",
                "metadata_json": {"source": "pytest"},
            },
        )
        assert ops_create_resp.status_code == 200
        ops_created = ops_create_resp.json()
        assert ops_created["action_type"] == "handoff_escalation_sweep"

        ops_list_resp = client.get(
            "/api/v1/admin/ops/audit?action_type=handoff_escalation_sweep&limit=10",
            headers=headers,
        )
        assert ops_list_resp.status_code == 200
        ops_list = ops_list_resp.json()
        assert ops_list["count"] >= 1
        assert any(e["id"] == ops_created["id"] for e in ops_list["entries"])


def test_channel_identity_linking_and_profile_merge(monkeypatch):
    monkeypatch.setattr("app.channels.service.send_messenger_or_instagram_text", lambda *args, **kwargs: None)

    with TestClient(app) as client:
        tenant_id, token = _onboard_and_token(client)
        headers = _headers(token)

        messenger_resp = client.post(
            "/api/v1/admin/channels/accounts",
            headers=headers,
            json={
                "channel_type": "messenger",
                "name": "Messenger QA",
                "page_id": f"pg_{uuid4().hex[:10]}",
                "access_token": "test-token",
            },
        )
        assert messenger_resp.status_code == 200
        page_id = messenger_resp.json()["page_id"]

        ig_resp = client.post(
            "/api/v1/admin/channels/accounts",
            headers=headers,
            json={
                "channel_type": "instagram",
                "name": "Instagram QA",
                "instagram_account_id": f"ig_{uuid4().hex[:10]}",
                "access_token": "test-token",
            },
        )
        assert ig_resp.status_code == 200
        instagram_account_id = ig_resp.json()["instagram_account_id"]

        sender_source = f"ext_{uuid4().hex[:10]}"
        sender_target = f"ext_{uuid4().hex[:10]}"

        for sender in (sender_source, sender_target):
            webhook_resp = client.post(
                "/api/v1/channels/meta/webhook",
                json={
                    "object": "page",
                    "entry": [
                        {
                            "messaging": [
                                {
                                    "sender": {"id": sender},
                                    "recipient": {"id": page_id},
                                    "message": {"text": "I need human support"},
                                }
                            ]
                        }
                    ],
                },
            )
            assert webhook_resp.status_code == 200
            assert webhook_resp.json()["processed_messages"] == 1

        ig_link_resp = client.post(
            "/api/v1/channels/meta/webhook",
            json={
                "object": "instagram",
                "entry": [
                    {
                        "messaging": [
                            {
                                "sender": {"id": sender_target},
                                "recipient": {"id": instagram_account_id},
                                "message": {"text": "I need human support"},
                            }
                        ]
                    }
                ],
            },
        )
        assert ig_link_resp.status_code == 200
        assert ig_link_resp.json()["processed_messages"] == 1

        profiles_resp = client.get("/api/v1/admin/channels/profiles?limit=100", headers=headers)
        assert profiles_resp.status_code == 200
        profiles = profiles_resp.json()["profiles"]
        assert len(profiles) >= 2

        source_profile_id = None
        target_profile_id = None
        for profile in profiles:
            ext_ids = {h["external_user_id"] for h in profile["handles"]}
            if sender_source in ext_ids:
                source_profile_id = profile["id"]
            if sender_target in ext_ids:
                target_profile_id = profile["id"]
        assert source_profile_id
        assert target_profile_id
        assert source_profile_id != target_profile_id

        merge_resp = client.post(
            "/api/v1/admin/channels/profiles/merge",
            headers=headers,
            json={
                "source_profile_id": source_profile_id,
                "target_profile_id": target_profile_id,
            },
        )
        assert merge_resp.status_code == 200
        merged = merge_resp.json()
        assert merged["tenant_id"] == tenant_id
        assert merged["moved_handoffs"] >= 1

        with SessionLocal() as db:
            target_handles = (
                db.query(CustomerChannelHandle)
                .filter(
                    CustomerChannelHandle.tenant_id == tenant_id,
                    CustomerChannelHandle.customer_profile_id == target_profile_id,
                )
                .all()
            )
            target_handle_keys = {(h.channel_type, h.external_user_id) for h in target_handles}

        assert ("messenger", sender_source) in target_handle_keys
        assert ("messenger", sender_target) in target_handle_keys
        assert ("instagram", sender_target) in target_handle_keys
