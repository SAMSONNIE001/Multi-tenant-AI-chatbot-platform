from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from typing import Any
from urllib import error, request


@dataclass
class Step:
    name: str
    ok: bool
    detail: str


class ApiClient:
    def __init__(self, base: str, token: str):
        self.base = base.rstrip("/")
        clean = (token or "").replace("Bearer ", "").strip()
        if not clean:
            raise ValueError("token is required")
        self.token = clean

    def call(self, path: str, *, method: str = "GET", body: dict[str, Any] | None = None) -> tuple[int, Any]:
        headers = {"Authorization": f"Bearer {self.token}"}
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode("utf-8")
        req = request.Request(f"{self.base}{path}", method=method.upper(), headers=headers, data=data)
        try:
            with request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8")
                try:
                    parsed = json.loads(raw) if raw else {}
                except Exception:
                    parsed = raw
                return resp.status, parsed
        except error.HTTPError as exc:
            raw = exc.read().decode("utf-8")
            try:
                parsed = json.loads(raw) if raw else {}
            except Exception:
                parsed = raw
            raise RuntimeError(f"HTTP {exc.code} {path}: {parsed}") from exc


def run_smoke(api_base: str, token: str) -> dict[str, Any]:
    steps: list[Step] = []
    client = ApiClient(api_base, token)
    status_payload: dict[str, Any] = {}

    def step(name: str, fn) -> None:
        try:
            detail = fn()
            steps.append(Step(name=name, ok=True, detail=str(detail)))
        except Exception as exc:
            steps.append(Step(name=name, ok=False, detail=str(exc)))

    step("ready", lambda: client.call("/ready")[0])
    step("auth.me", lambda: client.call("/api/v1/auth/me")[1])

    def _status() -> str:
        nonlocal status_payload
        _, status_payload = client.call("/api/v1/tenant/integrations/status")
        return f"tenant={status_payload.get('tenant_id')}"

    step("integrations.status", _status)

    def _validate() -> str:
        website = status_payload.get("website_live_chat", {})
        whatsapp = status_payload.get("whatsapp_business", {})
        messenger = status_payload.get("facebook_messenger", {})
        instagram = status_payload.get("instagram", {})
        telegram = status_payload.get("telegram", {})
        return json.dumps(
            {
                "website_enabled": bool(website.get("enabled")),
                "whatsapp_enabled": bool(whatsapp.get("enabled")),
                "facebook_enabled": bool(messenger.get("enabled")),
                "instagram_enabled": bool(instagram.get("enabled")),
                "telegram_supported": bool(telegram.get("supported")),
            }
        )

    step("integrations.summary", _validate)

    ok = all(s.ok for s in steps)
    return {
        "api_base": api_base,
        "pass": ok,
        "steps": [s.__dict__ for s in steps],
        "integrations": status_payload,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-check integrations status endpoint")
    parser.add_argument("--api-base", default="http://localhost:8000")
    parser.add_argument("--token", required=True, help="Bearer token value")
    args = parser.parse_args()

    report = run_smoke(args.api_base, args.token)
    print(json.dumps(report, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
