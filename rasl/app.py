"""
Main RASL application orchestrator.

Coordinates script loading, engine execution, web server, and monitoring.
"""

import asyncio
import logging
import signal
from pathlib import Path
from typing import Optional

from rasl.config import Config
from rasl.core.monitor import NodeMonitor
from rasl.script.loader import ScriptLoader
from rasl.script.watcher import ScriptWatcher
from .server.app import create_web_app

logger = logging.getLogger(__name__)


class RASLApp:
    """
    Main application class that orchestrates all RASL components.
    
    Responsibilities:
    - Load and validate user scripts
    - Start and manage the execution engine
    - Run the web server for UI and API
    - Handle hot-reload of script changes
    - Coordinate shutdown and cleanup
    """
    
    def __init__(self, config: Config):
        self.config = config
        self.engine: Optional[Engine] = None
        self.monitor = NodeMonitor()
        self.script_loader = ScriptLoader()
        self.script_watcher: Optional[ScriptWatcher] = None
        self.web_app = None
        self._shutdown_event = asyncio.Event()
        
    async def run(self):
        """Main application run loop."""
        
        # Setup logging
        self._setup_logging()
        
        # Setup signal handlers for graceful shutdown
        self._setup_signal_handlers()
        
        # Load initial script
        await self._load_script()
        
        # Start script watcher if enabled
        if self.config.watch_enabled:
            await self._start_script_watcher()
        
        # Start web server
        await self._start_web_server()
        
        # Start execution engine
        await self._start_engine()
        
        # Wait for shutdown signal
        await self._shutdown_event.wait()
        
        # Cleanup
        await self._cleanup()
        
    async def _load_script(self):
        """Load and validate the user script."""
        logger.info(f"Loading script: {self.config.script_path}")
        
        try:
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
        self.web_app = create_web_app(
            engine_provider=lambda: self.engine,
            monitor=self.monitor,
            config=self.config
        )
        
        # TODO: Start web server
        # This should start both the API server and serve the UI
        logger.info(f"Web server starting on {self.config.host}:{self.config.ui_port}")
        
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
