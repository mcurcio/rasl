"""
Integration tests for engine execution with real nodes and connections.

Tests the complete data flow pipeline from sources through transforms to sinks.
"""

import pytest
import asyncio
from unittest.mock import Mock

from rasl.core.engine import Engine
from rasl.core.executor import Executor
from rasl.core.scheduler import FixedRateScheduler, MonotonicClock
from rasl.core.types import Frame
from rasl.core.ports import reset_connections, get_connection_registry
from rasl.nodes.sources.sine import SineSource
from rasl.nodes.transforms.math import ScaleBias
from rasl.nodes.sinks.console import ConsoleSink


class TestEngineExecution:
    """Test complete engine execution with real nodes."""
    
    def setup_method(self):
        """Reset connections before each test."""
        reset_connections()
    
    @pytest.mark.asyncio
    async def test_simple_sine_pipeline_execution(self):
        """
        Test that a simple sine -> scale_bias -> console pipeline executes correctly.
        
        This is the core integration test - if this passes, the fundamental
        engine-executor-connection system is working.
        """
        # Create nodes (use 4 channels to match ScaleBias schema)
        sine = SineSource(freq=1.0, amplitude=1.0, channels=4)
        scaler = ScaleBias(scale=0.5, bias=0.2)
        console = ConsoleSink(format="raw", update_interval=0.0)  # No throttling for test
        
        # Connect nodes using >> operator
        sine >> scaler >> console
        
        # Verify connections were registered
        registry = get_connection_registry()
        edges = registry.get_edges()
        assert len(edges) == 2, f"Expected 2 connections, got {len(edges)}"
        
        # Create executor and register nodes
        executor = Executor()
        executor.register_node(sine)
        executor.register_node(scaler)
        executor.register_node(console)
        
        # Create engine with console as sink
        scheduler = FixedRateScheduler(MonotonicClock(), target_hz=30.0)
        engine = Engine(sinks=[console], scheduler=scheduler, executor=executor)
        
        # Test single frame execution
        await engine.tick_once()
        
        # Verify that data flowed through the pipeline by testing the transform chain
        # Create a test frame and verify the data flow manually
        frame = Frame(t=0.0, dt=0.0, seq=0)
        executor.reset_frame_cache(frame)
        
        # Test that we can materialize the scaler output (which should be sine -> scaler)
        scaler_output_port = scaler.ports["out"]
        result = await executor.materialize(scaler_output_port, frame)
        
        # Verify the result is correctly transformed
        # sine(t=0) = 0, scaled by 0.5 + 0.2 bias = 0.2
        expected = [0.2, 0.2, 0.2, 0.2]  # Four channels
        assert isinstance(result, list), f"Expected list, got {type(result)}"
        assert len(result) == 4, f"Expected 4 channels, got {len(result)}"
        for i, value in enumerate(result):
            assert abs(value - expected[i]) < 1e-6, f"Channel {i}: Expected {expected[i]}, got {value}"
    
    @pytest.mark.asyncio
    async def test_multi_channel_pipeline(self):
        """Test pipeline with multi-channel data flow."""
        # Create multi-channel sine source (4 channels to match ScaleBias)
        sine = SineSource(freq=1.0, amplitude=1.0, channels=4)
        scaler = ScaleBias(scale=2.0, bias=0.0)
        console = ConsoleSink(format="raw", update_interval=0.0)
        
        # Connect pipeline
        sine >> scaler >> console
        
        # Setup executor
        executor = Executor()
        executor.register_node(sine)
        executor.register_node(scaler)
        executor.register_node(console)
        
        # Test materialization
        frame = Frame(t=0.25, dt=0.033, seq=1)  # t=0.25 should give sin(π/2) = 1
        executor.reset_frame_cache(frame)
        
        result = await executor.materialize(scaler.ports["out"], frame)
        
        # All channels should be scaled: sin(π/2) * 2.0 = 2.0
        assert len(result) == 4, f"Expected 4 channels, got {len(result)}"
        for value in result:
            assert abs(value - 2.0) < 1e-6, f"Expected 2.0, got {value}"
    
    @pytest.mark.asyncio
    async def test_connection_error_handling(self):
        """Test that missing connections are handled gracefully."""
        # Create nodes but don't connect them
        sine = SineSource(freq=1.0, channels=1)
        console = ConsoleSink()
        
        executor = Executor()
        executor.register_node(sine)
        executor.register_node(console)
        
        frame = Frame.now(seq=0)
        executor.reset_frame_cache(frame)
        
        # Trying to materialize console input should fail - no connection
        with pytest.raises(Exception):  # Should raise some kind of execution error
            await executor.materialize(console.ports["in"], frame)
    
    @pytest.mark.asyncio
    async def test_node_registration_required(self):
        """Test that nodes must be registered with executor."""
        sine = SineSource(freq=1.0, channels=1)
        
        executor = Executor()
        # Don't register the node
        
        frame = Frame.now(seq=0)
        
        # Should fail because node is not registered
        with pytest.raises(Exception):
            await executor.materialize(sine.ports["out"], frame)
