# Deploy on a Hetzner server

**Not tested on a real server: no Hetzner server was created.** The CI workflow on GitHub builds the Docker images and starts the compose stack (the API and the web app must answer), nothing more; I did not run Docker on my own machine for this version. The steps below are UNVERIFIED, from our general knowledge. Check them against https://docs.hetzner.com. One small server runs everything with Docker Compose and Caddy, which gets an HTTPS certificate for you.

1. Make a server (Ubuntu LTS is fine). Add your SSH key while creating it.
2. Add a firewall that allows only ports 22, 80 and 443.
3. Point two DNS names at the server: one for the web app and one for the API.
4. Optional: paste `deploy/hetzner/cloud-init.yaml` into the cloud config box. It installs Docker and Caddy and holds no secrets. Do not add any.
5. Log in with SSH and clone your repository to `/opt/lorefern`.
6. `cp .env.example .env` and fill it in (see `04`). The Docker path needs these four, or the API will not start:
   - `DEMO_MODE=false`
   - `SESSION_SECRET`: a random value of 32 or more characters, `python3 -c "import secrets; print(secrets.token_urlsafe(48))"`
   - `OWNER_PASSWORD_HASH`: from `python3 tools/hash_password.py`, in single quotes
   - `POSTGRES_PASSWORD`: letters and digits only, or percent encoded, because it sits inside the database address: `openssl rand -hex 24`

   Also set `COMPANY_NAME`, `EMAIL_FROM` and `TIMEZONE` before `MODE=live`. Put your two DNS names in `deploy/hetzner/Caddyfile`.
7. `docker compose up -d --build`. The API runs the database migrations itself when it starts; `docker compose exec api alembic upgrade head` is only needed to run them by hand.
8. Copy the Caddyfile to `/etc/caddy/Caddyfile` and `sudo systemctl reload caddy`.
9. Put the company folder in the `knowledge` volume, then open the web address, sign in and press Read again on the Sources page.

## Backups

`deploy/hetzner/backup.sh` writes a compressed Postgres dump and a copy of the knowledge volume to `/var/backups/lorefern` (`BACKUP_DIR` changes it, `BACKUP_COPY_TO` copies the files to another machine, which a real backup needs). A failed or empty dump is never kept as a backup. Run it daily with cron: `0 3 * * * /opt/lorefern/deploy/hetzner/backup.sh` (it works from cron's own folder). Test a restore (see `11`) before you need it.
