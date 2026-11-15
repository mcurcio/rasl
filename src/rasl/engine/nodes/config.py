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

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class BaseNodeConfig(BaseModel):
    """Base configuration shared by all nodes.

    Attributes:
        id: Unique node identifier within the graph.
        metadata: Optional key-value metadata attached to frames.
    """

    model_config = ConfigDict(
        extra="forbid",  # Reject unknown fields
        frozen=True,  # Immutable after creation
    )

    id: str = Field(..., description="Unique node identifier")
    metadata: dict[str, str] = Field(default_factory=dict)


class SourceNodeConfig(BaseNodeConfig):
    """Base configuration for source nodes.

    Source nodes produce frames on output ports. They typically
    have timing configuration to control frame rate.

    Subclasses should add their own parameters. Port definitions
    are handled via PortGroup class attributes, not config.
    """

    kind: Literal["source"] = "source"
    fps: float | None = Field(None, ge=0.1, le=1000, description="Output frame rate")


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
