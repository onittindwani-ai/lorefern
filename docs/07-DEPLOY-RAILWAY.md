# Deploy the API and worker on Railway

**Not tested on Railway: no Railway account was used.** The CI workflow on GitHub builds the API image from `apps/api/Dockerfile`; `deploy/railway/railway.json` is checked only for valid syntax. The steps are UNVERIFIED, from general knowledge. Check them against https://docs.railway.com.

1. Create a project and add a **Postgres** database.
2. Add a service from your Git repository. Use `apps/api/Dockerfile` as the build file (the file `railway.json` already says so).
3. In the service Variables tab set `DATABASE_URL` from the Postgres service (use the `postgresql+psycopg://` form), `SESSION_SECRET` (32 or more random characters), `COMPANY_NAME`, `EMAIL_FROM`, `OWNER_EMAIL`, `OWNER_PASSWORD_HASH`, `APPROVER_EMAIL`, `APPROVER_PASSWORD_HASH`, `DEMO_MODE=false`, and `MODE=draft`.
4. Add a **volume** and mount it at `/data/knowledge`. Set `KNOWLEDGE_DIR=/data/knowledge`. Put the company folder there.
5. Add a second service from the same repository for the **worker**, with the start command `python -m lorefern.worker` and the same variables.
6. Run the migrations once from a shell on the API service: `alembic upgrade head`.
7. Set the health check path to `/health` (already in `railway.json`).
8. Put the web app on Vercel (doc 06) or run `apps/web/Dockerfile` as a third service, with `API_BASE_URL` set to the API's internal or public address.

Cost depends on your plan. Read Railway's price page yourself, none is quoted here.
