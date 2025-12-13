"""FastAPI application for RASL web interface."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import structlog
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from strawberry.fastapi import GraphQLRouter

from .state import AppState
from .graphql_api import RASLContext, schema

if TYPE_CHECKING:
    from rasl.engine.graph import ExecutionPlan
    from rasl.runtime import Runtime

logger = structlog.get_logger()


def create_app(runtime: "Runtime", plan: "ExecutionPlan") -> FastAPI:
    """Create the RASL FastAPI application.
    
    Args:
        runtime: The active Runtime instance for metrics access.
        plan: The ExecutionPlan for graph structure.
    
    Returns:
        Configured FastAPI application.
    """
    app = FastAPI(
        title="RASL",
        description="Real-time Async Streaming for Lighting",
        version="0.1.0",
    )
    
    # Store state in app.state (no globals!)
    app.state.rasl = AppState(runtime=runtime, plan=plan)

    async def get_context() -> RASLContext:
        return RASLContext(state=app.state.rasl)

    graphql_app = GraphQLRouter(
        schema,
        context_getter=get_context,
        subscription_protocols=("graphql-transport-ws",),
    )
    app.include_router(graphql_app, prefix="/graphql")

    ui_dir_candidates = [
        # Preferred: packaged UI under src/rasl/ui
        Path(__file__).resolve().parents[1] / "ui",
        # Backward-compatible: repo-root ui/ (during migration)
        Path(__file__).resolve().parents[3] / "ui",
    ]

    for ui_dir in ui_dir_candidates:
        if ui_dir.exists() and ui_dir.is_dir():
            app.mount("/", StaticFiles(directory=str(ui_dir), html=True), name="ui")
            break

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
    )
    server = uvicorn.Server(config)
    await server.serve()
