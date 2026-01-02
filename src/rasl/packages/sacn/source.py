"""sACN/E1.31 source node for receiving DMX universe data.

This module provides SacnSourceNode, which listens for sACN (E1.31)
DMX packets on the network and emits them as normalized Frames
into the processing graph.
"""

from __future__ import annotations

import asyncio
import time
from types import MappingProxyType
from typing import Any, Optional

import numpy as np
import sacn
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from numpy.typing import NDArray

from rasl.engine.nodes import BaseNode, NodeContext
from rasl.engine.frames import MatrixPayload, Frame
from rasl.engine.ports import OutputPortSpec, OutputPort, PortGroup, EMPTY_PORTS
from rasl.engine.registry import node
from rasl.nodes.models import SourceNodeConfig


class SacnUniverseConfig(BaseModel):
    """Per-universe configuration."""

    model_config = ConfigDict(extra="forbid")

    id: int = Field(..., ge=0, description="sACN universe number")
    channels: int | None = Field(
        None,
        ge=1,
        description="Number of RGB elements (rows) to emit from this universe",
    )


@node("SacnSourceNode", "SacnSource")
class SacnSourceNode(BaseNode):
    """Source node that receives sACN (E1.31) DMX universe data.

    SacnSourceNode listens on the specified network interface for sACN
    multicast packets and converts incoming DMX data into normalized
    Frames. Each received universe is emitted as a separate Frame with
    the channel data normalized to float32 [0.0, 1.0].

    Example config:
        rasl {
            node SacnSource sacnSource {
                universes 1 2;
                bind_address "0.0.0.0";
                bind_port 5568;
            }
        }
    """

    class Config(SourceNodeConfig):
        """Configuration for SacnSourceNode."""

        universes: list[int] | None = Field(
            default=None, min_length=1, description="Universe numbers to listen to"
        )
        universe_blocks: list[SacnUniverseConfig] = Field(
            default_factory=list,
            alias="universe",
            description="Per-universe overrides using block syntax",
        )
        bind_address: str = Field("0.0.0.0", description="Network interface to bind to")
        bind_port: int = Field(5568, ge=1, le=65535, description="UDP port to listen on")

        @field_validator("universes", mode="before")
        @classmethod
        def normalize_universes(cls, v: int | list[int] | None) -> list[int] | None:
            """Coerce single integer to list."""
            if v is None:
                return None
            if isinstance(v, int):
                return [v]
            return v

        @model_validator(mode="after")
        def ensure_universe_config(self) -> "SacnSourceNode.Config":
            if not self.universe_blocks and not self.universes:
                raise ValueError("SacnSource requires universes via 'universes' list or 'universe' blocks")
            return self

        def resolve_universe_configs(self) -> list[SacnUniverseConfig]:
            configs: dict[int, SacnUniverseConfig] = {block.id: block for block in self.universe_blocks}
            if self.universes:
                for universe in self.universes:
                    if universe not in configs:
                        configs[universe] = SacnUniverseConfig(id=universe)
            if not configs:
                raise ValueError("SacnSource requires at least one universe")
            return [configs[uid] for uid in sorted(configs.keys())]

    outputs = EMPTY_PORTS

    def __init__(self, config: Config) -> None:
        super().__init__(config)
        self._config = config
        self._universe_configs = config.resolve_universe_configs()
        self._universes = [cfg.id for cfg in self._universe_configs]
        self._bind_address = config.bind_address
        self._bind_port = config.bind_port
        self._receiver: Optional[sacn.sACNreceiver] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._ctx: Optional[NodeContext] = None
        self._universe_ports: dict[int, OutputPort] = {}
        self._channels_port: Optional[OutputPort] = None
        self._latest_slots: dict[int, NDArray[np.float32]] = {}
        self._channels_by_universe: dict[int, int | None] = {
            cfg.id: cfg.channels for cfg in self._universe_configs
        }
        self._init_ports()

    def _init_ports(self) -> None:
        port_specs: dict[str, OutputPortSpec] = {
            f"universe_{u}": OutputPortSpec(MatrixPayload) for u in self._universes
        }
        port_specs["channels"] = OutputPortSpec(MatrixPayload)
        self.outputs = PortGroup.outputs(**port_specs)
        self._channels_port = getattr(self.outputs, "channels", None)
        self._universe_ports = {
            u: getattr(self.outputs, f"universe_{u}") for u in self._universes
        }

    async def start(self, ctx: NodeContext) -> None:
        self._ctx = ctx
        self._loop = asyncio.get_running_loop()
        self._receiver = sacn.sACNreceiver(
            bind_address=self._bind_address, bind_port=self._bind_port
        )
        self._receiver.start()
        for universe in self._universes:
            self._receiver.register_listener(
                "universe", self._make_listener(universe), universe=universe
            )

    def _make_listener(self, universe: int) -> Any:
        """Create a callback function for a specific universe."""

        def _listener(packet: Any) -> None:
            if self._ctx is None or self._loop is None:
                return
            
            # Normalize DMX bytes (0-255) to float32 (0.0-1.0)
            # Note: sacn library always pads dmxData to 512 bytes
            # Reshape into RGB triplets for ColorPayload compatibility
            raw = np.array(packet.dmxData, dtype=np.float32) / 255.0
            # Truncate to configured RGB element count (defaults to full frame)
            max_elements = len(raw) // 3
            configured = self._channels_by_universe.get(universe)
            if configured is not None:
                rgb_count = min(max_elements, int(configured))
            else:
                rgb_count = max_elements
            slots = raw[:rgb_count * 3].reshape(-1, 3)
            
            timestamp = time.monotonic()
            metadata = {
                "sourceUniverse": packet.universe,
                "priority": getattr(packet, "priority", None),
                "sequence": getattr(packet, "sequence", None),
                "sourceName": getattr(packet, "sourceName", None),
                **self._metadata,
            }
            if self._loop.is_closed():
                return
            frame = Frame(
                topic=f"sacn.universe.{packet.universe}",
                timestamp=timestamp,
                payload=MatrixPayload(slots),
                metadata=MappingProxyType({k: v for k, v in metadata.items() if v is not None}),
            )
            # Write to specific universe port
            universe_port = self._universe_ports.get(universe)
            if universe_port is not None:
                universe_port.write(frame)

            # Update latest slots and emit merged channels output
            self._latest_slots[universe] = slots
            self._emit_channels_frame(frame)

        return _listener

    def _emit_channels_frame(self, source_frame: Frame) -> None:
        if self._channels_port is None:
            return

        ordered_slots = [
            self._latest_slots[u] for u in self._universes if u in self._latest_slots
        ]
        if not ordered_slots:
            return

        merged = np.concatenate(ordered_slots, axis=0)
        metadata = dict(source_frame.metadata)
        metadata.update(
            {
                "sourceUniverse": "channels",
                "mergedUniverses": ",".join(
                    str(u) for u in self._universes if u in self._latest_slots
                ),
            }
        )
        merged_frame = Frame(
            topic="sacn.channels",
            timestamp=source_frame.timestamp,
            payload=MatrixPayload(merged),
            metadata=MappingProxyType(metadata),
        )
        self._channels_port.write(merged_frame)

    async def handle(self, port: str, frame: Frame, ctx: NodeContext) -> None:
        pass  # Source nodes don't receive frames

    async def stop(self, ctx: NodeContext) -> None:
        if self._receiver is not None:
            self._receiver.stop()
            self._receiver = None
