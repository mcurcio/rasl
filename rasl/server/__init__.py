"""
Web server and API components for RASL.

Provides REST/WebSocket APIs and serves the built-in web UI
for monitoring and controlling RASL applications.
"""

from .app import create_web_app

__all__ = ["create_web_app"]
