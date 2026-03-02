# Release Note: Backend Timezone Cleanup (2026-03-02)

## Scope
- Standardized backend UTC timestamp handling and removed deprecated `datetime.utcnow()` usage in active admin/handoff/auth/channel/embed/system/tenant paths.
- Updated RAG schema config style to modern Pydantic v2 pattern.

## Delivered
- Replaced runtime timestamp creation with `datetime.now(timezone.utc)` in touched backend modules.
- Updated affected datetime imports to include `timezone`.
- Migrated `backend/app/rag/schemas.py` from `class Config` to `ConfigDict(from_attributes=True)`.
- Hardened handoff SLA comparison logic to safely normalize naive/aware datetimes before comparing.

## Validation
- Local backend test in venv:
  - `.\.venv\Scripts\python.exe -m pytest backend/tests/test_admin_handoff_channels_flows.py -q`
  - Result: `5 passed`
- Staging smoke:
  - `.\frontend\scripts\run-console-smoke.ps1 -ApiBase "https://staging-staging-760c.up.railway.app"`
  - Result: `critical_pass: true`, `pass: true`
- Manual staging UI checks passed:
  - Escalation metrics load
  - Escalation sweep run
  - Release checklist checks

## Commit
- `b52e03e` Migrate backend utcnow usage and update rag schemas config

## Outcome
- Backend time handling is now consistent for changed operational paths and validated on staging without regression.
