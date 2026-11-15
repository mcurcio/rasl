# The Python runtime (`rasl`) as a container: the engine plus its web UI and GraphQL API.
#
#   docker run -p 8080:8080 -p 5568:5568/udp -v ./conf:/config \
#       -e PUID=1000 -e PGID=1000 -e TZ=America/New_York ghcr.io/mcurcio/rasl
#
# The config lives in the /config volume. The entrypoint (docker/entrypoint.sh) starts as
# root, gives /config to PUID:PGID (default 1000:1000) and runs rasl as that user; UMASK sets
# the mode of the files it creates. If /config/rasl.conf does not exist it writes a starter
# config there, an empty graph, and never overwrites an existing one. With no arguments it
# runs that file with the web UI and API on RASL_PORT (default 8080); arguments replace that
# and go to `rasl` (e.g. `--validate /config/rasl.conf`). HEALTHCHECK asks GET /health,
# which fails when the graph stops ticking. The config is reloaded when its files change
# (the watcher polls their modification time, so it also sees edits made on an NFS server).

ARG PYTHON_VERSION=3.11

FROM ghcr.io/astral-sh/uv:0.11.32 AS uv

FROM python:${PYTHON_VERSION}-slim-bookworm AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/rasl
WORKDIR /src
# Dependencies first, so a source change reuses this layer
COPY pyproject.toml uv.lock README.md LICENSE ./
RUN uv sync --locked --no-dev --no-install-project
COPY src ./src
RUN uv sync --locked --no-dev --no-editable

FROM python:${PYTHON_VERSION}-slim-bookworm
# Set by the image workflow; "dev" and "unknown" on a local build
ARG VERSION=dev
ARG REVISION=unknown
LABEL org.opencontainers.image.title="rasl" \
      org.opencontainers.image.description="Real-time Async Streaming for Lighting: a DMX/sACN processing engine with a web UI" \
      org.opencontainers.image.source="https://github.com/mcurcio/rasl" \
      org.opencontainers.image.url="https://github.com/mcurcio/rasl" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.revision="${REVISION}" \
      org.opencontainers.image.licenses="MIT"
COPY --from=build /opt/rasl /opt/rasl
COPY docker/rasl.conf /usr/share/rasl/rasl.conf
COPY --chmod=755 docker/entrypoint.sh /usr/local/bin/rasl-entrypoint
COPY --chmod=755 docker/healthcheck.py /usr/local/bin/rasl-healthcheck
# PUID and PGID default to 1000 in the entrypoint, not here, so it can tell when they
# were set and say they do nothing for a container started as another user
ENV PATH=/opt/rasl/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    UMASK=022 \
    RASL_PORT=8080
# Owned by the default PUID:PGID, so a new named volume (which copies this directory's
# ownership) is writable even before the entrypoint changes its owner
RUN mkdir /config && chown 1000:1000 /config
# No USER: the entrypoint starts as root only to set the owner of /config, then runs rasl
# as PUID:PGID. Started as another user (docker --user, Kubernetes runAsUser), it runs as
# that user.
WORKDIR /config
VOLUME /config
# 8080: web UI and API (RASL_PORT). 5568/udp: sACN (E1.31).
EXPOSE 8080 5568/udp
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 CMD ["rasl-healthcheck"]
ENTRYPOINT ["rasl-entrypoint"]
