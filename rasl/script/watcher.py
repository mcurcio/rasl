"""
File system watcher for hot-reload functionality.

Monitors script files for changes and triggers reload events
for seamless development experience.
"""

import asyncio
import logging
from pathlib import Path
from typing import Callable, Optional
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileModifiedEvent

logger = logging.getLogger(__name__)


class ScriptFileHandler(FileSystemEventHandler):
    """Handles file system events for script files."""
    
    def __init__(self, script_path: Path, on_change_callback: Callable[[], None]):
        super().__init__()
        self.script_path = script_path
        self.on_change_callback = on_change_callback
        self._last_modified = 0.0
        self._debounce_delay = 0.5  # 500ms debounce
    
    def on_modified(self, event):
        """Handle file modification events."""
        if event.is_directory:
            return
        
        # Check if this is our target file
        event_path = Path(event.src_path)
        if event_path.resolve() != self.script_path.resolve():
            return
        
        # Debounce rapid file changes (common with editors)
        import time
        current_time = time.time()
        if current_time - self._last_modified < self._debounce_delay:
            return
        
        self._last_modified = current_time
        
        logger.info(f"Script file changed: {self.script_path}")
        
        # Call the change callback
        try:
            self.on_change_callback()
        except Exception as e:
            logger.error(f"Error in change callback: {e}")


class ScriptWatcher:
    """
    Watches script files for changes and triggers hot-reload.
    
    Provides debounced file watching with async callback support
    for seamless development workflow.
    """
    
    def __init__(self, script_path: Path, on_change: Callable[[], None]):
        self.script_path = script_path
        self.on_change = on_change
        self._observer: Optional[Observer] = None
        self._handler: Optional[ScriptFileHandler] = None
        self._running = False
    
    async def start(self) -> None:
        """Start watching the script file for changes."""
        if self._running:
            logger.warning("Script watcher is already running")
            return
        
        if not self.script_path.exists():
            raise FileNotFoundError(f"Script file not found: {self.script_path}")
        
        logger.info(f"Starting script watcher for: {self.script_path}")
        
        # Create file system observer
        self._observer = Observer()
        self._handler = ScriptFileHandler(self.script_path, self._on_change_wrapper)
        
        # Watch the directory containing the script
        watch_dir = self.script_path.parent
        self._observer.schedule(self._handler, str(watch_dir), recursive=False)
        
        # Start the observer
        self._observer.start()
        self._running = True
        
        logger.info("Script watcher started successfully")
    
    async def stop(self) -> None:
        """Stop watching for file changes."""
        if not self._running:
            return
        
        logger.info("Stopping script watcher")
        
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=5.0)  # Wait up to 5 seconds
            self._observer = None
        
        self._handler = None
        self._running = False
        
        logger.info("Script watcher stopped")
    
    def _on_change_wrapper(self) -> None:
        """Wrapper to handle async callback from sync file watcher."""
        # Schedule the async callback to run in the event loop
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._async_on_change())
        except RuntimeError:
            # No event loop running, call synchronously
            logger.warning("No event loop running, calling change handler synchronously")
            if asyncio.iscoroutinefunction(self.on_change):
                logger.error("Cannot call async change handler without event loop")
            else:
                self.on_change()
    
    async def _async_on_change(self) -> None:
        """Async wrapper for change callback."""
        try:
            if asyncio.iscoroutinefunction(self.on_change):
                await self.on_change()
            else:
                self.on_change()
        except Exception as e:
            logger.error(f"Error in script change handler: {e}")
    
    @property
    def is_running(self) -> bool:
        """Check if the watcher is currently running."""
        return self._running


class MultiScriptWatcher:
    """
    Watches multiple script files simultaneously.
    
    Useful for watching script dependencies or multiple related files.
    """
    
    def __init__(self):
        self._watchers: dict[Path, ScriptWatcher] = {}
        self._running = False
    
    def add_script(self, script_path: Path, on_change: Callable[[], None]) -> None:
        """Add a script to watch."""
        if script_path in self._watchers:
            logger.warning(f"Script already being watched: {script_path}")
            return
        
        watcher = ScriptWatcher(script_path, on_change)
        self._watchers[script_path] = watcher
        
        # If we're already running, start this watcher immediately
        if self._running:
            asyncio.create_task(watcher.start())
    
    def remove_script(self, script_path: Path) -> None:
        """Remove a script from watching."""
        if script_path not in self._watchers:
            return
        
        watcher = self._watchers[script_path]
        if watcher.is_running:
            asyncio.create_task(watcher.stop())
        
        del self._watchers[script_path]
    
    async def start_all(self) -> None:
        """Start watching all registered scripts."""
        if self._running:
            return
        
        logger.info(f"Starting multi-script watcher for {len(self._watchers)} scripts")
        
        # Start all watchers
        start_tasks = []
        for watcher in self._watchers.values():
            start_tasks.append(watcher.start())
        
        if start_tasks:
            await asyncio.gather(*start_tasks, return_exceptions=True)
        
        self._running = True
    
    async def stop_all(self) -> None:
        """Stop watching all scripts."""
        if not self._running:
            return
        
        logger.info("Stopping multi-script watcher")
        
        # Stop all watchers
        stop_tasks = []
        for watcher in self._watchers.values():
            if watcher.is_running:
                stop_tasks.append(watcher.stop())
        
        if stop_tasks:
            await asyncio.gather(*stop_tasks, return_exceptions=True)
        
        self._running = False
    
    def get_watched_scripts(self) -> list[Path]:
        """Get list of currently watched script paths."""
        return list(self._watchers.keys())


# Utility functions for common watching patterns
async def watch_script_with_dependencies(
    main_script: Path,
    dependencies: list[Path],
    on_any_change: Callable[[], None]
) -> MultiScriptWatcher:
    """
    Watch a main script and its dependencies.
    
    Calls the same callback when any file changes.
    """
    watcher = MultiScriptWatcher()
    
    # Add main script
    watcher.add_script(main_script, on_any_change)
    
    # Add dependencies
    for dep_path in dependencies:
        watcher.add_script(dep_path, on_any_change)
    
    await watcher.start_all()
    return watcher
