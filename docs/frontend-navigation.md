# Frontend Navigation Guide

## Entry Points
1. Default entry: `/index.html`  
   Redirects to `/dashboard.html`.
2. Main dashboard: `/dashboard.html`  
   Human-facing tenant snapshot and login.
3. Daily operations console: `/tenant-console.html`  
   Ops and staging QA workflows.
4. Setup/admin console: `/tenant-setup.html`  
   Tenant onboarding and setup-heavy actions.
5. Release checklist: `/release-checklist.html`  
   Release gate checks and manual promotion/smoke sign-off.

## Role Behavior
1. UI role mode defaults to `Operator`.
2. `Admin` mode can reveal advanced actions.
3. Backend guardrails still enforce safety:
   Advanced actions require admin-level role checks server-side.

## Login Behavior
1. Primary login is `email + password`.
2. If email belongs to multiple tenants, UI reveals Tenant ID fallback.
3. Retry with `email + password + tenant_id`.

## Smoke Verification
Run API-level console smoke checks:

```powershell
.\frontend\scripts\run-console-smoke.ps1 -ApiBase "<api-base-url>"
```

Example:

```powershell
.\frontend\scripts\run-console-smoke.ps1 -ApiBase "https://staging-staging-760c.up.railway.app"
```

## Recommended Daily Use
1. Start at dashboard (`/dashboard.html`) for high-level status.
2. Move to daily ops (`/tenant-console.html`) for queue and QA checks.
3. Use setup console (`/tenant-setup.html`) only for onboarding/configuration work.
4. Use release checklist (`/release-checklist.html`) before/after production promotion.
