"""
Tests for the main RASL execution engine.
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock

from rasl.core.engine import Engine, create_engine
from rasl.core.scheduler import ManualScheduler, MonotonicClock
from rasl.core.types import Frame
from rasl.core.monitor import NodeMonitor


class TestEngine:
    """Test Engine functionality."""
    
    def setup_method(self):
        """Set up test components."""
        self.clock = MonotonicClock()
        self.scheduler = ManualScheduler(self.clock)
        self.monitor = NodeMonitor()
        
        # Create mock sink
        self.mock_sink = Mock()
        self.mock_sink.id = "test_sink"
        self.mock_sink.ports.list.return_value = []
        self.mock_sink.emit = Mock()
    
    def test_engine_creation(self):
        """Test basic engine creation."""
        engine = Engine(
            sinks=[self.mock_sink],
            scheduler=self.scheduler,
            monitor=self.monitor
        )
        
        assert engine.sinks == [self.mock_sink]
        assert engine.scheduler == self.scheduler
        assert engine.monitor == self.monitor
        assert not engine._running
    
    def test_engine_validation_on_creation(self):
        """Test that engine validates graph on creation."""
        # This should work with mock sink
        engine = Engine(
            sinks=[self.mock_sink],
            scheduler=self.scheduler
        )
        assert engine is not None
        
        # Empty sinks should fail
        with pytest.raises(Exception):  # ValidationError
            Engine(sinks=[], scheduler=self.scheduler)
    
    @pytest.mark.asyncio
    async def test_tick_once(self):
        """Test single frame execution."""
        engine = Engine(
            sinks=[self.mock_sink],
            scheduler=self.scheduler,
            monitor=self.monitor
        )
        
        await engine.tick_once()
        
        # Should have called emit on the sink
        self.mock_sink.emit.assert_called_once()
        
        # Check that frame was passed
        call_args = self.mock_sink.emit.call_args
        assert len(call_args[0]) == 1  # One positional arg (frame)
        frame = call_args[0][0]
        assert isinstance(frame, Frame)
    
    @pytest.mark.asyncio
    async def test_tick_once_while_running_fails(self):
        """Test that tick_once fails when engine is running."""
        engine = Engine(
            sinks=[self.mock_sink],
            scheduler=self.scheduler
        )
        
        # Mock running state
        engine._running = True
        
        with pytest.raises(RuntimeError, match="Cannot tick_once while engine is running"):
            await engine.tick_once()
    
    @pytest.mark.asyncio
    async def test_engine_start_stop(self):
        """Test engine lifecycle."""
        engine = Engine(
            sinks=[self.mock_sink],
            scheduler=self.scheduler
        )
        
        # Start engine
        start_task = asyncio.create_task(engine.start())
        
        # Give it a moment to start
        await asyncio.sleep(0.01)
        assert engine._running
        
        # Stop engine
        await engine.stop()
        assert not engine._running
        
        # Wait for start task to complete
        await start_task
    
    @pytest.mark.asyncio
    async def test_engine_restart(self):
        """Test engine restart functionality."""
        engine = Engine(
            sinks=[self.mock_sink],
            scheduler=self.scheduler
        )
        
        # Mock the start/stop methods to avoid actual execution
        engine.start = AsyncMock()
        engine.stop = AsyncMock()
        engine._validate_graph = Mock()
        
        await engine.restart()
        
        engine.stop.assert_called_once()
        engine._validate_graph.assert_called_once()
        engine.start.assert_called_once()
    
    def test_get_node_status(self):
        """Test node status retrieval."""
        engine = Engine(
            sinks=[self.mock_sink],
            scheduler=self.scheduler,
            monitor=self.monitor
        )
        
        # Initially no status
        assert engine.get_node_status("nonexistent") is None
        
        # After recording an error, should have status
        self.monitor.record_node_error("test_node", ValueError("test error"))
        status = engine.get_node_status("test_node")
        assert status is not None
        assert status.error_count == 1
    
    def test_get_health_summary(self):
        """Test health summary retrieval."""
        engine = Engine(
            sinks=[self.mock_sink],
            scheduler=self.scheduler,
            monitor=self.monitor
        )
        
        summary = engine.get_health_summary()
        assert "total_nodes" in summary
        assert "overall_health" in summary


class TestEngineIntegration:
    """Integration tests with real components."""
    
    @pytest.mark.asyncio
    async def test_engine_with_test_nodes(self, test_source, test_transform, test_sink):
        """Test engine with actual test nodes."""
        # Connect nodes
        test_source.ports.out >> test_transform.ports.in
        test_transform.ports.out >> test_sink.ports.in
        
        # Create engine
        clock = MonotonicClock()
        scheduler = ManualScheduler(clock)
        engine = Engine(sinks=[test_sink], scheduler=scheduler)
        
        # Execute one frame
        await engine.tick_once()
        
        # Check that data flowed through
        assert len(test_sink.captured_data) == 1
        assert len(test_sink.captured_frames) == 1
        
        # Verify data transformation
        captured = test_sink.captured_data[0]
        assert "in" in captured
        # test_source generates [0.8, 0.8, 0.8], test_transform scales by 0.5
        expected = [0.4, 0.4, 0.4]  # 0.8 * 0.5
        assert captured["in"] == expected


class TestCreateEngine:
    """Test convenience function for creating engines."""
    
    def test_create_engine(self):
        """Test create_engine convenience function."""
        clock = MonotonicClock()
        scheduler = ManualScheduler(clock)
        mock_sink = Mock()
        mock_sink.id = "test_sink"
        mock_sink.ports.list.return_value = []
        
        engine = create_engine(sinks=[mock_sink], scheduler=scheduler)
        
        assert isinstance(engine, Engine)
        assert engine.sinks == [mock_sink]
        assert engine.scheduler == scheduler
