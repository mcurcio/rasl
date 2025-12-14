from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from pydantic import Field

from rasl.engine.frames import BoolPayload, ColorPayload, HslColorPayload
from rasl.engine.nodes import BaseNode
from rasl.engine.ports import InputPortSpec, OutputPortSpec, PortGroup
from rasl.engine.registry import node
from rasl.engine.tick import TickContext
from rasl.nodes.models import TransformNodeConfig

if TYPE_CHECKING:
    from numpy.typing import NDArray
    from rasl.engine.graph import Edge
    from rasl.engine.frames import Frame


@node("CrossfadeNode", "Crossfade", "crossfade")
class CrossfadeNode(BaseNode):
    class Config(TransformNodeConfig):
        seconds: float = Field(1.0, ge=0.0)

    inputs = PortGroup.inputs(
        input0=InputPortSpec(ColorPayload),
        input1=InputPortSpec(ColorPayload),
        selector=InputPortSpec(BoolPayload, count=1),
    )
    outputs = PortGroup.outputs(out=OutputPortSpec(HslColorPayload))

    def __init__(self, config: Config) -> None:
        super().__init__(config)
        self._seconds = float(config.seconds)
        self._mix: float | None = None

    def validate_connections(self, incoming_edges: "list[Edge]") -> None:
        connected_ports = {e.target_port for e in incoming_edges}
        for required in ("input0", "input1", "selector"):
            if required not in connected_ports:
                raise ValueError(f"Crossfade requires input '{required}' to be connected")

    def _shortest_circular_delta(
        self, a: NDArray[np.float32], b: NDArray[np.float32]
    ) -> NDArray[np.float32]:
        return ((b - a + 0.5) % 1.0) - 0.5

    async def pull(self, tick: TickContext) -> None:
        frame0 = self.inputs.input0.read()
        frame1 = self.inputs.input1.read()
        selector_frame = self.inputs.selector.read()

        if frame0 is None or frame1 is None or selector_frame is None:
            return

        if not isinstance(frame0.payload, ColorPayload):
            raise TypeError(
                f"Crossfade input0 must be a ColorPayload, got {type(frame0.payload).__name__}"
            )
        if not isinstance(frame1.payload, ColorPayload):
            raise TypeError(
                f"Crossfade input1 must be a ColorPayload, got {type(frame1.payload).__name__}"
            )

        selector_arr = np.asarray(selector_frame.payload)
        if selector_arr.size <= 0:
            return
        target = bool(selector_arr.reshape(-1)[0] != 0)

        target_mix = 1.0 if target else 0.0

        if self._mix is None:
            self._mix = target_mix
        else:
            if self._seconds <= 0.0:
                self._mix = target_mix
            else:
                step = float(tick.dt) / self._seconds
                if target_mix > self._mix:
                    self._mix = min(target_mix, self._mix + step)
                elif target_mix < self._mix:
                    self._mix = max(target_mix, self._mix - step)

        c0 = frame0.payload
        c1 = frame1.payload

        if c0.count != c1.count:
            raise ValueError(
                f"Crossfade inputs must have matching count, got input0={c0.count}, input1={c1.count}"
            )

        hsl0 = c0.to_model(HslColorPayload)
        hsl1 = c1.to_model(HslColorPayload)

        d0 = np.asarray(hsl0.data, dtype=np.float32)
        d1 = np.asarray(hsl1.data, dtype=np.float32)

        if d0.shape != d1.shape:
            raise ValueError(
                f"Crossfade inputs must have matching shape after conversion, got {d0.shape!r} vs {d1.shape!r}"
            )

        mix = float(self._mix)

        h0 = d0[:, 0]
        s0 = d0[:, 1]
        l0 = d0[:, 2]
        h1 = d1[:, 0]
        s1 = d1[:, 1]
        l1 = d1[:, 2]

        h = (h0 + mix * self._shortest_circular_delta(h0, h1)) % 1.0
        s = s0 + mix * (s1 - s0)
        l = l0 + mix * (l1 - l0)

        out = np.stack([h, s, l], axis=1).astype(np.float32)

        encoding = hsl1.encoding if target else hsl0.encoding
        out_payload = HslColorPayload(out, encoding=encoding)
        self.outputs.out.write(frame0.with_payload(out_payload))
