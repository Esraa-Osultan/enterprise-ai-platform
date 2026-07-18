# --- Build stage -----------------------------------------------------------
# build-essential is only needed to compile wheels for faiss/PyMuPDF; it has
# no reason to exist in the final image (previously it did, since everything
# was installed in one stage -- that's dead weight on every deploy/pull).
FROM python:3.11-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# --- Runtime stage -----------------------------------------------------------
FROM python:3.11-slim AS runtime

WORKDIR /app

# Run as an unprivileged user. The previous image ran as root with no
# USER directive -- fine for a quick demo, a real gap for anything
# internet-facing: a container escape or an RCE in a dependency gets
# root in the container for free otherwise.
RUN groupadd --system app && useradd --system --gid app --home-dir /app app

COPY --from=builder /root/.local /home/app/.local
COPY app ./app

# Intentionally NOT copying .env / .env.example into the image. Baking
# `JWT_SECRET_KEY=change-this-secret-in-production` (the default in
# .env.example) into every image built from this Dockerfile means anyone
# who forgets to override it at runtime is using a publicly-known secret
# capable of forging auth tokens. Configuration is supplied at run time via
# `env_file`/`environment` in docker-compose.yml or `-e` flags, same as any
# 12-factor deployment.
RUN mkdir -p data/uploads data/vector_store && chown -R app:app /app

USER app
ENV PATH=/home/app/.local/bin:$PATH \
    PYTHONUNBUFFERED=1

EXPOSE 8000

# Matches GET /health (app/api/health.py). Lets an orchestrator (compose,
# Kubernetes, ECS) detect a hung/unresponsive process instead of routing
# traffic to it forever -- there was no HEALTHCHECK at all before this.
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=2)" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
