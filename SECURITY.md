# Security policy

## Reporting a vulnerability

Please do not put the details of a security problem in a public issue.

This repository has no private reporting channel yet: GitHub's private vulnerability reporting is turned off,
and no security contact address has been published. To report a problem, open an issue that says you have a
security report and asks for a private way to send it. Leave out what the problem is and how to trigger it.
The maintainer will reply with a private channel.

Please include what an attacker can do, the version (`rasl --version`) or image tag you tested, and the steps or
config that show the problem.

## What is in scope

- The Python runtime in `src/rasl/`: the `rasl` command, the config loader, the nodes and device drivers, and the
  web server (the dashboard, `/graphql` and `GET /health`).
- The container image `ghcr.io/mcurcio/rasl`, built from the `Dockerfile` and `docker/`.

The JavaScript workspace (`js/`) and the Rust experiment (`v2/`) are not published and are out of scope.

## Supported versions

rasl has no versioned releases yet. Fixes go to the `alpha` branch, and the next image built from it
(`ghcr.io/mcurcio/rasl:sha-<commit>`) carries them. Older images are not patched.

## Things to know before you deploy

These are how rasl works today, not vulnerabilities:

- The web server has no authentication. Anyone who can reach its port can read the graph (node names, types, ports and
  connections), its metrics and the last config error through the dashboard, `/graphql` and `/health`. The API is read-only: it has no mutations, and the graph changes
  only when its config files change.
- Outside the container, the web server listens on `127.0.0.1` unless `--api-host` (with `--api-port`) or the
  `ui` block's `host` says otherwise. The container's
  default command passes `--api-host 0.0.0.0`, so it listens on every interface of the container.
- sACN input (`SacnSource`) listens on UDP port 5568 on `0.0.0.0` by default and accepts data from any sender, as
  the protocol does.
- The dashboard loads two scripts in the browser from third-party CDNs: cytoscape from `cdn.jsdelivr.net` and
  graphql-ws from `unpkg.com`.

Keep rasl on a trusted network, or put it behind a proxy that checks who is signing in.
