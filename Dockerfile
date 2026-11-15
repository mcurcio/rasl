# The Python runtime (`rasl`) as a container: the engine plus its web UI and GraphQL API.
#
#   docker run -p 8080:8080 -p 5568:5568/udp -v ./conf:/config ghcr.io/mcurcio/rasl
#
# The config lives in the /config volume. On start, if /config/rasl.conf does not exist, the
# entrypoint (docker/entrypoint.sh) writes a starter config there, an empty graph, and never
# overwrites an existing one. The default command runs that file with the web UI and API on
# port 8080; arguments replace it and go to `rasl` (e.g. `--validate /config/rasl.conf`).
# The config is reloaded when its files change (the watcher polls their modification time,
# so it also sees edits made on an NFS server).

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
COPY docker/rasl.conf /usr/share/rasl/rasl.conf
COPY --chmod=755 docker/entrypoint.sh /usr/local/bin/rasl-entrypoint
ENV PATH=/opt/rasl/bin:$PATH \
    PYTHONUNBUFFERED=1
# Owned by the runtime user, so a new named volume (which copies this directory's ownership)
# is writable and the entrypoint can seed it
RUN mkdir /config && chown 65534:65534 /config
# A numeric non-root user, so Kubernetes can verify runAsNonRoot
USER 65534:65534
WORKDIR /config
VOLUME /config
# 8080: web UI and API. 5568/udp: sACN (E1.31).
EXPOSE 8080 5568/udp
ENTRYPOINT ["rasl-entrypoint"]
CMD ["/config/rasl.conf", "--api-host", "0.0.0.0", "--api-port", "8080"]
