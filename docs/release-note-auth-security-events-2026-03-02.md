# Release Note: Auth Security Events (2026-03-02)

## Scope
- Added auth security event observability for password reset workflows.
- Exposed admin endpoint and Setup UI access for recent event review.

## Delivered
- Backend event model:
  - `AuthSecurityEvent` in `backend/app/auth/models.py`
- Auth flow instrumentation in `backend/app/auth/router.py`:
  - `password_forgot` outcomes:
    - `success`, `queued`, `email_error`, `not_found`, `rate_limited`
  - `password_reset` outcomes:
    - `success`, `invalid_token`, `invalid_code`, `rate_limited`
- Admin read endpoint in `backend/app/admin/router.py`:
  - `GET /api/v1/admin/auth/security-events`
  - Filters: `since_hours`, `event_type`, `outcome`, `limit`, `offset`
- Setup UI card in `frontend/tenant-setup.html` + handler in `frontend/scripts/tenant-console-setup.js`:
  - Loads and displays recent auth security events.

## Validation
- Backend tests:
  - `pytest backend/tests/test_auth_password_reset.py -q` -> passed
  - `pytest backend/tests/test_admin_handoff_channels_flows.py -q` -> passed
- Staging auth smoke:
  - `run-auth-smoke.ps1` -> `critical_pass: true`, `pass: true`

## Commits
- `43b9548` Add auth security event logging and admin audit endpoint

## Outcome
- Password reset security events are now auditable from API and visible in Setup/Admin UI for faster incident response and operational review.
