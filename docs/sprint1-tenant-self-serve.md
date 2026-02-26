# Sprint 1: Tenant Self-Serve API

New router prefix: `/api/v1/tenant`

## 1) Onboard tenant + admin + default bot

`POST /api/v1/tenant/onboard`

Example:

```json
{
  "tenant_name": "Acme Support",
  "admin_email": "admin@acme.com",
  "admin_password": "StrongPass123",
  "compliance_level": "standard",
  "bot_name": "Acme Website Bot",
  "allowed_origins": ["https://acme.com"]
}
```

Returns:
- tenant
- admin
- default `bot_id`
- default `bot_api_key`
- auth tokens

## 2) Bot management

- `GET /api/v1/tenant/bots`
- `POST /api/v1/tenant/bots`
- `PATCH /api/v1/tenant/bots/{bot_id}`
- `POST /api/v1/tenant/bots/{bot_id}/rotate-key`

Requires bearer token (admin login/onboard token).

## 3) Knowledge management

- `POST /api/v1/tenant/knowledge/upload` (multipart file)
- `POST /api/v1/tenant/knowledge/reindex`
- `GET /api/v1/tenant/knowledge/status`

## 4) Embed snippet

`GET /api/v1/tenant/embed/snippet?bot_id=...`

Returns a copy-paste HTML snippet configured with tenant bot id.

## Suggested verification flow

1. Call `/api/v1/tenant/onboard`
2. Authorize Swagger with returned access token
3. Call `/api/v1/tenant/knowledge/upload`
4. Call `/api/v1/tenant/knowledge/status`
5. Call `/api/v1/tenant/embed/snippet?bot_id=...`
