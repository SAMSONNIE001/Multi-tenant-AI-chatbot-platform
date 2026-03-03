# Release Note: Production Smoke Green (2026-03-03)

## Scope
- Frontend UX polish across dashboard, operations, setup, and release pages.
- Production API base routing correction (`api.staunchbot.com`).
- Role guardrail verification for advanced actions.

## Environment
- Frontend: `https://www.staunchbot.com`
- API base: `https://api.staunchbot.com`
- Date: 2026-03-03

## Validation Results

### Auth Smoke
Command:

```powershell
.\frontend\scripts\run-auth-smoke.ps1 -ApiBase "https://api.staunchbot.com"
```

Result:
- `critical_pass: true`
- `pass: true`
- Verified login, refresh, logout, revoked-refresh rejection, and support-role forbidden on advanced admin action.

### Console Smoke
Command:

```powershell
.\frontend\scripts\run-console-smoke.ps1 -ApiBase "https://api.staunchbot.com"
```

Result:
- `critical_pass: true`
- `pass: true`
- Verified onboarding, admin login, queue load, metrics load, and support-role block for advanced action.

## Release Decision
- Production baseline is healthy and can be considered frozen at this checkpoint.

## Next Item
- Password-reset email deliverability hardening (SPF/DKIM/DMARC alignment + inbox placement checks).
