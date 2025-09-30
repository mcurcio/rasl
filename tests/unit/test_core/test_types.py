"""
Tests for core type definitions.
"""

import pytest
import time
from rasl.core.types import (
    Frame, Range, RangeRule, Channel, Component, Schema,
    NodeState, NodeStatus, RGB_SCHEMA, HSV_SCHEMA, SCALAR_SCHEMA
)


class TestFrame:
    """Test Frame class functionality."""
    
    def test_frame_creation(self):
        """Test basic frame creation."""
        frame = Frame(t=1.5, dt=0.033, seq=45)
        assert frame.t == 1.5
        assert frame.dt == 0.033
        assert frame.seq == 45
    
    def test_frame_now(self):
        """Test Frame.now() class method."""
        start_time = time.perf_counter()
        frame1 = Frame.now(seq=1)
        frame2 = Frame.now(seq=2, last_time=frame1.t)
        
        assert frame1.seq == 1
        assert frame2.seq == 2
        assert frame1.dt == 0.0  # First frame has no delta
        assert frame2.dt > 0.0   # Second frame has positive delta
        assert frame2.t > frame1.t
        assert frame1.t >= start_time


class TestRange:
    """Test Range class and normalization."""
    
    def test_default_range(self):
        """Test default range [0,1] with clip rule."""
        r = Range()
        assert r.min == 0.0
        assert r.max == 1.0
        assert r.rule == RangeRule.CLIP
    
    def test_clip_normalization(self):
        """Test clipping normalization."""
        r = Range(min=0.0, max=1.0, rule=RangeRule.CLIP)
        
        assert r.normalize(0.5) == 0.5  # In range
        assert r.normalize(-0.5) == 0.0  # Below range
        assert r.normalize(1.5) == 1.0   # Above range
    
    def test_wrap_normalization(self):
        """Test wrapping normalization (for hue)."""
        r = Range(min=0.0, max=1.0, rule=RangeRule.WRAP)
        
        assert r.normalize(0.5) == 0.5   # In range
        assert r.normalize(1.5) == 0.5   # Wraps around
        assert r.normalize(-0.3) == 0.7  # Negative wrap
        assert r.normalize(2.2) == 0.2   # Multiple wraps
    
    def test_error_normalization(self):
        """Test error normalization."""
        r = Range(min=0.0, max=1.0, rule=RangeRule.ERROR)
        
        assert r.normalize(0.5) == 0.5  # In range is fine
        
        with pytest.raises(ValueError, match="outside range"):
            r.normalize(1.5)
        
        with pytest.raises(ValueError, match="outside range"):
            r.normalize(-0.5)


class TestChannel:
    """Test Channel class."""
    
    def test_channel_creation(self):
        """Test basic channel creation."""
        ch = Channel("red", "unitless", Range(0.0, 1.0))
        assert ch.id == "red"
        assert ch.units == "unitless"
        assert ch.range.min == 0.0
        assert ch.range.max == 1.0
    
    def test_channel_defaults(self):
        """Test channel with default values."""
        ch = Channel("hue")
        assert ch.id == "hue"
        assert ch.units is None
        assert ch.range.min == 0.0
        assert ch.range.max == 1.0
        assert ch.range.rule == RangeRule.CLIP


class TestComponent:
    """Test Component class."""
    
    def test_component_creation(self):
        """Test basic component creation."""
        channels = (
            Channel("r", "unitless", Range(0.0, 1.0)),
            Channel("g", "unitless", Range(0.0, 1.0)),
            Channel("b", "unitless", Range(0.0, 1.0)),
        )
        
        comp = Component(
            name="Color",
            flavor="linear_srgb", 
            channels=channels,
            colorspace="linear_srgb"
        )
        
        assert comp.name == "Color"
        assert comp.flavor == "linear_srgb"
        assert len(comp.channels) == 3
        assert comp.colorspace == "linear_srgb"
    
    def test_component_defaults(self):
        """Test component with default values."""
        comp = Component("Vector")
        assert comp.name == "Vector"
        assert comp.flavor is None
        assert comp.channels == ()
        assert comp.colorspace is None


class TestSchema:
    """Test Schema class and compatibility."""
    
    def test_schema_creation(self):
        """Test basic schema creation."""
        comp = Component(
            name="Test",
            channels=(Channel("a"), Channel("b"))
        )
        schema = Schema(components=(comp,))
        
        assert len(schema.components) == 1
        assert schema.components[0].name == "Test"
    
    def test_channel_count(self):
        """Test channel counting across components."""
        comp1 = Component("RGB", channels=(Channel("r"), Channel("g"), Channel("b")))
        comp2 = Component("Alpha", channels=(Channel("a"),))
        
        schema = Schema(components=(comp1, comp2))
        assert schema.channel_count() == 4
    
    def test_channel_names(self):
        """Test getting flat channel names."""
        comp = Component(
            "Color",
            channels=(Channel("r"), Channel("g"), Channel("b"))
        )
        schema = Schema(components=(comp,))
        
        names = schema.get_channel_names()
        assert names == ["Color.r", "Color.g", "Color.b"]
    
    def test_schema_compatibility(self):
        """Test schema compatibility checking."""
        # Same schemas should be compatible
        comp = Component("Test", channels=(Channel("a"), Channel("b")))
        schema1 = Schema(components=(comp,))
        schema2 = Schema(components=(comp,))
        
        assert schema1.is_compatible(schema2)
        assert schema2.is_compatible(schema1)
        
        # Different schemas should not be compatible
        comp_different = Component("Test", channels=(Channel("x"), Channel("y")))
        schema3 = Schema(components=(comp_different,))
        
        assert not schema1.is_compatible(schema3)


class TestNodeStatus:
    """Test NodeStatus tracking."""
    
    def test_initial_status(self):
        """Test initial node status."""
        status = NodeStatus()
        assert status.state == NodeState.HEALTHY
        assert status.last_error is None
        assert status.error_count == 0
        assert status.total_evaluations == 0
        assert status.avg_eval_time == 0.0
    
    def test_update_success(self):
        """Test successful evaluation update."""
        status = NodeStatus()
        status.update_success(eval_time=0.001, frame_time=1.0)
        
        assert status.state == NodeState.HEALTHY
        assert status.last_success == 1.0
        assert status.total_evaluations == 1
        assert status.error_count == 0
        assert status.avg_eval_time > 0.0
    
    def test_update_error(self):
        """Test error handling."""
        status = NodeStatus()
        error = ValueError("Test error")
        
        # First error -> RECOVERING
        status.update_error(error)
        assert status.state == NodeState.RECOVERING
        assert status.last_error == error
        assert status.error_count == 1
        
        # Third error -> FAILED
        status.update_error(error)
        status.update_error(error)
        assert status.state == NodeState.FAILED
        assert status.error_count == 3
    
    def test_error_recovery(self):
        """Test recovery after errors."""
        status = NodeStatus()
        error = ValueError("Test error")
        
        # Generate some errors
        status.update_error(error)
        status.update_error(error)
        assert status.state == NodeState.RECOVERING
        
        # Success should reset error count
        status.update_success(eval_time=0.001, frame_time=1.0)
        assert status.state == NodeState.HEALTHY
        assert status.error_count == 0


class TestBuiltinSchemas:
    """Test predefined schema constants."""
    
    def test_rgb_schema(self):
        """Test RGB schema definition."""
        assert len(RGB_SCHEMA.components) == 1
        comp = RGB_SCHEMA.components[0]
        assert comp.name == "Color"
        assert comp.flavor == "linear_srgb"
        assert len(comp.channels) == 3
        
        channel_ids = [ch.id for ch in comp.channels]
        assert channel_ids == ["r", "g", "b"]
    
    def test_hsv_schema(self):
        """Test HSV schema definition."""
        assert len(HSV_SCHEMA.components) == 1
        comp = HSV_SCHEMA.components[0]
        assert comp.name == "Color"
        assert comp.flavor == "HSV"
        assert len(comp.channels) == 3
        
        channel_ids = [ch.id for ch in comp.channels]
        assert channel_ids == ["h", "s", "v"]
        
        # Hue should wrap
        hue_channel = comp.channels[0]
        assert hue_channel.range.rule == RangeRule.WRAP
    
    def test_scalar_schema(self):
        """Test scalar schema definition."""
        assert len(SCALAR_SCHEMA.components) == 1
        comp = SCALAR_SCHEMA.components[0]
        assert comp.name == "Scalar"
        assert len(comp.channels) == 1
        assert comp.channels[0].id == "value"
