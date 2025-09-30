"""
Unit tests for WebServerManager.

Tests the lifecycle management of the web server component,
including startup, shutdown, and error handling.
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from pathlib import Path

from rasl.config import Config
from rasl.core.monitor import NodeMonitor


class TestWebServerManager:
    """Test WebServerManager functionality."""
    
    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return Config(
            script_path=Path("test.py"),
            host="localhost",
            ui_port=8080,
            debug_mode=True
        )
    
    @pytest.fixture
    def monitor(self):
        """Create test monitor."""
        return NodeMonitor()
    
    @pytest.fixture
    def engine_provider(self):
        """Create mock engine provider."""
        mock_engine = Mock()
        mock_engine._running = True
        return lambda: mock_engine
    
    def test_web_server_manager_creation(self, config):
        """
        WebServerManager should initialize with config.
        
        This test will fail initially since WebServerManager doesn't exist yet.
        """
        from rasl.server.manager import WebServerManager
        
        manager = WebServerManager(config)
        
        assert manager.config == config
        assert manager.server is None
        assert manager.server_task is None
        assert manager.app is None
    
    @pytest.mark.asyncio
    async def test_web_server_start(self, config, monitor, engine_provider):
        """
        WebServerManager should start the web server successfully.
        
        Tests the complete startup process including FastAPI app creation
        and uvicorn server initialization.
        """
        from rasl.server.manager import WebServerManager
        
        manager = WebServerManager(config)
        
        # Mock uvicorn components
        with patch('rasl.server.manager.uvicorn') as mock_uvicorn, \
             patch('rasl.server.manager.create_web_app') as mock_create_app:
            
            mock_app = Mock()
            mock_create_app.return_value = mock_app
            
            mock_server = Mock()
            mock_uvicorn.Server.return_value = mock_server
            mock_server.serve = AsyncMock()
            
            # Start the server
            await manager.start(engine_provider, monitor)
            
            # Verify app creation
            mock_create_app.assert_called_once_with(
                engine_provider=engine_provider,
                monitor=monitor,
                config=config
            )
            
            # Verify server configuration
            mock_uvicorn.Config.assert_called_once()
            config_call = mock_uvicorn.Config.call_args
            assert config_call[1]['host'] == 'localhost'
            assert config_call[1]['port'] == 8080
            
            # Verify server is stored
            assert manager.server == mock_server
            assert manager.app == mock_app
            assert manager.server_task is not None
    
    @pytest.mark.asyncio
    async def test_web_server_stop(self, config, monitor, engine_provider):
        """
        WebServerManager should stop the web server gracefully.
        
        Tests cleanup and graceful shutdown of the server.
        """
        from rasl.server.manager import WebServerManager
        
        manager = WebServerManager(config)
        
        with patch('rasl.server.manager.uvicorn') as mock_uvicorn, \
             patch('rasl.server.manager.create_web_app'):
            
            mock_server = Mock()
            mock_uvicorn.Server.return_value = mock_server
            mock_server.serve = AsyncMock()
            
            # Start then stop
            await manager.start(engine_provider, monitor)
            await manager.stop()
            
            # Verify server shutdown
            assert mock_server.should_exit is True
    
    @pytest.mark.asyncio
    async def test_web_server_start_error_handling(self, config, monitor, engine_provider):
        """
        WebServerManager should handle startup errors gracefully.
        
        Tests error handling during server initialization.
        """
        from rasl.server.manager import WebServerManager
        
        manager = WebServerManager(config)
        
        with patch('rasl.server.manager.create_web_app') as mock_create_app:
            mock_create_app.side_effect = Exception("App creation failed")
            
            # Should raise the exception
            with pytest.raises(Exception, match="App creation failed"):
                await manager.start(engine_provider, monitor)
            
            # Should not have server or task set
            assert manager.server is None
            assert manager.server_task is None
    
    @pytest.mark.asyncio
    async def test_web_server_stop_when_not_started(self, config):
        """
        WebServerManager should handle stop() when server was never started.
        
        Tests defensive programming for cleanup.
        """
        from rasl.server.manager import WebServerManager
        
        manager = WebServerManager(config)
        
        # Should not raise an error
        await manager.stop()
        
        # State should remain clean
        assert manager.server is None
        assert manager.server_task is None
    
    @pytest.mark.asyncio
    async def test_web_server_restart(self, config, monitor, engine_provider):
        """
        WebServerManager should support restart operations.
        
        Tests stopping and restarting the server.
        """
        from rasl.server.manager import WebServerManager
        
        manager = WebServerManager(config)
        
        with patch('rasl.server.manager.uvicorn') as mock_uvicorn, \
             patch('rasl.server.manager.create_web_app') as mock_create_app:
            
            mock_app = Mock()
            mock_create_app.return_value = mock_app
            
            # Create different mock instances for each call
            mock_server1 = Mock()
            mock_server1.serve = AsyncMock()
            mock_server2 = Mock()
            mock_server2.serve = AsyncMock()
            
            mock_uvicorn.Server.side_effect = [mock_server1, mock_server2]
            
            # Start, stop, start again
            await manager.start(engine_provider, monitor)
            first_server = manager.server
            
            await manager.stop()
            await manager.start(engine_provider, monitor)
            
            # Should have new server instance
            assert manager.server != first_server
            assert manager.server is not None
    
    def test_web_server_manager_config_validation(self):
        """
        WebServerManager should validate configuration.
        
        Tests that invalid configurations are handled appropriately.
        """
        from rasl.server.manager import WebServerManager
        
        # Test with invalid port
        config = Config(
            script_path=Path("test.py"),
            ui_port=-1  # Invalid port
        )
        
        # Should still create manager (validation happens at runtime)
        manager = WebServerManager(config)
        assert manager.config.ui_port == -1
