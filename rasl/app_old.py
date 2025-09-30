"""
Main RASL application orchestrator.

Coordinates script loading, engine execution, web server, and monitoring
through dedicated manager components.
"""

import asyncio
import logging
import signal
from pathlib import Path
from typing import Optional

from rasl.config import Config
from rasl.core.monitor import NodeMonitor
from rasl.script.manager import ScriptManager
from rasl.server.manager import WebServerManager

logger = logging.getLogger(__name__)


class RASLApp:
    """
    Main application orchestrator that coordinates RASL components.
    
    Uses dedicated managers for clean separation of concerns:
    - ScriptManager: Handles script loading and hot-reload
    - WebServerManager: Manages web server lifecycle
    - Engine: Executes the animation graph
    - Monitor: Tracks performance and health
    """
    
    def __init__(self, config: Config):
        self.config = config
        self.engine: Optional[Engine] = None
        self.monitor = NodeMonitor()
        
        # Dedicated managers for clean separation
        self.script_manager = ScriptManager(config)
        self.web_server_manager = WebServerManager(config)
        
        self._shutdown_event = asyncio.Event()
        
    async def run(self):
        """Main application run loop."""
        
        try:
            # Load script and create engine
            await self.script_manager.load_initial_script()
            self._create_engine()
            graph_spec = await self.script_loader.load_script(self.config.script_path)
            logger.info(f"Script loaded successfully: {len(graph_spec.nodes)} nodes, {len(graph_spec.sinks)} sinks")
            
            # Stop existing engine if running
            if self.engine:
                await self.engine.stop()
            
            # Create new engine from the discovered graph
            from .core.scheduler import FixedRateScheduler, MonotonicClock
            from .core.engine import Engine
            from .core.executor import Executor
            from .core.validator import Validator
            
            # Create scheduler with configured frame rate
            clock = MonotonicClock()
            scheduler = FixedRateScheduler(clock, self.config.default_frame_rate)
            
            # Create executor and register all discovered nodes
            executor = Executor()
            for node in graph_spec.nodes:
                executor.register_node(node)
            
            # Create validator and register nodes
            validator = Validator()
            for node in graph_spec.nodes:
                validator.register_node(node)
            
            # Create engine with discovered sinks
            self.engine = Engine(
                sinks=graph_spec.sinks,
                scheduler=scheduler,
                executor=executor,
                validator=validator,
                monitor=self.monitor
            )
            
            logger.info(f"Engine created with {len(graph_spec.sinks)} sinks")
            
        except Exception as e:
            logger.error(f"Failed to load script: {e}")
            raise
            
    async def _start_script_watcher(self):
        """Start watching script file for changes."""
        self.script_watcher = ScriptWatcher(
            script_path=self.config.script_path,
            on_change=self._handle_script_change
        )
        await self.script_watcher.start()
        logger.info("Script watcher started")
        
    async def _handle_script_change(self):
        """Handle script file changes for hot-reload."""
        logger.info("Script changed, reloading...")
        
        try:
            await self._load_script()
            
            # Restart engine with new graph
            if self.engine:
                await self.engine.restart()
                
            logger.info("Script reloaded successfully")
            
        except Exception as e:
            logger.error(f"Failed to reload script: {e}")
            # Don't crash on reload failure, keep running with old graph
            
    async def _start_web_server(self):
        """Start the web server for UI and API."""
        import uvicorn
        from rasl.server.app import create_web_app
        
        self.web_app = create_web_app(
            engine_provider=lambda: self.engine,
            monitor=self.monitor,
            config=self.config
        )
        
        # Start uvicorn server in background
        config = uvicorn.Config(
            self.web_app,
            host=self.config.host,
            port=self.config.ui_port,
            log_level="info"
        )
        self.web_server = uvicorn.Server(config)
        
        # Start server in background task
        import asyncio
        self.web_server_task = asyncio.create_task(self.web_server.serve())
        
    async def _start_engine(self):
        """Start the execution engine."""
        if not self.engine:
            logger.warning("No engine to start (script may have failed to load)")
            return
            
        logger.info("Starting execution engine...")
        await self.engine.start()
        
    async def _cleanup(self):
        """Clean up resources on shutdown."""
        logger.info("Shutting down RASL application...")
        
        tasks = []
        
        if self.engine:
            tasks.append(self.engine.stop())
            
        if self.script_watcher:
            tasks.append(self.script_watcher.stop())
            
        # Stop web server
        if hasattr(self, 'web_server') and self.web_server:
            self.web_server.should_exit = True
            if hasattr(self, 'web_server_task'):
                tasks.append(self.web_server_task)
            
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
            
        logger.info("Cleanup complete")
    
    def _setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown."""
        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, initiating graceful shutdown...")
            # Set the shutdown event directly (thread-safe)
            self._shutdown_event.set()
        
        # Register handlers for common shutdown signals
        signal.signal(signal.SIGINT, signal_handler)   # Ctrl+C
        signal.signal(signal.SIGTERM, signal_handler)  # Termination signal
        
        logger.info("Signal handlers registered for graceful shutdown")
        
    def _setup_logging(self):
        """Configure application logging."""
        level = logging.DEBUG if self.config.debug_mode else logging.INFO
        
        logging.basicConfig(
            level=level,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            handlers=[
                logging.StreamHandler(),
                # TODO: Add file handler for production logs
            ]
        )
        
    def shutdown(self):
        """Signal the application to shut down."""
        self._shutdown_event.set()
