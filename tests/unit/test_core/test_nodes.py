"""
Tests for base node classes and functionality.
"""

import pytest
from rasl.core.nodes import BaseNode, BaseSource, BaseTransform, BaseSink
from rasl.core.types import Frame, Liveness, Schema
from rasl.core.ports import PortRef


class TestBaseNode:
    """Test BaseNode functionality."""
    
    def test_node_creation(self):
        """Test basic node creation."""
        node = BaseNode()
        assert node.id.startswith("basenode_")
        assert len(node.id) == 17  # "basenode_" + 8 hex chars
        assert node.KIND == "base"
        assert node.TYPE == "BaseNode"
    
    def test_node_with_custom_id(self):
        """Test node creation with custom ID."""
        node = BaseNode(id="custom_node")
        assert node.id == "custom_node"
    
    def test_node_parameters(self):
        """Test parameter management."""
        # BaseNode has no parameters by default
        node = BaseNode()
        assert node.param_spec() == {}
        assert node.get_params() == {}
        
        # Setting unknown parameter should fail
        with pytest.raises(ValueError, match="Unknown parameter"):
            node.set_params(unknown_param=123)
    
    def test_ports_property(self):
        """Test ports property access."""
        node = BaseNode()
        ports = node.ports
        assert ports is not None
        
        # Should return same instance on repeated access
        assert node.ports is ports


class TestParameterizedNode(BaseNode):
    """Test node with parameters for testing parameter system."""
    
    TYPE = "TestParameterizedNode"
    
    def param_spec(self):
        return {
            "scale": {"type": "float", "default": 1.0, "min": 0.0, "max": 10.0},
            "offset": {"type": "float", "default": 0.0},
            "name": {"type": "str", "default": "test"}
        }


class TestNodeParameters:
    """Test parameter system with a parameterized node."""
    
    def test_parameter_initialization(self):
        """Test parameter initialization during construction."""
        node = TestParameterizedNode(scale=2.5, name="custom")
        params = node.get_params()
        assert params["scale"] == 2.5
        assert params["name"] == "custom"
    
    def test_parameter_updates(self):
        """Test runtime parameter updates."""
        node = TestParameterizedNode()
        
        node.set_params(scale=3.0, offset=1.5)
        params = node.get_params()
        assert params["scale"] == 3.0
        assert params["offset"] == 1.5
    
    def test_invalid_parameter(self):
        """Test handling of invalid parameters."""
        node = TestParameterizedNode()
        
        with pytest.raises(ValueError, match="Unknown parameter"):
            node.set_params(invalid_param=123)


class TestSource(BaseSource):
    """Concrete test source for testing."""
    
    TYPE = "TestSource"
    LIVENESS = Liveness.STREAM
    
    def __init__(self, *, frequency: float = 1.0, **kwargs):
        super().__init__(**kwargs)
        self.frequency = frequency
    
    def sample(self, frame: Frame):
        # Generate simple sine-like data
        import math
        value = math.sin(2 * math.pi * self.frequency * frame.t)
        return {"out": [value]}
    
    def param_spec(self):
        return {
            "frequency": {"type": "float", "default": 1.0, "min": 0.1, "max": 100.0}
        }


class TestBaseSource:
    """Test BaseSource functionality."""
    
    def test_source_creation(self):
        """Test source node creation."""
        source = TestSource(frequency=2.0)
        assert source.KIND == "source"
        assert source.LIVENESS == Liveness.STREAM
        assert source.frequency == 2.0
    
    def test_source_lifecycle(self):
        """Test source open/close lifecycle."""
        source = TestSource()
        
        # Default implementations should not raise
        source.open()
        source.close()
    
    def test_source_sampling(self):
        """Test source data generation."""
        source = TestSource(frequency=1.0)
        frame = Frame(t=0.0, dt=0.033, seq=0)
        
        data = source.sample(frame)
        assert "out" in data
        assert len(data["out"]) == 1
        assert isinstance(data["out"][0], float)
    
    def test_source_duration(self):
        """Test duration for finite sources."""
        source = TestSource()
        # Base implementation returns None (infinite/stream)
        assert source.duration_seconds() is None


class TestTransform(BaseTransform):
    """Concrete test transform for testing."""
    
    TYPE = "TestTransform"
    
    def __init__(self, *, gain: float = 1.0, **kwargs):
        super().__init__(**kwargs)
        self.gain = gain
    
    def evaluate(self, frame: Frame, **inputs):
        if "in" not in inputs:
            raise ValueError("Missing required input 'in'")
        
        input_data = inputs["in"]
        output_data = [x * self.gain for x in input_data]
        return {"out": output_data}
    
    def param_spec(self):
        return {
            "gain": {"type": "float", "default": 1.0, "min": 0.0, "max": 10.0}
        }


class TestBaseTransform:
    """Test BaseTransform functionality."""
    
    def test_transform_creation(self):
        """Test transform node creation."""
        transform = TestTransform(gain=2.0)
        assert transform.KIND == "transform"
        assert transform.gain == 2.0
    
    def test_transform_evaluation(self):
        """Test transform data processing."""
        transform = TestTransform(gain=2.0)
        frame = Frame(t=1.0, dt=0.033, seq=30)
        
        result = transform.evaluate(frame, **{"in": [0.5, 0.8, 0.2]})
        assert "out" in result
        assert result["out"] == [1.0, 1.6, 0.4]
    
    def test_transform_missing_input(self):
        """Test transform with missing required input."""
        transform = TestTransform()
        frame = Frame(t=1.0, dt=0.033, seq=30)
        
        with pytest.raises(ValueError, match="Missing required input"):
            transform.evaluate(frame)


class TestSink(BaseSink):
    """Concrete test sink for testing."""
    
    TYPE = "TestSink"
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.received_data = []
        self.received_frames = []
    
    def emit(self, frame: Frame, **inputs):
        self.received_frames.append(frame)
        self.received_data.append(dict(inputs))


class TestBaseSink:
    """Test BaseSink functionality."""
    
    def test_sink_creation(self):
        """Test sink node creation."""
        sink = TestSink()
        assert sink.KIND == "sink"
    
    def test_sink_emission(self):
        """Test sink data consumption."""
        sink = TestSink()
        frame = Frame(t=1.0, dt=0.033, seq=30)
        
        sink.emit(frame, **{"in": [0.1, 0.2, 0.3]})
        
        assert len(sink.received_frames) == 1
        assert sink.received_frames[0] == frame
        assert len(sink.received_data) == 1
        assert sink.received_data[0] == {"in": [0.1, 0.2, 0.3]}
    
    def test_sink_required_rate(self):
        """Test sink rate requirements."""
        sink = TestSink()
        # Base implementation returns None (no requirements)
        assert sink.required_rate() is None


class TestNodeProtocols:
    """Test that nodes implement the expected protocols."""
    
    def test_source_protocol(self):
        """Test that BaseSource implements Source protocol."""
        from rasl.core.nodes import Source
        
        source = TestSource()
        assert isinstance(source, Source)
    
    def test_transform_protocol(self):
        """Test that BaseTransform implements Transform protocol."""
        from rasl.core.nodes import Transform
        
        transform = TestTransform()
        assert isinstance(transform, Transform)
    
    def test_sink_protocol(self):
        """Test that BaseSink implements Sink protocol."""
        from rasl.core.nodes import Sink
        
        sink = TestSink()
        assert isinstance(sink, Sink)
