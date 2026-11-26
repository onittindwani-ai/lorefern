# Vercel

Vercel needs no file from this repo. Follow `docs/06-DEPLOY-VERCEL.md`: set the Root Directory to `apps/web` and set `API_BASE_URL`. Nothing else: the web app never reads `SESSION_SECRET`, which belongs on the API server only.
