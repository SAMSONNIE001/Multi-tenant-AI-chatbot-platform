# Production Deployment Notes

## Runtime
- Run app behind a reverse proxy (Nginx/Caddy).
- Enable TLS certificates and HTTP to HTTPS redirect at the edge.
- Keep HSTS at the edge (`Strict-Transport-Security`).

## App Server
- Docker image runs Gunicorn + Uvicorn workers by default.
- Control workers via `GUNICORN_WORKERS`.

## Health Probes
- Liveness: `GET /health`
- Readiness: `GET /ready` (checks DB connectivity)

## Database Pool
- Tune via env:
  - `DB_POOL_SIZE`
  - `DB_MAX_OVERFLOW`
  - `DB_POOL_TIMEOUT`
  - `DB_POOL_RECYCLE`

## Reverse Proxy
- Start from `deploy/nginx.conf.example`.
