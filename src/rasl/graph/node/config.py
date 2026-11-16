"""Base configuration models for RASL nodes.

All node Config classes inherit from these bases, which provide
common fields and validation. The hierarchy is:

    BaseNodeConfig
    ├── SourceNodeConfig   (for source nodes)
    ├── TransformNodeConfig (for transform nodes)
    └── SinkNodeConfig     (for sink nodes)

Nodes define their own ports via PortGroup attributes, not in config.
Config models only contain user-configurable parameters.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from rasl.units import Frequency


class BaseNodeConfig(BaseModel):

    """Base configuration shared by all nodes.

    Attributes:
        id: Unique node identifier within the graph.
        metadata: Optional key-value metadata attached to frames.
        max_consecutive_errors: Disable this node after this many failed pulls in a
            row; 0 means never. None (the default) uses the config's
            ``runtime { max_consecutive_errors N; }``, itself 10 by default.
    """

    model_config = ConfigDict(
        extra="forbid",  # Reject unknown fields
        frozen=True,  # Immutable after creation
    )

    id: str = Field(..., description="Unique node identifier")
    metadata: dict[str, str] = Field(default_factory=dict)
    max_consecutive_errors: int | None = Field(None, ge=0)

    @classmethod
    def from_positional(cls, words: Sequence[str], written: Sequence[str]) -> dict[str, Any]:
        """Settings given on the node's own line, after its type and name.

        ``node Color warm oklch { ... }`` has one such value, ``oklch``. A node
        type that takes values there overrides this in its Config and returns
        them as settings, by field name; they are validated with the rest.

        Args:
            words: Each value as a plain word (quotes removed).
            written: Each value as the config wrote it (a list keeps its
                brackets, a string its quotes).

        Returns:
            Settings to add to the node's config.

        Raises:
            ValueError: If the values are not what this node type takes. The
                message is shown at the node's line in the config.
        """
        if words:
            raise ValueError("this node type takes no values after its name")
        return {}


class SourceNodeConfig(BaseNodeConfig):
    """Base configuration for source nodes.

    Source nodes produce frames on output ports. They typically
    have timing configuration to control frame rate.

    Subclasses should add their own parameters. Port definitions
    are handled via PortGroup class attributes, not config.
    """

    kind: Literal["source"] = "source"
    fps: Frequency | None = Field(None, description="Output frame rate (e.g. '30', '30hz')")

    @field_validator("fps")
    @classmethod
    def _fps_in_range(cls, value: Frequency | None) -> Frequency | None:
        if value is not None and not 0.1 <= value.hz <= 1000:
            raise ValueError(f"fps must be between 0.1hz and 1000hz (got {value})")
        return value


class TransformNodeConfig(BaseNodeConfig):
    """Base configuration for transform nodes.

    Transform nodes receive frames on input ports, process them,
    and emit results on output ports.

    Subclasses should add their own parameters. Port definitions
    are handled via PortGroup class attributes, not config.
    """

    kind: Literal["transform"] = "transform"


class SinkNodeConfig(BaseNodeConfig):
    """Base configuration for sink nodes.

    Sink nodes consume frames from input ports and write to
    external targets (network, console, etc.).

    Subclasses should add their own parameters. Port definitions
    are handled via PortGroup class attributes, not config.
    """

    kind: Literal["sink"] = "sink"
