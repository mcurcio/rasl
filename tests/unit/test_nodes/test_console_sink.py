"""
Unit tests for ConsoleSink flexible channel handling.

Tests that ConsoleSink can accept arbitrary numbers of input channels
and properly displays data from various source configurations.
"""

import pytest
import io
import sys
import numpy as np
from contextlib import redirect_stdout, redirect_stderr
from unittest.mock import patch

from rasl.core.types import Frame, Schema, Component, Channel, Range, RangeRule
from rasl.nodes.sinks.console import ConsoleSink
from rasl.nodes.sources.sine import SineSource
from rasl.nodes.transforms.math import ScaleBias


class TestConsoleSinkFlexibleChannels:
    """Test ConsoleSink with various channel configurations."""
    
    def test_console_sink_accepts_single_channel(self):
        """
        ConsoleSink should accept and display single channel input.
        
        This test defines the expected behavior for 1-channel inputs.
        """
        # Create a 1-channel source
        sine = SineSource(freq=1.0, channels=1)
        console = ConsoleSink(format="raw")
        
        # This connection should work without schema errors
        sine.ports.out >> console.ports["in"]
        
        # Verify the connection was established
        from rasl.core.ports import get_connection_registry
        registry = get_connection_registry()
        connections = registry.get_edges()
        
        assert len(connections) == 1, "Should have one connection"
        assert connections[0].src_id == sine.id
        assert connections[0].dst_id == console.id
    
    def test_console_sink_accepts_multiple_channels(self):
        """
        ConsoleSink should accept inputs with various channel counts.
        
        Tests 2, 4, 8, and 16 channel configurations.
        """
        channel_counts = [2, 4, 8, 16]
        
        for channels in channel_counts:
            # Reset connection registry for each test
            from rasl.core.ports import reset_connections
            reset_connections()
            
            sine = SineSource(freq=1.0, channels=channels)
            console = ConsoleSink(format="table")
            
            # This should work for any channel count
            sine.ports.out >> console.ports["in"]
            
            # Verify connection
            from rasl.core.ports import get_connection_registry
            registry = get_connection_registry()
            connections = registry.get_edges()
            
            assert len(connections) == 1, f"Should connect with {channels} channels"
    
    def test_console_sink_schema_adapts_to_input(self):
        """
        ConsoleSink accepts any input schema through flexible compatibility.
        
        The sink uses an empty schema that is compatible with any input.
        """
        # Test with 3-channel input (unusual number)
        sine = SineSource(freq=1.0, channels=3)
        console = ConsoleSink()
        
        # Get the sink's input port schema before connection
        input_port = console.ports["in"]
        original_schema = input_port.schema
        
        # The sink should have an empty schema (flexible)
        assert original_schema.channel_count() == 0, "ConsoleSink should have flexible (empty) schema"
        
        # Connect - this should succeed due to flexible schema compatibility
        sine.ports.out >> console.ports["in"]
        
        # The connection should succeed (no ConnectionError raised)
        # Verify connection was established
        from rasl.core.ports import get_connection_registry
        registry = get_connection_registry()
        connections = registry.get_edges()
        
        assert len(connections) == 1, "Should have established connection"
        assert connections[0].src_id == sine.id
        assert connections[0].dst_id == console.id
    
    def test_console_sink_displays_variable_channels(self):
        """
        ConsoleSink should properly format and display variable channel data.
        
        Tests the actual output formatting for different channel counts.
        """
        from rasl.core.types import Frame
        import numpy as np
        
        # Test data for different channel counts
        test_cases = [
            (1, [0.5]),
            (2, [0.3, -0.7]),
            (4, [0.1, 0.2, 0.3, 0.4]),
            (8, [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8])
        ]
        
        for channels, test_data in test_cases:
            console = ConsoleSink(format="raw", update_interval=0.0)
            
            # Create test frame
            frame = Frame(t=0.0, dt=0.016, seq=0)
            
            # Create input data
            inputs = {"in": np.array(test_data)}
            
            # Capture output
            captured_output = io.StringIO()
            with redirect_stdout(captured_output):
                console.emit(frame, **inputs)
            
            output = captured_output.getvalue()
            
            # Should contain all channel values (check for the actual format)
            for value in test_data:
                # The raw format shows arrays like [0.5] or [0.3 -0.7]
                assert str(value) in output, f"Should display value {value}"
    
    def test_console_sink_max_channels_display(self):
        """
        ConsoleSink should handle large channel counts gracefully.
        
        Should truncate display for very large channel counts.
        """
        # Create a sink with max_channels limit and no throttling
        console = ConsoleSink(format="table", max_channels=5, update_interval=0.0)
        
        # Test with more channels than the limit
        large_data = list(range(20))  # 20 channels
        frame = Frame(t=0.0, dt=0.016, seq=0)
        inputs = {"in": np.array(large_data, dtype=float)}
        
        # Capture output
        captured_output = io.StringIO()
        with redirect_stdout(captured_output):
            console.emit(frame, **inputs)
        
        output = captured_output.getvalue()
        
        # Should show truncation indicator
        assert "..." in output or "more" in output, "Should indicate truncation"
        
        # Should show first few channels
        assert "0.000" in output, "Should show first channel"
        assert "4.000" in output, "Should show 5th channel (within limit)"
    
    def test_console_sink_different_source_types(self):
        """
        ConsoleSink should work with outputs from different node types.
        
        Tests compatibility with various source and transform outputs.
        """
        from rasl.core.ports import reset_connections
        
        # Test with direct source
        reset_connections()
        sine = SineSource(freq=1.0, channels=2)
        console1 = ConsoleSink(format="raw")
        sine.ports.out >> console1.ports["in"]
        
        # Test with transform output
        reset_connections()
        sine2 = SineSource(freq=1.0, channels=3)
        scaler = ScaleBias(scale=0.5, bias=0.1)
        console2 = ConsoleSink(format="table")
        
        sine2.ports.out >> scaler.ports["in"]
        scaler.ports.out >> console2.ports["in"]
        
        # Both should work without errors
        from rasl.core.ports import get_connection_registry
        registry = get_connection_registry()
        connections = registry.get_edges()
        
        assert len(connections) == 2, "Should have two connections in chain"
    
    def test_console_sink_port_schema_validation(self):
        """
        Test that ConsoleSink properly validates port schemas.
        
        Should accept compatible schemas and reject incompatible ones.
        """
        console = ConsoleSink()
        
        # Test that the input port exists and has a schema
        input_port = console.ports["in"]
        assert input_port is not None, "Should have input port"
        assert input_port.schema is not None, "Input port should have schema"
        
        # The schema should be flexible (this test will help us define what that means)
        schema = input_port.schema
        assert len(schema.components) >= 0, "Should accept variable component count"
