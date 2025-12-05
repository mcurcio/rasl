"""RASL Web Server - HTTP API and WebSocket metrics streaming.

This package provides a FastAPI-based web server for monitoring and
inspecting the RASL runtime.

Example:
    >>> from rasl.server import create_app, run_server
    >>> from rasl.runtime import Runtime
    >>>
    >>> app = create_app(runtime, plan)
    >>> await run_server(app, port=8080)
"""

from .app import create_app, run_server

__all__ = ["create_app", "run_server"]
