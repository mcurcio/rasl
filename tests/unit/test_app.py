"""
Unit tests for the refactored RASLApp.

Tests the main application orchestration with extracted managers.
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from pathlib import Path

from rasl.config import Config


class TestRASLApp:
    """Test refactored RASLApp functionality."""
    
    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return Config(
            script_path=Path("examples/test.py"),
            watch_enabled=True,
            debug_mode=True
        )
    
    def test_rasl_app_creation(self, config):
        """
        RASLApp should initialize with managers.
        
        Tests that the app creates the necessary manager components.
        """
        from rasl.app import RASLApp
        
        app = RASLApp(config)
        
        assert app.config == config
        assert app.engine is None
        assert app.monitor is not None
        assert hasattr(app, 'script_manager')
        assert hasattr(app, 'web_server_manager')
    
    @pytest.mark.asyncio
    async def test_rasl_app_run_lifecycle(self, config):
        """
        RASLApp should orchestrate the complete application lifecycle.
        
        Tests startup sequence with all managers.
        """
        from rasl.app import RASLApp
        
        app = RASLApp(config)
        
        # Mock all the managers and components
        with patch.object(app.script_manager, 'load_initial_script') as mock_load, \
             patch.object(app.script_manager, 'start_watching') as mock_watch, \
             patch.object(app.web_server_manager, 'start') as mock_web_start, \
             patch.object(app, '_create_engine') as mock_create_engine, \
             patch.object(app, '_setup_signal_handlers') as mock_signals:
            
            # Mock script loading
            mock_spec = Mock()
            mock_spec.nodes = [Mock(), Mock()]
            mock_spec.sinks = [Mock()]
            mock_load.return_value = mock_spec
            
            # Mock engine
            mock_engine = Mock()
            mock_engine.start = AsyncMock()
            mock_engine.stop = AsyncMock()
            mock_create_engine.return_value = mock_engine
            app.engine = mock_engine
            
            # Mock async methods
            mock_watch.return_value = AsyncMock()
            mock_web_start.return_value = AsyncMock()
            
            # Mock shutdown event to complete quickly
            app._shutdown_event.set()
            
            # Run the app
            await app.run()
            
            # Verify startup sequence
            mock_signals.assert_called_once()
            mock_load.assert_called_once()
            mock_create_engine.assert_called_once()
            mock_watch.assert_called_once()
            mock_web_start.assert_called_once()
            mock_engine.start.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_rasl_app_script_change_handling(self, config):
        """
        RASLApp should handle script changes through the script manager.
        
        Tests hot-reload coordination between managers.
        """
        from rasl.app import RASLApp
        
        app = RASLApp(config)
        
        # Set up initial state
        mock_engine = Mock()
        mock_engine.restart = AsyncMock()
        app.engine = mock_engine
        
        # Mock script manager reload
        with patch.object(app.script_manager, 'reload_script') as mock_reload:
            mock_spec = Mock()
            mock_spec.nodes = [Mock(), Mock(), Mock()]
            mock_spec.sinks = [Mock(), Mock()]
            mock_reload.return_value = mock_spec
            
            # Handle script change
            await app._handle_script_change()
            
            # Verify reload and engine restart
            mock_reload.assert_called_once()
            mock_engine.restart.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_rasl_app_cleanup(self, config):
        """
        RASLApp should clean up all managers during shutdown.
        
        Tests proper resource cleanup coordination.
        """
        from rasl.app import RASLApp
        
        app = RASLApp(config)
        
        # Set up components
        mock_engine = Mock()
        mock_engine.stop = AsyncMock()
        app.engine = mock_engine
        
        # Mock manager cleanup
        with patch.object(app.script_manager, 'stop_watching') as mock_stop_watch, \
             patch.object(app.web_server_manager, 'stop') as mock_stop_web:
            
            mock_stop_watch.return_value = AsyncMock()
            mock_stop_web.return_value = AsyncMock()
            
            # Set up manager states to trigger cleanup
            app.script_manager.watcher = Mock()  # Make is_watching return True
            app.web_server_manager.server = Mock()  # Make is_running return True
            app.web_server_manager.server_task = Mock()
            app.web_server_manager.server_task.done.return_value = False
            
            # Run cleanup
            await app._cleanup()
            
            # Verify all components cleaned up
            mock_engine.stop.assert_called_once()
            mock_stop_watch.assert_called_once()
            mock_stop_web.assert_called_once()
    
    def test_rasl_app_engine_creation(self, config):
        """
        RASLApp should create engine from script spec.
        
        Tests engine creation with proper configuration.
        """
        from rasl.app import RASLApp
        
        app = RASLApp(config)
        
        # Mock script spec
        mock_spec = Mock()
        mock_spec.nodes = [Mock(), Mock()]
        mock_spec.sinks = [Mock()]
        app.script_manager.current_spec = mock_spec
        
        # Mock engine creation
        with patch('rasl.app.Engine') as mock_engine_class, \
             patch('rasl.app.FixedRateScheduler') as mock_scheduler_class, \
             patch('rasl.app.MonotonicClock') as mock_clock_class:
            
            mock_engine = Mock()
            mock_engine_class.return_value = mock_engine
            
            # Create engine
            engine = app._create_engine()
            
            # Verify engine creation
            assert engine == mock_engine
            assert app.engine == mock_engine
            mock_engine_class.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_rasl_app_error_handling(self, config):
        """
        RASLApp should handle errors gracefully during startup.
        
        Tests error propagation and cleanup on failure.
        """
        from rasl.app import RASLApp
        
        app = RASLApp(config)
        
        # Mock script loading to fail
        with patch.object(app.script_manager, 'load_initial_script') as mock_load:
            mock_load.side_effect = Exception("Script load failed")
            
            # Should propagate the error
            with pytest.raises(Exception, match="Script load failed"):
                await app.run()
    
    def test_rasl_app_signal_handling(self, config):
        """
        RASLApp should set up signal handlers for graceful shutdown.
        
        Tests signal handler registration.
        """
        from rasl.app import RASLApp
        
        app = RASLApp(config)
        
        # Mock signal registration
        with patch('rasl.app.signal') as mock_signal:
            app._setup_signal_handlers()
            
            # Should register handlers for SIGINT and SIGTERM
            assert mock_signal.signal.call_count >= 2
