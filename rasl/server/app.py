"""
Main web application factory for RASL server.

Creates FastAPI application with all routes, middleware, and
WebSocket endpoints for the RASL monitoring interface.
"""

import logging
from typing import Callable, Optional

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from rasl.config import Config
from rasl.core.engine import Engine
from rasl.core.monitor import NodeMonitor

from .routes import graph, nodes, monitoring, websocket
from .middleware.cors import add_cors_middleware

logger = logging.getLogger(__name__)


def create_web_app(
    engine_provider: Callable[[], Optional[Engine]],
    monitor: NodeMonitor,
    config: Config
) -> FastAPI:
    """
    Create the main RASL web application.
    
    Args:
        engine_provider: Function that returns current engine instance
        monitor: Node monitor for health/performance data
        config: Application configuration
        
    Returns:
        Configured FastAPI application
    """
    
    # Create FastAPI app
    app = FastAPI(
        title="RASL - Real-Time Animation Show Library",
        description="Web interface for RASL animation control and monitoring",
        version="0.1.0",
        docs_url="/api/docs" if config.debug_mode else None,
        redoc_url="/api/redoc" if config.debug_mode else None
    )
    
    # Add middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if config.debug_mode else ["http://localhost:8080"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Store dependencies in app state
    app.state.engine_provider = engine_provider
    app.state.monitor = monitor
    app.state.config = config
    
    # Include API routes
    app.include_router(
        graph.router,
        prefix="/api/v1/graph",
        tags=["graph"]
    )
    
    app.include_router(
        nodes.router,
        prefix="/api/v1/nodes",
        tags=["nodes"]
    )
    
    app.include_router(
        monitoring.router,
        prefix="/api/v1/monitoring",
        tags=["monitoring"]
    )
    
    app.include_router(
        websocket.router,
        prefix="/api/v1/ws",
        tags=["websocket"]
    )
    
    # Health check endpoint
    @app.get("/api/health")
    async def health_check():
        """Simple health check endpoint."""
        engine = engine_provider()
        return {
            "status": "healthy",
            "engine_running": engine is not None and engine._running if engine else False,
            "version": "0.1.0"
        }
    
    # Serve static UI files (in production, these would be embedded)
    try:
        from pathlib import Path
        ui_dist_path = Path(__file__).parent.parent / "ui" / "dist"
        if ui_dist_path.exists():
            app.mount("/", StaticFiles(directory=str(ui_dist_path), html=True), name="ui")
        else:
            logger.warning(f"UI dist directory not found: {ui_dist_path}")
            
            # Fallback: serve a simple HTML page
            @app.get("/")
            async def root():
                return {
                    "message": "RASL Server Running",
                    "api_docs": "/api/docs",
                    "websocket": "/api/v1/ws/stream"
                }
    except Exception as e:
        logger.error(f"Failed to setup static file serving: {e}")
        
        @app.get("/")
        async def root():
            return {"message": "RASL Server Running", "error": "UI not available"}
    
    # Startup event
    @app.on_event("startup")
    async def startup_event():
        logger.info("RASL web server starting up")
    
    # Shutdown event
    @app.on_event("shutdown")
    async def shutdown_event():
        logger.info("RASL web server shutting down")
    
    return app
