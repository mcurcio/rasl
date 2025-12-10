"""RASL Web Server - HTTP API and WebSocket metrics streaming.

This package provides a FastAPI-based web server for monitoring and
inspecting the RASL runtime.

Components:
    - AppState: Application state class (no globals)
    - create_app: Factory function to create the FastAPI app
    - run_server: Convenience function to run the server

Example:
    >>> from rasl.server import create_app, run_server
    >>> from rasl.runtime import Runtime
    >>>
    >>> app = create_app(runtime, plan)
    >>> await run_server(app, port=8080)
"""

from .app import create_app, run_server
from .state import AppState

__all__ = ["AppState", "create_app", "run_server"]
