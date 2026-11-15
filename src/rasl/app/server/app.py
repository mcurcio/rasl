"""FastAPI application for RASL web interface."""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import TYPE_CHECKING

import structlog
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from strawberry.fastapi import GraphQLRouter

from rasl.app.server.graphql_api import RASLContext, schema
from rasl.app.server.health import HealthStatus
from rasl.app.server.state import AppState

if TYPE_CHECKING:
    from rasl.config import ConfigSession
    from rasl.graph import ExecutionPlan
    from rasl.runtime import Runtime

logger = structlog.get_logger()


def health_response(state: AppState) -> JSONResponse:
    """The ``GET /health`` response: the health report as JSON.

    Returns:
        Status 503 when the report is ``stalled``, so a container health check marks
        the container unhealthy; 200 for ``ok`` and ``degraded``.
    """
    report = state.health()
    body = dataclasses.asdict(report)
    body["status"] = report.status.value
    body["disabled_nodes"] = list(report.disabled_nodes)
    code = 503 if report.status is HealthStatus.STALLED else 200
    return JSONResponse(body, status_code=code)


def create_app(
    runtime: "Runtime",
    plan: "ExecutionPlan",
    session: "ConfigSession | None" = None,
) -> FastAPI:
    """Create the RASL FastAPI application.
    
    Args:
        runtime: The running runtime, for metrics access.
        plan: The ExecutionPlan for graph structure.
        session: The config session when the config is watched, so health can report
            the last reload; None when it is not.
    
    Returns:
        Configured FastAPI application, serving ``GET /health``, ``/graphql`` and the UI.
    """
    app = FastAPI(
        title="RASL",
        description="Real-time Async Streaming for Lighting",
        version="0.1.0",
        # No generated API pages: they are unauthenticated, /docs loads its assets
        # from a CDN, and they do not document the GraphQL API (docs/web-api.md does)
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    
    # Store state in app.state (no globals!)
    app.state.rasl = AppState(runtime=runtime, plan=plan, session=session)

    @app.get("/health")
    async def health() -> JSONResponse:
        """Server health; 503 when the graph has stalled (see ``health_response``)."""
        return health_response(app.state.rasl)

    async def get_context() -> RASLContext:
        return RASLContext(state=app.state.rasl)

    graphql_app = GraphQLRouter(
        schema,
        context_getter=get_context,
        subscription_protocols=("graphql-transport-ws",),
    )
    app.include_router(graphql_app, prefix="/graphql")

    # The dashboard ships inside the package, in rasl/app/ui
    ui_dir = Path(__file__).resolve().parents[1] / "ui"
    if ui_dir.is_dir():
        app.mount("/", StaticFiles(directory=str(ui_dir), html=True), name="ui")

    return app


async def run_server(
    app: FastAPI,
    host: str = "127.0.0.1",
    port: int = 8080,
) -> None:
    """Run the API server.
    
    This is a convenience function for running the server programmatically.
    In production, use uvicorn directly.
    
    Args:
        app: The FastAPI application.
        host: Host to bind to.
        port: Port to bind to.
    """
    import uvicorn
    
    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="warning",  # Reduce uvicorn noise
        # The app has no startup or shutdown handlers, and uvicorn's lifespan
        # task logs a traceback when the server is cancelled on shutdown
        lifespan="off",
    )
    server = uvicorn.Server(config)
    await server.serve()
