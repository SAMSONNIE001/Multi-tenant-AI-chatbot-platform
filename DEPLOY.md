# Deployment (Staging -> Production)

## Required env vars
- ENV=prod
- DATABASE_URL=postgresql+psycopg://...
- JWT_SECRET=...
- OPENAI_API_KEY=...
- CORS_ORIGINS=https://your-frontend.com

## Docker local test (prod-like)
1) Create a `.env.prod` file (DO NOT COMMIT)
2) Run:
   `docker compose -f docker-compose.prod.yml --env-file .env.prod up --build`

## Railway (recommended first deploy)
1) Create a new Railway project
2) Add a PostgreSQL plugin (managed DB)
3) Set the env vars above in Railway
4) Deploy from GitHub (Railway will build from Dockerfile)
5) Run migrations automatically (Docker CMD runs `alembic upgrade head`)

## Health endpoints
- /health
- /ready
