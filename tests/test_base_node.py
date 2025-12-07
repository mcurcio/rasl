"""Unit tests for the BaseNode abstract base class."""

import pytest
from pydantic import Field

from rasl.config.models import BaseNodeConfig, SourceNodeConfig, TransformNodeConfig
from rasl.engine.base_node import BaseNode


class TestBaseNodeConfig:
    """Tests for base config models."""

    def test_base_node_config_requires_id(self):
        """Test that BaseNodeConfig requires an id."""
        with pytest.raises(Exception):  # Pydantic ValidationError
            BaseNodeConfig()

    def test_base_node_config_with_id(self):
        """Test that BaseNodeConfig accepts an id."""
        config = BaseNodeConfig(id="test_node")
        assert config.id == "test_node"
        assert config.metadata == {}

    def test_base_node_config_with_metadata(self):
        """Test that BaseNodeConfig accepts metadata."""
        config = BaseNodeConfig(id="test", metadata={"key": "value"})
        assert config.metadata == {"key": "value"}

    def test_base_node_config_is_frozen(self):
        """Test that BaseNodeConfig is immutable."""
        config = BaseNodeConfig(id="test")
        with pytest.raises(Exception):  # Pydantic frozen model error
            config.id = "changed"

    def test_base_node_config_rejects_extra_fields(self):
        """Test that BaseNodeConfig rejects unknown fields."""
        with pytest.raises(Exception):  # Pydantic ValidationError
            BaseNodeConfig(id="test", unknown_field="value")


class TestSourceNodeConfig:
    """Tests for SourceNodeConfig."""

    def test_source_node_config_defaults(self):
        """Test SourceNodeConfig default values."""
        config = SourceNodeConfig(id="source")
        assert config.kind == "source"
        assert config.fps is None

    def test_source_node_config_with_fps(self):
        """Test SourceNodeConfig with fps."""
        config = SourceNodeConfig(id="source", fps=30.0)
        assert config.fps == 30.0

    def test_source_node_config_fps_validation(self):
        """Test SourceNodeConfig fps range validation."""
        # Too low
        with pytest.raises(Exception):
            SourceNodeConfig(id="source", fps=0.05)
        # Too high
        with pytest.raises(Exception):
            SourceNodeConfig(id="source", fps=1001)


class TestTransformNodeConfig:
    """Tests for TransformNodeConfig."""

    def test_transform_node_config_defaults(self):
        """Test TransformNodeConfig default values."""
        config = TransformNodeConfig(id="transform")
        assert config.kind == "transform"


class TestBaseNode:
    """Tests for BaseNode ABC."""

    def test_base_node_sets_id(self):
        """Test that BaseNode.__init__ sets id from config."""

        class TestNode(BaseNode):
            class Config(SourceNodeConfig):
                pass

            async def start(self, ctx):
                pass

            async def handle(self, port, frame, ctx):
                pass

            async def stop(self, ctx):
                pass

        config = TestNode.Config(id="my_node")
        node = TestNode(config)
        assert node.id == "my_node"

    def test_base_node_sets_metadata(self):
        """Test that BaseNode.__init__ sets metadata from config."""

        class TestNode(BaseNode):
            class Config(SourceNodeConfig):
                pass

            async def start(self, ctx):
                pass

            async def handle(self, port, frame, ctx):
                pass

            async def stop(self, ctx):
                pass

        config = TestNode.Config(id="my_node", metadata={"foo": "bar"})
        node = TestNode(config)
        assert node._metadata == {"foo": "bar"}

    def test_subclass_can_add_config_fields(self):
        """Test that subclasses can add custom config fields."""

        class CustomNode(BaseNode):
            class Config(SourceNodeConfig):
                custom_param: float = Field(1.0, ge=0.0)
                required_param: str

            async def start(self, ctx):
                pass

            async def handle(self, port, frame, ctx):
                pass

            async def stop(self, ctx):
                pass

        config = CustomNode.Config(
            id="custom",
            custom_param=2.5,
            required_param="hello",
        )
        assert config.custom_param == 2.5
        assert config.required_param == "hello"

    def test_subclass_config_inherits_validation(self):
        """Test that subclass Config inherits base validation."""

        class CustomNode(BaseNode):
            class Config(SourceNodeConfig):
                value: int = Field(0, ge=0, le=100)

            async def start(self, ctx):
                pass

            async def handle(self, port, frame, ctx):
                pass

            async def stop(self, ctx):
                pass

        # Valid
        config = CustomNode.Config(id="test", value=50)
        assert config.value == 50

        # Invalid - out of range
        with pytest.raises(Exception):
            CustomNode.Config(id="test", value=101)

    def test_config_json_schema_export(self):
        """Test that Config can export JSON schema."""

        class SchemaNode(BaseNode):
            class Config(SourceNodeConfig):
                frequency: float = Field(1.0, description="Frequency in Hz")

            async def start(self, ctx):
                pass

            async def handle(self, port, frame, ctx):
                pass

            async def stop(self, ctx):
                pass

        schema = SchemaNode.Config.model_json_schema()
        assert "properties" in schema
        assert "frequency" in schema["properties"]
        assert schema["properties"]["frequency"]["description"] == "Frequency in Hz"
