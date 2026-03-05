# Release Rollback Checklist

Use this when a production release introduces regressions and must be reverted quickly.

## Trigger Conditions
- Login failures spike (401/500 increase).
- Password reset or transactional email failures spike.
- Channel integrations fail (website chat, WhatsApp, Facebook Messenger).
- P0/P1 incidents affecting tenant operations.

## Immediate Actions
1. Freeze further deploys.
2. Confirm current production artifact/version and previous known-good commit.
3. Roll back app service to last known-good version.
4. Verify database migrations are backward-safe before rollback.
5. Announce incident + rollback start in ops channel.

## Post-Rollback Verification
1. `GET /health` and `GET /ready` return 200.
2. Admin login works.
3. `GET /api/v1/tenant/integrations/status` returns expected statuses.
4. Website widget sends/receives messages.
5. WhatsApp webhook and Facebook Messenger webhook processing recover.
6. Handoff queue and metrics endpoints return healthy responses.

## Communications
1. Incident update: rollback completed, user impact window, current status.
2. Capture affected release commit hash and rollback target hash.
3. Open follow-up action items for root cause and prevention.

## Exit Criteria
- Critical user journeys pass in production smoke checks.
- Error rate returns to baseline.
- On-call + owner sign-off recorded.
