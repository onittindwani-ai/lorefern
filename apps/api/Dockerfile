# Build from the repository root:  docker build -f apps/api/Dockerfile -t lorefern-api .
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY constraints.txt /app/constraints.txt
COPY packages/core-py /app/packages/core-py
COPY apps/api /app/apps/api
COPY data /app/data
RUN pip install --no-cache-dir -c /app/constraints.txt /app/packages/core-py "/app/apps/api[postgres]"
ENV SEED_DIR=/app/data KNOWLEDGE_DIR=/data/knowledge
RUN useradd --create-home --uid 10001 app && mkdir -p /data/knowledge && chown -R app /data
USER app
WORKDIR /app/apps/api
# Only these addresses may say who the visitor is (uvicorn reads FORWARDED_ALLOW_IPS). Compose widens it to the private network that holds the web container.
ENV FORWARDED_ALLOW_IPS=127.0.0.1
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/ready')"
# The healthcheck asks /ready, which reads the database, so an API that cannot reach it is not called healthy.
# Migrations run on start for Postgres, and a failed migration stops the start (set -e) instead of serving a broken schema. SQLite creates its own tables.
CMD ["sh", "-c", "set -e; case \"$DATABASE_URL\" in postgres*) alembic upgrade head;; esac; exec python -m uvicorn lorefern.api.app:app_from_env --factory --host 0.0.0.0 --port 8000 --proxy-headers"]
