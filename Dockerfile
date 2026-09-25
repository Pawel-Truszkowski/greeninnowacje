FROM python:3.14-slim

COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /usr/local/bin/uv

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# tzdata: slim images ship no timezone database, and without it TZ is ignored — the
# scheduler would run on UTC and drift by an hour twice a year.
# supercronic: a cron built for containers (inherits the environment, logs to stdout).
# Version and checksum are pinned: a build step that downloads a binary is part of the
# supply chain, and an unpinned one makes images non-reproducible.
ARG SUPERCRONIC_VERSION=v0.2.49
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata curl ca-certificates \
    && arch="$(dpkg --print-architecture)" \
    && case "$arch" in \
         amd64) sha1=e63c11a9726b775a6a11801e81af4f3fb926aa68 ;; \
         arm64) sha1=0b6c5bb743e0b0dafed1132198c81807927ac413 ;; \
         *) echo "Unsupported architecture: $arch" && exit 1 ;; \
       esac \
    && curl -fsSLo /usr/local/bin/supercronic \
       "https://github.com/aptible/supercronic/releases/download/${SUPERCRONIC_VERSION}/supercronic-linux-${arch}" \
    && echo "${sha1}  /usr/local/bin/supercronic" | sha1sum -c - \
    && chmod +x /usr/local/bin/supercronic \
    && apt-get purge -y curl && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

# Dependencies first — this layer stays cached until uv.lock changes.
COPY pyproject.toml uv.lock ./
ARG UV_SYNC_ARGS="--no-dev"
RUN uv sync --locked --no-install-project $UV_SYNC_ARGS

COPY . .

# The directory must exist in the image before the volume is created: an empty named
# volume inherits content and ownership from this path, and a root-owned one would make
# collectstatic fail for the unprivileged user.
RUN mkdir -p /app/staticfiles \
    && useradd --create-home --uid 1000 app \
    && chown -R app /app
USER app

EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
