"""
Web server lifecycle management for RASL.

Handles the startup, shutdown, and configuration of the FastAPI web server
that provides the monitoring UI and REST API.
"""

import asyncio
import logging
from typing import Optional, Callable, Any

import uvicorn
from rasl.config import Config
from rasl.core.monitor import NodeMonitor
from .app import create_web_app

logger = logging.getLogger(__name__)


class WebServerManager:
    """
    Manages the lifecycle of the RASL web server.
    
    Handles FastAPI application creation, uvicorn server startup/shutdown,
    and provides clean separation between web server concerns and main
    application logic.
    """
    
    def __init__(self, config: Config):
        """
        Initialize web server manager.
        
        Args:
            config: Application configuration containing server settings
        """
        self.config = config
        self.server: Optional[uvicorn.Server] = None
        self.server_task: Optional[asyncio.Task] = None
        self.app: Optional[Any] = None  # FastAPI app
    
    async def start(
        self, 
        engine_provider: Callable[[], Any], 
        monitor: NodeMonitor
    ) -> None:
        """
        Start the web server.
        
        Creates the FastAPI application and starts the uvicorn server
        in a background task.
        
        Args:
            engine_provider: Function that returns the current engine instance
            monitor: Node monitor for health/performance data
            
        Raises:
            Exception: If server startup fails
        """
        logger.info(f"Starting web server on {self.config.host}:{self.config.ui_port}")
        
        try:
            # Create FastAPI application
            self.app = create_web_app(
                engine_provider=engine_provider,
                monitor=monitor,
                config=self.config
            )
            
            # Configure uvicorn server
            server_config = uvicorn.Config(
                self.app,
                host=self.config.host,
                port=self.config.ui_port,
                log_level="info" if self.config.debug_mode else "warning",
                access_log=self.config.debug_mode
            )
            
            self.server = uvicorn.Server(server_config)
            
            # Start server in background task
            self.server_task = asyncio.create_task(self.server.serve())
            
            logger.info(f"Web server started successfully on http://{self.config.host}:{self.config.ui_port}")
            
        except Exception as e:
            logger.error(f"Failed to start web server: {e}")
            # Clean up partial state
            self.server = None
            self.server_task = None
            self.app = None
            raise
    
    async def stop(self) -> None:
        """
        Stop the web server gracefully.
        
        Signals the server to shut down and waits for the background
        task to complete.
        """
        if self.server is None:
            logger.debug("Web server not running, nothing to stop")
            return
        
        logger.info("Stopping web server...")
        
        try:
            # Signal server to stop
            self.server.should_exit = True
            
            # Wait for server task to complete
            if self.server_task:
                try:
                    await asyncio.wait_for(self.server_task, timeout=5.0)
                except asyncio.TimeoutError:
                    logger.warning("Web server shutdown timed out, cancelling task")
                    self.server_task.cancel()
                    try:
                        await self.server_task
                    except asyncio.CancelledError:
                        pass
            
            logger.info("Web server stopped successfully")
            
        except Exception as e:
            logger.error(f"Error during web server shutdown: {e}")
        
        finally:
            # Clean up state
            self.server = None
            self.server_task = None
            self.app = None
    
    @property
    def is_running(self) -> bool:
        """
        Check if the web server is currently running.
        
        Returns:
            True if server is running, False otherwise
        """
        return (
            self.server is not None and 
            self.server_task is not None and 
            not self.server_task.done()
        )
    
    @property
    def server_url(self) -> str:
        """
        Get the server URL.
        
        Returns:
            Full URL where the server is accessible
        """
        return f"http://{self.config.host}:{self.config.ui_port}"
