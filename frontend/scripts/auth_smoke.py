from __future__ import annotations

import argparse
import json
import random
import string
import sys
from dataclasses import dataclass
from typing import Any
from urllib import error, request


def _rand(prefix: str, n: int = 8) -> str:
    letters = string.ascii_lowercase + string.digits
    return f"{prefix}_{''.join(random.choice(letters) for _ in range(n))}"


@dataclass
class StepResult:
    name: str
    ok: bool
    detail: str
    critical: bool = True


class ApiClient:
    def __init__(self, base: str):
        self.base = base.rstrip("/")

    def call(
        self,
        path: str,
        *,
        method: str = "GET",
        token: str | None = None,
        json_body: dict[str, Any] | None = None,
        expected_status: int | None = None,
    ) -> tuple[int, Any]:
        url = f"{self.base}{path}"
        headers: dict[str, str] = {}
        data = None
        if token:
            clean = token.replace("Bearer ", "").strip()
            headers["Authorization"] = f"Bearer {clean}"
        if json_body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(json_body).encode("utf-8")
        req = request.Request(url, data=data, headers=headers, method=method.upper())
        try:
            with request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8")
                try:
                    body: Any = json.loads(raw) if raw else {}
                except Exception:
                    body = raw
                if expected_status is not None and resp.status != expected_status:
                    raise RuntimeError(f"Expected {expected_status}, got {resp.status}: {body}")
                return resp.status, body
        except error.HTTPError as exc:
            raw = exc.read().decode("utf-8")
            try:
                body = json.loads(raw) if raw else {}
            except Exception:
                body = raw
            if expected_status is not None and exc.code == expected_status:
                return exc.code, body
            raise RuntimeError(f"HTTP {exc.code} {path}: {body}") from exc


def run_smoke(api_base: str) -> dict[str, Any]:
    client = ApiClient(api_base)
    steps: list[StepResult] = []

    tenant_id = f"t_{_rand('auth', 10)}"
    admin_id = f"u_{_rand('admin', 10)}"
    admin_email = f"{_rand('admin')}@example.com"
    support_email = f"{_rand('support')}@example.com"
    support_id = f"u_{_rand('support', 10)}"
    password = "StrongPass123!"

    admin_access = ""
    admin_refresh = ""
    support_access = ""

    def step(name: str, fn, critical: bool = True) -> None:
        try:
            detail = fn()
            steps.append(StepResult(name=name, ok=True, detail=str(detail), critical=critical))
        except Exception as exc:
            steps.append(StepResult(name=name, ok=False, detail=str(exc), critical=critical))

    step("ready", lambda: client.call("/ready", expected_status=200)[1])

    def _onboard() -> str:
        _, body = client.call(
            "/api/v1/tenant/onboard",
            method="POST",
            json_body={
                "tenant_id": tenant_id,
                "tenant_name": f"Auth Smoke {_rand('tenant')}",
                "admin_id": admin_id,
                "admin_email": admin_email,
                "admin_password": password,
                "compliance_level": "standard",
                "bot_name": "Auth Smoke Bot",
                "allowed_origins": ["https://example.com"],
            },
            expected_status=200,
        )
        return body["tenant"]["id"]

    step("setup.onboard", _onboard)

    def _login_admin() -> str:
        nonlocal admin_access, admin_refresh
        _, body = client.call(
            "/api/v1/auth/login",
            method="POST",
            json_body={"email": admin_email, "password": password},
            expected_status=200,
        )
        admin_access = body["access_token"]
        admin_refresh = body.get("refresh_token") or ""
        if not admin_refresh:
            raise RuntimeError("Missing refresh_token from login")
        return "admin login ok"

    step("auth.login", _login_admin)

    step("auth.me", lambda: client.call("/api/v1/auth/me", token=admin_access, expected_status=200)[0])

    def _refresh() -> str:
        nonlocal admin_access, admin_refresh
        _, body = client.call(
            "/api/v1/auth/refresh",
            method="POST",
            json_body={"refresh_token": admin_refresh},
            expected_status=200,
        )
        admin_access = body["access_token"]
        admin_refresh = body.get("refresh_token") or ""
        if not admin_refresh:
            raise RuntimeError("Missing rotated refresh_token")
        return "refresh ok"

    step("auth.refresh", _refresh)

    def _register_support() -> str:
        client.call(
            "/api/v1/auth/register",
            method="POST",
            json_body={
                "id": support_id,
                "tenant_id": tenant_id,
                "email": support_email,
                "password": password,
                "role": "support",
            },
            expected_status=200,
        )
        return support_id

    step("role.register_support", _register_support)

    def _login_support() -> str:
        nonlocal support_access
        _, body = client.call(
            "/api/v1/auth/login",
            method="POST",
            json_body={"tenant_id": tenant_id, "email": support_email, "password": password},
            expected_status=200,
        )
        support_access = body["access_token"]
        return "support login ok"

    step("role.login_support", _login_support)

    def _support_forbidden() -> str:
        status, body = client.call(
            "/api/v1/admin/handoff/escalation/sweep",
            method="POST",
            token=support_access,
            expected_status=403,
        )
        return f"{status} {body}"

    step("role.forbidden_advanced_action", _support_forbidden)

    def _logout() -> str:
        client.call(
            "/api/v1/auth/logout",
            method="POST",
            json_body={"refresh_token": admin_refresh},
            expected_status=200,
        )
        return "logout ok"

    step("auth.logout", _logout)

    def _refresh_after_logout() -> str:
        status, body = client.call(
            "/api/v1/auth/refresh",
            method="POST",
            json_body={"refresh_token": admin_refresh},
            expected_status=401,
        )
        return f"{status} {body}"

    step("auth.refresh_revoked_token_blocked", _refresh_after_logout)

    critical_pass = all(s.ok for s in steps if s.critical)
    full_pass = all(s.ok for s in steps)
    return {
        "api_base": api_base,
        "critical_pass": critical_pass,
        "pass": full_pass,
        "steps": [s.__dict__ for s in steps],
        "evidence": {
            "tenant_id": tenant_id,
            "admin_email": admin_email,
            "support_email": support_email,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Auth flow smoke tests")
    parser.add_argument(
        "--api-base",
        default="http://localhost:8000",
        help="Base API URL, e.g. https://staging-...railway.app",
    )
    args = parser.parse_args()

    report = run_smoke(args.api_base)
    print(json.dumps(report, indent=2))
    return 0 if report["critical_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
