# Go-Live Checklist

## Pre-Deploy
- Confirm `main` contains the approved release commit.
- Confirm production frontend base URL is `https://www.staunchbot.com`.
- Confirm production API base URL is `https://api.staunchbot.com`.
- Confirm staging API base URL is `https://multi-tenant-ai-chatbot-platform-staging.up.railway.app`.

## Automated Gate
- Run:
```powershell
.\frontend\scripts\run-release-gate.ps1
```
- Required outcome: all steps pass for both production and staging.

## Manual Product Checks
- Auth: sign up, login, logout, forgot password, reset password.
- Integrations: status loads and channel cards show user-friendly messages.
- Unified Inbox: queue loads and handoff actions work.
- Knowledge Base: upload, status, and reindex all succeed.
- Profile and Settings pages render correctly on desktop and mobile.

## Production Safety
- Verify dev-only controls are hidden on production host.
- Verify release checklist page is not accessible on production navigation.
- Verify no demo credentials are prefilled in forms.

## Post-Deploy
- Validate key endpoints return `200`:
  - `/ready`
  - `/api/v1/auth/me`
  - `/api/v1/tenant/integrations/status`
  - `/api/v1/tenant/knowledge/status`
  - `/api/v1/admin/handoff/metrics`
- Run one live message through Website Chat and verify it appears in Unified Inbox.

## Rollback Trigger
- Roll back immediately if auth/login fails, integrations status errors at scale, or inbox workflow is blocked.
