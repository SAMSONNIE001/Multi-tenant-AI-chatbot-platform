# Release Note: Session Hardening + Auth Smoke (2026-03-02)

## Scope
- Hardened frontend session/token handling.
- Added explicit session-expired UX across frontend surfaces.
- Added auth-focused smoke test coverage.

## Delivered
- Switched auth token persistence from `localStorage` to `sessionStorage` (with backward-compatible migration cleanup) in:
  - `frontend/scripts/dashboard.js`
  - `frontend/scripts/tenant-console-api.js`
  - `frontend/scripts/tenant-console-setup.js`
  - `frontend/scripts/release-checklist.js`
- Added session-expired UX behavior on `401` responses:
  - clears active token
  - sets short-lived session-expired flag
  - renders clear “Session expired. Please sign in again.” message
- Added auth smoke runner:
  - `frontend/scripts/auth_smoke.py`
  - `frontend/scripts/run-auth-smoke.ps1`
- Added refresh endpoint robustness fix for timezone-safe comparison:
  - `backend/app/auth/router.py`

## Validation
- Frontend checks:
  - `python frontend/scripts/check_frontend.py` -> OK
  - JS syntax checks for updated frontend scripts -> OK
- Backend tests:
  - `pytest backend/tests/test_tenant_smoke.py backend/tests/test_auth_password_reset.py -q` -> `4 passed`
- Staging smoke (provided by operator):
  - `run-console-smoke.ps1` -> `critical_pass: true`, `pass: true`
  - `run-auth-smoke.ps1` -> `critical_pass: true`, `pass: true`
    - verified: login, refresh, logout, support forbidden advanced action

## Commits
- `dc7caff` Harden frontend session handling and add auth smoke checks

## Outcome
- Session handling is now safer by default, expiry behavior is explicit for operators, and auth lifecycle checks are automated and passing on staging.
