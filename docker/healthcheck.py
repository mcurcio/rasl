#!/usr/bin/env python3
"""Container health check: exit 0 if rasl's GET /health answers 200, else 1.

The port comes from RASL_PORT (default 8080), the same variable the entrypoint's default
command uses. /health answers 503 when the graph has rate-driving sinks but has stopped
ticking, and 200 when it is ok or only degraded (see rasl.app.server.health).
"""

from __future__ import annotations

import os
import sys
import urllib.error
import urllib.request


def main() -> int:
    """Ask the local server for its health; return the exit code."""
    url = f"http://127.0.0.1:{os.environ.get('RASL_PORT', '8080')}/health"
    try:
        with urllib.request.urlopen(url, timeout=4) as response:
            return 0 if response.status == 200 else 1
    except urllib.error.HTTPError as error:
        print(f"rasl-healthcheck: {url} answered {error.code}", file=sys.stderr)
    except OSError as error:
        print(f"rasl-healthcheck: {url}: {error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
