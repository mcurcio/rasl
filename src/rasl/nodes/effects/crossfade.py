"""Crossfade transform node: fade between two color inputs under a boolean selector."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

import numpy as np
from pydantic import Field

from rasl.color import ColorPayload, HslColorPayload
from rasl.graph import InputCountError, InputSize
from rasl.graph.node import BaseNode, TickContext, TransformNodeConfig, node
from rasl.graph.ports import InputPortSpec, OutputPortSpec, PortGroup
from rasl.signal import BoolPayload

if TYPE_CHECKING:
    from numpy.typing import NDArray

    from rasl.graph import Edge


@node("CrossfadeNode", "Crossfade", "crossfade")
class CrossfadeNode(BaseNode):
    """Transform node that fades between two color inputs when a selector changes.

    A false ``selector`` shows ``input0`` and a true one ``input1``. When it changes, the mix
    moves linearly to the other input over ``seconds``. The blend is done in HSL, with hue
    taking the shorter way round the circle, and the output is always HSL.
    """

    class Config(TransformNodeConfig):
        """Fade time for CrossfadeNode."""

        seconds: float = Field(1.0, ge=0.0)

    inputs = PortGroup.inputs(
        input0=InputPortSpec(ColorPayload),
        input1=InputPortSpec(ColorPayload),
        selector=InputPortSpec(BoolPayload, count=1),
    )
    outputs = PortGroup.outputs(out=OutputPortSpec(HslColorPayload, count_of="input0"))

    def __init__(self, config: Config) -> None:
        super().__init__(config)
        self._seconds = float(config.seconds)
        self._mix: float | None = None

    def validate_connections(self, incoming_edges: "list[Edge]") -> None:
        """Require ``input0``, ``input1`` and ``selector`` to be connected.

        Raises:
            ValueError: One of the three ports has no incoming edge.
        """
        connected_ports = {e.target_port for e in incoming_edges}
        for required in ("input0", "input1", "selector"):
            if required not in connected_ports:
                raise ValueError(f"Crossfade requires input '{required}' to be connected")

    def output_counts(self, inputs: Mapping[str, InputSize]) -> dict[str, int | None]:
        """Check ``input0`` and ``input1`` have one element count (the output's, via
        ``count_of``), when the plan is built.

        Raises:
            InputCountError: On ``input1``, when the two counts differ.
        """
        c0, c1 = inputs["input0"].count, inputs["input1"].count
        if c0 is not None and c1 is not None and c0 != c1:
            raise InputCountError(
                "input1", f"Crossfade inputs must have one element count, got input0={c0}, input1={c1}"
            )
        return {}

    def _shortest_circular_delta(
        self, a: NDArray[np.float32], b: NDArray[np.float32]
    ) -> NDArray[np.float32]:
        return ((b - a + 0.5) % 1.0) - 0.5

    async def pull(self, tick: TickContext) -> None:
        """Blend ``input0`` and ``input1`` in HSL and write the result to ``out``.

        The mix moves towards the selector's input by ``tick.dt / seconds`` per pull; it jumps
        there on the first pull and when ``seconds`` is 0. The output frame is ``input0``'s
        frame with the blended payload, encoded like the input the selector points at. Writes
        nothing until all three inputs have a frame.

        Raises:
            TypeError: An input's payload is not a ColorPayload.
            ValueError: The two inputs have different element counts.
        """
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
