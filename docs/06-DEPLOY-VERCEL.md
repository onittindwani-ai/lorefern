# Deploy the web app on Vercel

Vercel hosts only the **web** part. The API and worker need a server that stays on (Railway, Hetzner or any host that runs Docker). **Not tested: no Vercel account was used.** `next build` was run locally and passed.

The Root Directory steps were read from https://vercel.com/docs/monorepos on 2026-11-23 (VERIFIED). The rest is UNVERIFIED.

1. Put the API online first (`07` or `08`) and note its address, such as `https://api.example.com`.
2. In Vercel choose Create New, then Project, and import your Git repository.
3. Press Edit next to Root Directory and choose `apps/web`.
4. If the build cannot find `packages/ui-kit`, look for the setting that includes source files outside the Root Directory and turn it on. UNVERIFIED: the name of that setting was not on the page we read.
5. Framework Next.js. Install command `pnpm install`. Build command `pnpm build`.
6. Set `API_BASE_URL` to your API address with no trailing slash. Set nothing else: the web app never reads `SESSION_SECRET`, and giving it to a third party host would hand over the key that signs owner sessions. It belongs on the API server only.
7. Do not set `INSECURE_COOKIES` or `NEXT_PUBLIC_DEMO_HINT`.
8. Deploy, open the address, sign in.
9. Rate limits and the audit log should see the real visitor, but Vercel has no proxy address you can list (UNVERIFIED: we found no fixed address for its functions). `FORWARDED_ALLOW_IPS` (the Docker image reads it; by hand pass `--proxy-headers --forwarded-allow-ips` to uvicorn) lists the addresses the API trusts to say who the visitor is, so you have three choices:
   - Leave it as it is (`127.0.0.1`). Safe, but every visitor then looks like the same address, so one burst of wrong passwords from anyone uses up the sign in budget of that one shared address and slows sign in for everybody until it refills (the per account limit still holds). Real accounts are not locked.
   - Set `*` only when the API can be reached from nowhere except your web host. Otherwise anyone who can reach the API directly can invent a visitor address and escape the limits. Vercel cannot promise that, so this is not recommended with Vercel.
   - Put the web app on the same server as the API (`08`), where the compose file already lists the private network that holds the web container. This is the recommended way.

## If the build fails

Most often the shared `ui-kit` folder was not included (step 4), or `pnpm-workspace.yaml` does not list `packages/*`. See `15-TROUBLESHOOTING.md`.
