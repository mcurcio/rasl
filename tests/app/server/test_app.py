"""The web app: which routes it serves."""

from __future__ import annotations

from rasl.app.server.app import create_app
from rasl.config.build import parse_config
from rasl.runtime import Runtime

CONFIG = """
graph {
    node ConsoleSink sink { fps 1; }
}
"""


def _paths() -> set[str]:
    plan = parse_config(CONFIG)
    app = create_app(Runtime(plan), plan)
    return {getattr(route, "path", "") for route in app.routes}


def test_health_and_graphql_are_served() -> None:
    assert {"/health", "/graphql"} <= _paths()


def test_fastapis_generated_api_pages_are_off() -> None:
    # They are unauthenticated, load assets from a CDN, and do not document GraphQL
    assert not {"/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"} & _paths()
