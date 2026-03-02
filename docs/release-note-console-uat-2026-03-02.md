# Console UAT Release Note - 2026-03-02

## Scope
- Environment: `staging`
- API base: `https://staging-staging-760c.up.railway.app`
- Run timestamp (UTC): `2026-03-02T18:00:40.0679280Z`
- Validation mode: API-level execution equivalent to tenant-console UAT pack.

## Summary
- `critical_pass`: `true`
- `pass`: `true`
- Result: staging is ready for manual production promotion.

## Check Results
1. `health`: pass (`ok`)
2. `onboard`: pass (`tenant=t_uat_1772474434`)
3. `login`: pass
4. `preflight_handoff_metrics`: pass
5. `preflight_profiles`: pass
6. `preflight_ops_audit`: pass
7. `seed_channel_account` (non-critical): pass (`ch_20260302180039392790`)
8. `seed_profile_activity`: pass (`processed=1`)
9. `handoff_queue_basic`: pass (`count=1`)
10. `handoff_claim`: pass
11. `handoff_patch`: pass (`status=open`, `priority=high`)
12. `setup_bots_load`: pass
13. `setup_knowledge_status`: pass

## Evidence IDs
- Tenant ID: `t_uat_1772474434`
- Channel Account ID: `ch_20260302180039392790`

## Blockers
- None.

## Promotion Decision
- Proceed with manual promotion to production using the same commit currently validated on staging.
