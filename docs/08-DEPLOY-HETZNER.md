# Deploy on a Hetzner server

**Not tested on a real server: no Hetzner server was created.** The CI workflow on GitHub builds the Docker images and starts the compose stack (the API and the web app must answer), nothing more; I did not run Docker on my own machine for this version. The steps below are UNVERIFIED, from our general knowledge. Check them against https://docs.hetzner.com. One small server runs everything with Docker Compose and Caddy, which gets an HTTPS certificate for you.

1. Make a server (Ubuntu LTS is fine). Add your SSH key while creating it.
2. Add a firewall that allows only ports 22, 80 and 443.
3. Point one DNS name at the server, for the web app. The API is not published: the web app reaches it inside the compose network. (Only if the web app runs on Vercel, `06`, the API needs a name of its own: uncomment the second block in the Caddyfile.)
4. Optional: paste `deploy/hetzner/cloud-init.yaml` into the cloud config box. It installs Docker and Caddy and holds no secrets. Do not add any.
5. Log in with SSH and clone your repository to `/opt/lorefern`.
6. `cp .env.example .env` and fill it in (see `04`). The Docker path needs these four, or the API will not start:
   - `DEMO_MODE=false`
   - `SESSION_SECRET`: a random value of 32 or more characters, `python3 -c "import secrets; print(secrets.token_urlsafe(48))"`
   - `OWNER_PASSWORD_HASH`: made on the computer where you ran `make install` with `.venv/bin/python tools/hash_password.py` (the server has no Python environment and needs none: the tools are not in the Docker image), pasted in single quotes
   - `POSTGRES_PASSWORD`: letters and digits only, or percent encoded, because it sits inside the database address: `openssl rand -hex 24`

   Also set `COMPANY_NAME`, `EMAIL_FROM` and `TIMEZONE` before `MODE=live`. Put your DNS name in `deploy/hetzner/Caddyfile`.
7. `docker compose up -d --build`. The API runs the database migrations itself when it starts; `docker compose exec api alembic upgrade head` is only needed to run them by hand.
8. Copy the Caddyfile to `/etc/caddy/Caddyfile` and `sudo systemctl reload caddy`.
9. Put the company folder in the `knowledge` volume, for example from the server's shell: `docker compose cp ./my-company-folder/. api:/data/knowledge/` (UNVERIFIED: Docker was not run for these steps). The worker uses the same volume. Then open the web address, sign in, add a folder source on the Sources page whose path is the folder's name (paths are relative to `/data/knowledge`), and press Read.

## Backups

`deploy/hetzner/backup.sh` writes a compressed Postgres dump and a copy of the knowledge volume to `/var/backups/lorefern` (`BACKUP_DIR` changes it, `BACKUP_COPY_TO` copies the files to another machine, which a real backup needs). A failed or empty dump is never kept as a backup. Run it daily with cron: `0 3 * * * /opt/lorefern/deploy/hetzner/backup.sh` (it works from cron's own folder). Test a restore (see `11`) before you need it.
