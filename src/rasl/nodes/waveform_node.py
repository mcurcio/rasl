"""Waveform generator source node.

This module provides WaveformNode, which generates various waveform shapes
with per-channel phase and speed modulation support. This is the core
building block for twinkle and other animated effects.
"""

from __future__ import annotations

import math
import time
from typing import Literal

import anyio
import numpy as np
from numpy.typing import NDArray
from pydantic import Field

from rasl.config.models import SourceNodeConfig
from rasl.engine.base_node import BaseNode
from rasl.engine.frame import ArrayPayload, Frame
from rasl.engine.node import NodeContext
from rasl.engine.ports import PortGroup, PortSpec
from rasl.engine.registry import node


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

    inputs = PortGroup(
        phase=PortSpec(accepts="array"),  # Per-channel phase offsets [0, 1]
        speed=PortSpec(accepts="array"),  # Per-channel speed multipliers
    )
    outputs = PortGroup(out=PortSpec(accepts="array"))

    def __init__(self, config: Config) -> None:
        super().__init__(config)
        self._channels = config.output_channels
        self._shape = config.shape
        self._frequency_hz = config.frequency_hz
        self._attack_ratio = config.attack_ratio
        self._duty = config.duty
        self._fps = int(config.fps) if config.fps else 30
        self._topic = config.topic or f"waveform.{self.id}"

        # Modulation buffers (optional inputs)
        self._phase_offsets: NDArray[np.float32] | None = None
        self._speed_multipliers: NDArray[np.float32] | None = None

    async def start(self, ctx: NodeContext) -> None:
        ctx.start_background(self._run_loop, ctx)

    async def _run_loop(self, ctx: NodeContext) -> None:
        interval = 1.0 / float(self._fps)
        t0 = time.monotonic()

        while True:
            now = time.monotonic()
            t = now - t0

            # Base phase for all channels
            base_phase = (self._frequency_hz * t) % 1.0

            # Apply per-channel speed multipliers if available
            if self._speed_multipliers is not None:
                speeds = self._speed_multipliers[:self._channels]
                if len(speeds) < self._channels:
                    speeds = np.resize(speeds, self._channels)
                phase = (base_phase * speeds) % 1.0
            else:
                phase = np.full(self._channels, base_phase, dtype=np.float32)

            # Apply per-channel phase offsets if available
            if self._phase_offsets is not None:
                offsets = self._phase_offsets[:self._channels]
                if len(offsets) < self._channels:
                    offsets = np.resize(offsets, self._channels)
                phase = (phase + offsets) % 1.0

            # Generate waveform
            values = self._apply_shape(phase)

            frame = Frame(
                topic=self._topic,
                timestamp=now,
                payload=ArrayPayload(values),
                metadata=dict(self._metadata),
            )
            await ctx.emit("out", frame)
            await anyio.sleep(interval)

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

    async def handle(self, port: str, frame: Frame, ctx: NodeContext) -> None:
        """Handle modulation inputs."""
        data = np.asarray(frame.payload, dtype=np.float32)

        if port == "phase":
            self._phase_offsets = data
        elif port == "speed":
            self._speed_multipliers = data

    async def stop(self, ctx: NodeContext) -> None:
        pass
