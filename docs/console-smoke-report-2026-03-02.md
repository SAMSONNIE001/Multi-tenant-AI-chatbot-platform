# Console Smoke Report - 2026-03-02

## Scope
- Environment: `staging`
- API base: `https://staging-staging-760c.up.railway.app`
- Execution mode: API-level smoke run via `frontend/scripts/console_smoke.py`

## Summary
- `critical_pass`: `true`
- `pass`: `true`
- Result: staging console baseline checks passed.

## Steps
1. `health`: pass (`{"status":"ok"}`)
2. `setup.onboard`: pass (`tenant=t_smoke_qw2q9uthhb`)
3. `setup.login_admin_email_only`: pass
4. `setup.auth_me`: pass (`role=admin`)
5. `setup.bots_load`: pass (`200`)
6. `setup.knowledge_status`: pass (`200`)
7. `daily.create_handoff`: pass (`ho_aa2ec7c44f0eb3eea67092f9`)
8. `daily.queue_load`: pass (`200`)
9. `daily.metrics_load`: pass (`200`)
10. `role.register_support`: pass
11. `role.login_support`: pass
12. `role.blocked_advanced_action`: pass (`403`, admin-role guardrail enforced)

## Evidence
- Tenant ID: `t_smoke_qw2q9uthhb`
- Handoff ID: `ho_aa2ec7c44f0eb3eea67092f9`
- Admin email: `admin_m18es9ol@example.com`
- Support email: `support_ym5v1yqf@example.com`

## Command
```powershell
.\.venv\Scripts\python.exe frontend/scripts/console_smoke.py --api-base "https://staging-staging-760c.up.railway.app"
```
