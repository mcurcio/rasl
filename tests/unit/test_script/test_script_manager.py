"""
Unit tests for ScriptManager.

Tests script loading, watching, and hot-reload functionality
with proper separation from the main application logic.
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from pathlib import Path

from rasl.config import Config


class TestScriptManager:
    """Test ScriptManager functionality."""
    
    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return Config(
            script_path=Path("examples/test.py"),
            watch_enabled=True,
            debug_mode=True
        )
    
    def test_script_manager_creation(self, config):
        """
        ScriptManager should initialize with config.
        
        This test will fail initially since ScriptManager doesn't exist yet.
        """
        from rasl.script.manager import ScriptManager
        
        manager = ScriptManager(config)
        
        assert manager.config == config
        assert manager.loader is not None
        assert manager.watcher is None
        assert manager.current_spec is None
    
    @pytest.mark.asyncio
    async def test_load_initial_script(self, config):
        """
        ScriptManager should load the initial script successfully.
        
        Tests script loading and graph spec creation.
        """
        from rasl.script.manager import ScriptManager
        
        manager = ScriptManager(config)
        
        # Mock the script loader
        with patch.object(manager.loader, 'load_script') as mock_load:
            mock_spec = Mock()
            mock_spec.nodes = [Mock(), Mock()]
            mock_spec.sinks = [Mock()]
            mock_load.return_value = mock_spec
            
            # Load the script
            spec = await manager.load_initial_script()
            
            # Verify loading
            mock_load.assert_called_once_with(config.script_path)
            assert spec == mock_spec
            assert manager.current_spec == mock_spec
    
    @pytest.mark.asyncio
    async def test_start_watching(self, config):
        """
        ScriptManager should start file watching when enabled.
        
        Tests the script watcher initialization and callback setup.
        """
        from rasl.script.manager import ScriptManager
        
        manager = ScriptManager(config)
        
        # Mock the script watcher
        with patch('rasl.script.manager.ScriptWatcher') as mock_watcher_class:
            mock_watcher = Mock()
            mock_watcher.start = AsyncMock()
            mock_watcher_class.return_value = mock_watcher
            
            callback = AsyncMock()
            
            # Start watching
            await manager.start_watching(callback)
            
            # Verify watcher creation and startup
            mock_watcher_class.assert_called_once_with(
                script_path=config.script_path,
                on_change=callback
            )
            mock_watcher.start.assert_called_once()
            assert manager.watcher == mock_watcher
    
    @pytest.mark.asyncio
    async def test_start_watching_disabled(self, config):
        """
        ScriptManager should not start watching when disabled in config.
        
        Tests conditional watching based on configuration.
        """
        from rasl.script.manager import ScriptManager
        
        # Disable watching
        config.watch_enabled = False
        manager = ScriptManager(config)
        
        callback = AsyncMock()
        
        # Should not start watcher
        await manager.start_watching(callback)
        
        assert manager.watcher is None
    
    @pytest.mark.asyncio
    async def test_reload_script(self, config):
        """
        ScriptManager should reload script and return new spec.
        
        Tests hot-reload functionality.
        """
        from rasl.script.manager import ScriptManager
        
        manager = ScriptManager(config)
        
        # Set initial spec
        old_spec = Mock()
        manager.current_spec = old_spec
        
        # Mock the reload
        with patch.object(manager.loader, 'load_script') as mock_load:
            new_spec = Mock()
            new_spec.nodes = [Mock(), Mock(), Mock()]
            new_spec.sinks = [Mock(), Mock()]
            mock_load.return_value = new_spec
            
            # Reload the script
            spec = await manager.reload_script()
            
            # Verify reload
            mock_load.assert_called_once_with(config.script_path)
            assert spec == new_spec
            assert manager.current_spec == new_spec
            assert manager.current_spec != old_spec
    
    @pytest.mark.asyncio
    async def test_stop_watching(self, config):
        """
        ScriptManager should stop file watching gracefully.
        
        Tests cleanup of watcher resources.
        """
        from rasl.script.manager import ScriptManager
        
        manager = ScriptManager(config)
        
        # Mock watcher
        with patch('rasl.script.manager.ScriptWatcher') as mock_watcher_class:
            mock_watcher = Mock()
            mock_watcher.start = AsyncMock()
            mock_watcher.stop = AsyncMock()
            mock_watcher_class.return_value = mock_watcher
            
            callback = AsyncMock()
            
            # Start and stop watching
            await manager.start_watching(callback)
            await manager.stop_watching()
            
            # Verify cleanup
            mock_watcher.stop.assert_called_once()
            assert manager.watcher is None
    
    @pytest.mark.asyncio
    async def test_stop_watching_when_not_started(self, config):
        """
        ScriptManager should handle stop_watching when watcher was never started.
        
        Tests defensive programming for cleanup.
        """
        from rasl.script.manager import ScriptManager
        
        manager = ScriptManager(config)
        
        # Should not raise an error
        await manager.stop_watching()
        
        assert manager.watcher is None
    
    @pytest.mark.asyncio
    async def test_script_load_error_handling(self, config):
        """
        ScriptManager should handle script loading errors gracefully.
        
        Tests error propagation and state management during failures.
        """
        from rasl.script.manager import ScriptManager
        
        manager = ScriptManager(config)
        
        # Mock loader to raise error
        with patch.object(manager.loader, 'load_script') as mock_load:
            mock_load.side_effect = Exception("Script syntax error")
            
            # Should propagate the error
            with pytest.raises(Exception, match="Script syntax error"):
                await manager.load_initial_script()
            
            # State should remain clean
            assert manager.current_spec is None
    
    @pytest.mark.asyncio
    async def test_script_reload_error_handling(self, config):
        """
        ScriptManager should handle reload errors without losing current spec.
        
        Tests error recovery during hot-reload.
        """
        from rasl.script.manager import ScriptManager
        
        manager = ScriptManager(config)
        
        # Set initial spec
        old_spec = Mock()
        manager.current_spec = old_spec
        
        # Mock reload to fail
        with patch.object(manager.loader, 'load_script') as mock_load:
            mock_load.side_effect = Exception("Reload failed")
            
            # Should propagate error but preserve state
            with pytest.raises(Exception, match="Reload failed"):
                await manager.reload_script()
            
            # Should keep old spec
            assert manager.current_spec == old_spec
    
    def test_script_manager_properties(self, config):
        """
        ScriptManager should provide useful properties for status checking.
        
        Tests property accessors for current state.
        """
        from rasl.script.manager import ScriptManager
        
        manager = ScriptManager(config)
        
        # Initially no script loaded
        assert not manager.has_script
        assert manager.script_path == config.script_path
        
        # After loading
        mock_spec = Mock()
        manager.current_spec = mock_spec
        assert manager.has_script
