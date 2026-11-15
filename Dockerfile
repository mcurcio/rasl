# The Python runtime (`rasl`) as a container: the engine plus its web UI and GraphQL API.
#
#   docker run -p 8080:8080 -p 5568:5568/udp -v ./conf:/config ghcr.io/mcurcio/rasl \
#       /config/rasl.conf --api-host 0.0.0.0 --api-port 8080
#
# The image carries no config: the entrypoint is `rasl`, and the config path and flags are
# the arguments. The config is reloaded when its files change (the watcher polls their
# modification time, so it also sees edits made on an NFS server).

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
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-dev --no-install-project
COPY src ./src
RUN uv sync --locked --no-dev --no-editable

FROM python:${PYTHON_VERSION}-slim-bookworm
COPY --from=build /opt/rasl /opt/rasl
ENV PATH=/opt/rasl/bin:$PATH \
    PYTHONUNBUFFERED=1
# A numeric non-root user, so Kubernetes can verify runAsNonRoot
USER 65534:65534
WORKDIR /config
# 8080: web UI and API (when run with --api-port 8080). 5568/udp: sACN (E1.31).
EXPOSE 8080 5568/udp
ENTRYPOINT ["rasl"]
