"""
Pytest configuration and shared fixtures for RASL tests.
"""

import pytest
import asyncio
from pathlib import Path
from typing import Generator

from rasl.core.types import Frame, Schema, Component, Channel, Range
from rasl.core.ports import reset_connections
from rasl.core.nodes import BaseSource, BaseTransform, BaseSink


@pytest.fixture(autouse=True)
def reset_global_state():
    """Reset global state before each test."""
    reset_connections()
    yield
    reset_connections()


@pytest.fixture
def sample_frame() -> Frame:
    """Create a sample frame for testing."""
    return Frame(t=1.0, dt=0.033, seq=30)


@pytest.fixture
def simple_schema() -> Schema:
    """Create a simple test schema."""
    return Schema(components=(
        Component(
            name="Test",
            channels=(
                Channel("a", "unitless", Range(0.0, 1.0)),
                Channel("b", "unitless", Range(0.0, 1.0)),
            )
        ),
    ))


@pytest.fixture
def rgb_schema() -> Schema:
    """Create RGB color schema for testing."""
    return Schema(components=(
        Component(
            name="Color",
            flavor="linear_srgb",
            channels=(
                Channel("r", "unitless", Range(0.0, 1.0)),
                Channel("g", "unitless", Range(0.0, 1.0)),
                Channel("b", "unitless", Range(0.0, 1.0)),
            ),
            colorspace="linear_srgb"
        ),
    ))


class TestSource(BaseSource):
    """Test source node that generates predictable data."""
    
    TYPE = "TestSource"
    
    def __init__(self, *, value: float = 0.5, channels: int = 1, **kwargs):
        super().__init__(**kwargs)
        self.value = value
        self.channels = channels
    
    def sample(self, frame: Frame):
        return {"out": [self.value] * self.channels}
    
    def port_schema(self, name: str) -> Schema:
        if name == "out":
            return Schema(components=(
                Component(
                    name="Test",
                    channels=tuple(
                        Channel(f"ch{i}", "unitless", Range(0.0, 1.0))
                        for i in range(self.channels)
                    )
                ),
            ))
        raise ValueError(f"Unknown port: {name}")


class TestTransform(BaseTransform):
    """Test transform that scales input by a factor."""
    
    TYPE = "TestTransform"
    
    def __init__(self, *, scale: float = 2.0, **kwargs):
        super().__init__(**kwargs)
        self.scale = scale
    
    def evaluate(self, frame: Frame, **inputs):
        if "in" not in inputs:
            raise ValueError("TestTransform requires 'in' input")
        
        input_data = inputs["in"]
        output_data = [x * self.scale for x in input_data]
        return {"out": output_data}
    
    def port_schema(self, name: str) -> Schema:
        # Same schema for input and output
        return Schema(components=(
            Component(
                name="Test",
                channels=(Channel("value", "unitless", Range(0.0, 1.0)),)
            ),
        ))


class TestSink(BaseSink):
    """Test sink that captures emitted data."""
    
    TYPE = "TestSink"
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.captured_data = []
        self.captured_frames = []
    
    def emit(self, frame: Frame, **inputs):
        self.captured_frames.append(frame)
        self.captured_data.append(dict(inputs))
    
    def port_schema(self, name: str) -> Schema:
        if name == "in":
            return Schema(components=(
                Component(
                    name="Test", 
                    channels=(Channel("value", "unitless", Range(0.0, 1.0)),)
                ),
            ))
        raise ValueError(f"Unknown port: {name}")


@pytest.fixture
def test_source() -> TestSource:
    """Create a test source node."""
    return TestSource(value=0.8, channels=3)


@pytest.fixture
def test_transform() -> TestTransform:
    """Create a test transform node."""
    return TestTransform(scale=0.5)


@pytest.fixture
def test_sink() -> TestSink:
    """Create a test sink node."""
    return TestSink()


@pytest.fixture
def temp_script_file(tmp_path: Path) -> Path:
    """Create a temporary script file for testing."""
    script_content = '''
from rasl import *

# Simple test script
source = SineSource(freq=1.0, channels=4)
sink = ConsoleSink()

source >> sink
'''
    
    script_path = tmp_path / "test_script.py"
    script_path.write_text(script_content)
    return script_path


@pytest.fixture
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create an event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
