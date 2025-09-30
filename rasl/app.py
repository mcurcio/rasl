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
        self.engine: Optional['Engine'] = None
        self.monitor = NodeMonitor()
        
        # Dedicated managers for clean separation
        self.script_manager = ScriptManager(config)
        self.web_server_manager = WebServerManager(config)
        
        self._shutdown_event = asyncio.Event()
        
    async def run(self):
        """Main application run loop."""
        
        # Setup logging
        self._setup_logging()
        
        # Setup signal handlers for graceful shutdown
        self._setup_signal_handlers()
        
        try:
            # Load script and create engine
            await self.script_manager.load_initial_script()
            self._create_engine()
            
            # Start managers
            await self.script_manager.start_watching(self._handle_script_change)
            await self.web_server_manager.start(
                engine_provider=lambda: self.engine,
                monitor=self.monitor
            )
            
            # Start engine execution
            await self._start_engine()
            
            # Wait for shutdown signal
            await self._shutdown_event.wait()
            
        finally:
            # Always cleanup
            await self._cleanup()
    
    def _create_engine(self):
        """Create engine from current script specification."""
        if not self.script_manager.current_spec:
            raise RuntimeError("No script loaded")
        
        spec = self.script_manager.current_spec
        logger.info(f"Creating engine: {len(spec.nodes)} nodes, {len(spec.sinks)} sinks")
        
        # Import engine components
        from rasl.core.scheduler import FixedRateScheduler, MonotonicClock
        from rasl.core.engine import Engine
        from rasl.core.executor import Executor
        from rasl.core.validator import Validator
        
        # Create scheduler with configured frame rate
        clock = MonotonicClock()
        scheduler = FixedRateScheduler(clock, self.config.default_frame_rate)
        
        # Create executor and register all discovered nodes
        executor = Executor()
        for node in spec.nodes:
            executor.register_node(node)
        
        # Create validator and register nodes
        validator = Validator()
        for node in spec.nodes:
            validator.register_node(node)
        
        # Create engine with discovered sinks
        self.engine = Engine(
            sinks=spec.sinks,
            scheduler=scheduler,
            executor=executor,
            validator=validator,
            monitor=self.monitor
        )
        
        logger.info(f"Engine created with {len(spec.sinks)} sinks")
        return self.engine
    
    async def _handle_script_change(self):
        """Handle script file changes for hot-reload."""
        logger.info("Script changed, reloading...")
        
        try:
            await self.script_manager.reload_script()
            
            # Restart engine with new graph
            if self.engine:
                await self.engine.restart()
                
            logger.info("Script reloaded successfully")
            
        except Exception as e:
            logger.error(f"Failed to reload script: {e}")
            # Don't crash on reload failure, keep running with old graph
    
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
        
        # Stop engine
        if self.engine:
            tasks.append(self.engine.stop())
        
        # Stop script watcher
        if self.script_manager.is_watching:
            tasks.append(self.script_manager.stop_watching())
        
        # Stop web server
        if self.web_server_manager.is_running:
            tasks.append(self.web_server_manager.stop())
        
        # Wait for all cleanup tasks
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
