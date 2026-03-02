# Staging Go-Live Checklist - 2026-03-02

## Scope
- Environment: `staging`
- API base: `https://staging-staging-760c.up.railway.app`
- Execution mode: terminal/API-level checklist run (equivalent backend calls used by `tenant-console.html`)
- Run timestamp (UTC): `2026-03-02T16:15:20.8294820+00:00`

## Summary
- Total checks: 17
- Pass: 16
- Fail: 1
- Primary blocker: `frontend/widget-test.html` is still pinned to production API base.

## Checklist Outcomes

### 1) Deploy latest main to staging
- Status: `pass (operational validation)`
- Evidence: staging `/health` returned `{"status":"ok"}` and all core admin/tenant calls succeeded in the same run.
- Note: deploy action itself is done in Railway UI; this run validates deployed environment functionality.

### 2) `tenant-console.html` with staging base

#### Preflight checks (equivalent API checks)
- `GET /health` -> `pass`
- `GET /api/v1/admin/handoff/metrics` -> `pass`
- `GET /api/v1/admin/channels/profiles?limit=5` -> `pass`
- `GET /api/v1/admin/ops/audit?limit=1&offset=0` -> `pass`

#### Staging QA pack (equivalent API flow)
- Social channel account created for seeding -> `pass`
- Seed profile activity via webhook (`POST /api/v1/channels/meta/webhook`) -> `pass` (`processed=1`)
- Handoff generated and visible in queue -> `pass`

#### Onboard -> login -> bot create/patch -> knowledge upload/status
- Onboard (`POST /api/v1/tenant/onboard`) -> `pass`
- Login (`POST /api/v1/auth/login`) -> `pass`
- Bot create (`POST /api/v1/tenant/bots`) -> `pass`
- Bot patch (`PATCH /api/v1/tenant/bots/{id}`) -> `pass`
- Knowledge upload (`POST /api/v1/tenant/knowledge/upload`) -> `pass` (`document_id=d_566528c5f21e`, `chunks=3`)
- Knowledge status (`GET /api/v1/tenant/knowledge/status`) -> `pass` (`documents=1`, `chunks=3`)

#### Handoff queue basic actions
- Queue list (`GET /api/v1/admin/handoff`) -> `pass` (`count=1`)
- Claim (`POST /api/v1/admin/handoff/{id}/claim`) -> `pass`
- Patch (`PATCH /api/v1/admin/handoff/{id}` to `status=open`, `priority=high`) -> `pass`

### 3) Verify widget on staging with `widget-test.html`
- Embed snippet check from staging (`GET /api/v1/tenant/embed/snippet?bot_id=...`) -> `pass`
- `frontend/widget-test.html` staging validation -> `fail`
  - Found: `apiBase: "https://api.staunchbot.com"`
  - Expected: `https://staging-staging-760c.up.railway.app`

## Entities Created During Run
- Tenant ID: `t_stagecheck_1772468112`
- Admin: `stagecheck+1772468112@demo.com`
- Onboarded Bot ID: `bot_20260302161515711903`
- Created/Patch Bot ID: `bot_20260302161517403604`
- Channel Account ID: `ch_20260302161520716992`
- Handoff ID: `ho_91e014019687c6029764ba2c`

## Blockers
1. `frontend/widget-test.html` is hardcoded to production API base and cannot be used as-is for staging verification.

## Recommendation
- Update `frontend/widget-test.html` to support staging API base (query-param override or staging default) and rerun widget verification.
- After widget-test fix, this checklist is green for staging.

## Remaining Major Gap (as noted)
- Expand backend test coverage for handoff/admin flows (integration-style coverage for claim/patch/sweep/ops-audit and channel identity linking paths).
