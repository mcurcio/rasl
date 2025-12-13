"""Waveform generator source node.

This module provides WaveformNode, which generates various waveform shapes
with per-channel phase and speed modulation support. This is the core
building block for twinkle and other animated effects.

Pull-based execution: Computes waveform on-demand using tick.t for timing.
No internal loop - scheduler drives all timing.
"""

from __future__ import annotations

from typing import Literal

import numpy as np
from numpy.typing import NDArray
from pydantic import Field

from rasl.engine.nodes import BaseNode, NodeContext
from rasl.engine.frames import MatrixPayload, Frame
from rasl.engine.ports import InputPortSpec, OutputPortSpec, PortGroup
from rasl.engine.registry import node
from rasl.engine.tick import TickContext
from rasl.nodes.models import SourceNodeConfig


WaveShape = Literal["sine", "triangle", "sawtooth", "attack_decay", "square"]


def attack_decay_wave(phase: NDArray[np.float32], attack_ratio: float = 0.33) -> NDArray[np.float32]:
    """Asymmetric triangle wave with fast attack, slow decay.

    This is the classic TwinkleFOX waveform:
        /\\
       /  \\
      /    \\
     /      \\

    Args:
        phase: Phase values in [0, 1] range
        attack_ratio: Fraction of cycle for attack (default 1/3)

    Returns:
        Wave values in [0, 1] range
    """
    result = np.zeros_like(phase)
    attack_mask = phase < attack_ratio
    decay_mask = ~attack_mask

    # Fast attack: 0 -> 1 in attack_ratio of cycle
    result[attack_mask] = phase[attack_mask] / attack_ratio

    # Slow decay: 1 -> 0 in remaining (1 - attack_ratio) of cycle
    decay_phase = (phase[decay_mask] - attack_ratio) / (1.0 - attack_ratio)
    result[decay_mask] = 1.0 - decay_phase

    return result.astype(np.float32)


def triangle_wave(phase: NDArray[np.float32]) -> NDArray[np.float32]:
    """Symmetric triangle wave."""
    # 0->0.5: rise from 0 to 1
    # 0.5->1: fall from 1 to 0
    result = np.where(
        phase < 0.5,
        phase * 2.0,
        2.0 - phase * 2.0
    )
    return result.astype(np.float32)


def sawtooth_wave(phase: NDArray[np.float32]) -> NDArray[np.float32]:
    """Sawtooth wave (linear rise, instant fall)."""
    return phase.astype(np.float32)


def square_wave(phase: NDArray[np.float32], duty: float = 0.5) -> NDArray[np.float32]:
    """Square wave with configurable duty cycle."""
    return np.where(phase < duty, 1.0, 0.0).astype(np.float32)


def sine_wave(phase: NDArray[np.float32]) -> NDArray[np.float32]:
    """Sine wave normalized to [0, 1]."""
    return ((np.sin(phase * 2.0 * np.pi) + 1.0) / 2.0).astype(np.float32)


@node("WaveformNode", "Waveform")
class WaveformNode(BaseNode):
    """Source node that generates configurable waveforms.

    Generates per-channel waveforms with optional phase offset and speed
    modulation inputs. This enables effects like twinkle where each LED
    has its own phase and speed.

    Pull-based: Computes waveform on-demand using tick.t for timing.
    No internal loop - scheduler drives all timing.

    Waveform shapes:
        - sine: Smooth sinusoidal wave
        - triangle: Symmetric up-down triangle
        - sawtooth: Linear rise, instant fall
        - attack_decay: Fast rise, slow fall (TwinkleFOX style)
        - square: On/off with duty cycle

    Example config:
        rasl {
            # Basic waveform
            node Waveform pulse {
                shape attack_decay;
                frequency_hz 0.5;
                output_channels 150;
            }

            # With phase modulation from random source
            node Waveform twinkle {
                shape attack_decay;
                frequency_hz 0.3;
                attack_ratio 0.33;
                connect phases phase;
                connect speeds speed;
            }
        }
    """

    class Config(SourceNodeConfig):
        """Configuration for WaveformNode."""

        output_channels: int = Field(512, ge=1, le=65536, description="Number of output channels")
        shape: WaveShape = Field("sine", description="Waveform shape")
        frequency_hz: float = Field(1.0, ge=0.001, le=100.0, description="Base frequency in Hz")
        attack_ratio: float = Field(0.33, ge=0.01, le=0.99, description="Attack ratio for attack_decay shape")
        duty: float = Field(0.5, ge=0.0, le=1.0, description="Duty cycle for square wave")
        topic: str | None = Field(None, description="Optional topic override")

    # Class-level ports
    inputs = PortGroup.inputs(
        phase=InputPortSpec(MatrixPayload),  # Per-channel phase offsets [0, 1]
        speed=InputPortSpec(MatrixPayload),  # Per-channel speed multipliers
    )
    outputs = PortGroup.outputs(out=OutputPortSpec(MatrixPayload))

    def __init__(self, config: Config) -> None:
        super().__init__(config)
        self._channels = config.output_channels
        self._shape = config.shape
        self._frequency_hz = config.frequency_hz
        self._attack_ratio = config.attack_ratio
        self._duty = config.duty
        self._topic = config.topic or f"waveform.{self.id}"

    async def pull(self, tick: TickContext) -> None:
        """Compute waveform using scheduler's authoritative time."""
        t = tick.t

        # Base phase for all channels
        base_phase = (self._frequency_hz * t) % 1.0

        # Read optional modulation inputs
        phase_offsets: NDArray[np.float32] | None = None
        speed_multipliers: NDArray[np.float32] | None = None

        if phase_frame := self.inputs.phase.read():
            phase_offsets = np.asarray(phase_frame.payload, dtype=np.float32)

        if speed_frame := self.inputs.speed.read():
            speed_multipliers = np.asarray(speed_frame.payload, dtype=np.float32)

        # Apply per-channel speed multipliers if available
        if speed_multipliers is not None:
            speeds = speed_multipliers[: self._channels]
            if len(speeds) < self._channels:
                speeds = np.resize(speeds, self._channels)
            phase = (base_phase * speeds) % 1.0
        else:
            phase = np.full(self._channels, base_phase, dtype=np.float32)

        # Apply per-channel phase offsets if available
        if phase_offsets is not None:
            offsets = phase_offsets[: self._channels]
            if len(offsets) < self._channels:
                offsets = np.resize(offsets, self._channels)
            phase = (phase + offsets) % 1.0

        # Generate waveform
        values = self._apply_shape(phase)

        out_port = self.outputs.out
        buf = out_port.acquire(self._channels)
        arr = np.asarray(buf, dtype=np.float32)
        arr[: self._channels, 0] = values[: self._channels]
        out_port.commit(
            Frame(
                topic=self._topic,
                timestamp=tick.wall_time,
                payload=MatrixPayload(arr[: self._channels, :1]),
                metadata=dict(self._metadata),
            )
        )

    def _apply_shape(self, phase: NDArray[np.float32]) -> NDArray[np.float32]:
        """Apply the configured waveform shape."""
        shape = self._shape

        if shape == "sine":
            return sine_wave(phase)
        elif shape == "triangle":
            return triangle_wave(phase)
        elif shape == "sawtooth":
            return sawtooth_wave(phase)
        elif shape == "attack_decay":
            return attack_decay_wave(phase, self._attack_ratio)
        elif shape == "square":
            return square_wave(phase, self._duty)
        else:
            return sine_wave(phase)
