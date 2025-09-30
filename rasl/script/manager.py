"""
Script lifecycle management for RASL.

Handles script loading, file watching, and hot-reload functionality
with clean separation from the main application orchestration.
"""

import logging
from typing import Optional, Callable, Any
from pathlib import Path

from rasl.config import Config
from .loader import ScriptLoader
from .watcher import ScriptWatcher

logger = logging.getLogger(__name__)


class ScriptManager:
    """
    Manages the lifecycle of RASL script loading and watching.
    
    Handles script loading, file watching for hot-reload, and provides
    clean separation between script management and main application logic.
    """
    
    def __init__(self, config: Config):
        """
        Initialize script manager.
        
        Args:
            config: Application configuration containing script settings
        """
        self.config = config
        self.loader = ScriptLoader()
        self.watcher: Optional[ScriptWatcher] = None
        self.current_spec: Optional[Any] = None  # GraphSpec
    
    async def load_initial_script(self) -> Any:
        """
        Load the initial script from the configured path.
        
        Returns:
            GraphSpec: The loaded and validated graph specification
            
        Raises:
            ScriptLoadError: If script loading fails
        """
        logger.info(f"Loading initial script: {self.config.script_path}")
        
        try:
            spec = await self.loader.load_script(self.config.script_path)
            self.current_spec = spec
            
            logger.info(
                f"Script loaded successfully: {len(spec.nodes)} nodes, "
                f"{len(spec.sinks)} sinks"
            )
            
            return spec
            
        except Exception as e:
            logger.error(f"Failed to load initial script: {e}")
            raise
    
    async def start_watching(self, on_change_callback: Callable[[], Any]) -> None:
        """
        Start watching the script file for changes.
        
        Only starts watching if enabled in configuration.
        
        Args:
            on_change_callback: Async function to call when script changes
        """
        if not self.config.watch_enabled:
            logger.debug("Script watching disabled in configuration")
            return
        
        logger.info(f"Starting script watcher for: {self.config.script_path}")
        
        try:
            self.watcher = ScriptWatcher(
                script_path=self.config.script_path,
                on_change=on_change_callback
            )
            
            await self.watcher.start()
            logger.info("Script watcher started successfully")
            
        except Exception as e:
            logger.error(f"Failed to start script watcher: {e}")
            self.watcher = None
            raise
    
    async def reload_script(self) -> Any:
        """
        Reload the script from disk.
        
        Used during hot-reload when file changes are detected.
        
        Returns:
            GraphSpec: The newly loaded graph specification
            
        Raises:
            ScriptLoadError: If script reloading fails
        """
        logger.info(f"Reloading script: {self.config.script_path}")
        
        try:
            spec = await self.loader.load_script(self.config.script_path)
            self.current_spec = spec
            
            logger.info(
                f"Script reloaded successfully: {len(spec.nodes)} nodes, "
                f"{len(spec.sinks)} sinks"
            )
            
            return spec
            
        except Exception as e:
            logger.error(f"Failed to reload script: {e}")
            # Don't update current_spec on failure - keep the old one
            raise
    
    async def stop_watching(self) -> None:
        """
        Stop watching the script file for changes.
        
        Gracefully shuts down the file watcher if it's running.
        """
        if self.watcher is None:
            logger.debug("Script watcher not running, nothing to stop")
            return
        
        logger.info("Stopping script watcher")
        
        try:
            await self.watcher.stop()
            logger.info("Script watcher stopped successfully")
            
        except Exception as e:
            logger.error(f"Error stopping script watcher: {e}")
        
        finally:
            self.watcher = None
    
    @property
    def has_script(self) -> bool:
        """
        Check if a script has been successfully loaded.
        
        Returns:
            True if a script is currently loaded, False otherwise
        """
        return self.current_spec is not None
    
    @property
    def script_path(self) -> Path:
        """
        Get the configured script path.
        
        Returns:
            Path to the script file
        """
        return self.config.script_path
    
    @property
    def is_watching(self) -> bool:
        """
        Check if file watching is currently active.
        
        Returns:
            True if watching for file changes, False otherwise
        """
        return self.watcher is not None
