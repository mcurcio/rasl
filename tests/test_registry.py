"""Unit tests for the node and payload registry."""

import pytest

from rasl.nodes.models import SourceNodeConfig, TransformNodeConfig
from rasl.engine.nodes import BaseNode
from rasl.engine.registry import (
    get_node_class,
    get_node_registry,
    get_payload_type,
    list_node_types,
    list_payload_types,
    node,
    payload,
    reset_registries,
)


@pytest.fixture
def clean_registry():
    """Provide a clean registry state for tests.
    
    Note: We don't actually reset the global registry because that
    breaks class identity for tests that run after this. Instead,
    we just yield and let tests add to the existing registry.
    """
    yield


class TestNodeDecorator:
    """Tests for the @node decorator."""

    def test_node_registers_class(self, clean_registry):
        """Test that @node registers a class with the given name."""

        @node("TestNode")
        class TestNode(BaseNode):
            class Config(SourceNodeConfig):
                pass

            async def start(self, ctx):
                pass

            async def handle(self, port, frame, ctx):
                pass

            async def stop(self, ctx):
                pass

        assert get_node_class("TestNode") is TestNode

    def test_node_registers_aliases(self, clean_registry):
        """Test that @node registers aliases."""

        @node("TestNodeFull", "TestNode", "TN")
        class TestNodeFull(BaseNode):
            class Config(SourceNodeConfig):
                pass

            async def start(self, ctx):
                pass

            async def handle(self, port, frame, ctx):
                pass

            async def stop(self, ctx):
                pass

        assert get_node_class("TestNodeFull") is TestNodeFull
        assert get_node_class("TestNode") is TestNodeFull
        assert get_node_class("TN") is TestNodeFull

    def test_node_requires_config_class(self, clean_registry):
        """Test that @node raises TypeError if Config is missing."""
        with pytest.raises(TypeError, match="must define a nested Config class"):

            @node("BadNode")
            class BadNode:
                pass

    def test_get_node_class_returns_none_for_unknown(self, clean_registry):
        """Test that get_node_class returns None for unknown types."""
        assert get_node_class("UnknownNode") is None

    def test_list_node_types(self, clean_registry):
        """Test that list_node_types returns registered names."""

        @node("AlphaNode")
        class AlphaNode(BaseNode):
            class Config(SourceNodeConfig):
                pass

            async def start(self, ctx):
                pass

            async def handle(self, port, frame, ctx):
                pass

            async def stop(self, ctx):
                pass

        @node("BetaNode", "Beta")
        class BetaNode(BaseNode):
            class Config(TransformNodeConfig):
                pass

            async def start(self, ctx):
                pass

            async def handle(self, port, frame, ctx):
                pass

            async def stop(self, ctx):
                pass

        types = list_node_types()
        assert "AlphaNode" in types
        assert "BetaNode" in types
        assert "Beta" in types

    def test_get_node_registry(self, clean_registry):
        """Test that get_node_registry returns a copy."""

        @node("RegistryTestNode")
        class RegistryTestNode(BaseNode):
            class Config(SourceNodeConfig):
                pass

            async def start(self, ctx):
                pass

            async def handle(self, port, frame, ctx):
                pass

            async def stop(self, ctx):
                pass

        registry = get_node_registry()
        assert "RegistryTestNode" in registry
        # Modifying the copy shouldn't affect the original
        registry.clear()
        assert get_node_class("RegistryTestNode") is RegistryTestNode


class TestPayloadDecorator:
    """Tests for the @payload decorator."""

    def test_payload_registers_class(self, clean_registry):
        """Test that @payload registers a class with the given name."""

        @payload("test_payload")
        class TestPayload:
            pass

        assert get_payload_type("test_payload") is TestPayload

    def test_get_payload_type_returns_none_for_unknown(self, clean_registry):
        """Test that get_payload_type returns None for unknown types."""
        assert get_payload_type("unknown_payload") is None

    def test_list_payload_types(self, clean_registry):
        """Test that list_payload_types returns registered names."""

        @payload("payload_a")
        class PayloadA:
            pass

        @payload("payload_b")
        class PayloadB:
            pass

        types = list_payload_types()
        assert "payload_a" in types
        assert "payload_b" in types


class TestBuiltinPayloads:
    """Tests for built-in payload registration."""

    def test_array_payload_registered(self):
        """Test that 'array' payload type is registered when frame module is imported."""
        # Just import frame - don't reload as that breaks class identity
        import rasl.engine.frames  # noqa: F401

        assert get_payload_type("array") is not None

    def test_color_payloads_registered(self):
        """Test that color payloads are registered."""
        import rasl.engine.frames  # noqa: F401

        assert get_payload_type("color") is not None
        assert get_payload_type("rgb") is None
        assert get_payload_type("hsl") is None
        assert get_payload_type("color:rgb") is not None
        assert get_payload_type("color:hsl") is not None
