"""
Sine wave source for generating smooth oscillating values.
"""

import math
from typing import Dict, Mapping, Any

from rasl.core.nodes import BaseSource, NDArrayLike
from rasl.core.types import Frame, Liveness, Schema, Component, Channel, Range


class SineSource(BaseSource):
    """
    Generates sine wave data across multiple channels.
    
    Useful for smooth animations, breathing effects, and periodic motion.
    Each channel can have independent phase offsets for wave-like patterns.
    """
    
    TYPE = "SineSource"
    LIVENESS = Liveness.STREAM
    
    def __init__(
        self,
        *,
        freq: float = 1.0,
        amplitude: float = 1.0,
        offset: float = 0.0,
        phase: float = 0.0,
        channels: int = 1,
        phase_shift: float = 0.0,  # Phase shift between channels
        **kwargs
    ):
        super().__init__(**kwargs)
        self.freq = freq
        self.amplitude = amplitude
        self.offset = offset
        self.phase = phase
        self.channels = channels
        self.phase_shift = phase_shift
    
    def param_spec(self) -> Mapping[str, Mapping[str, Any]]:
        return {
            "freq": {
                "type": "float",
                "default": 1.0,
                "min": 0.01,
                "max": 100.0,
                "description": "Frequency in Hz"
            },
            "amplitude": {
                "type": "float", 
                "default": 1.0,
                "min": 0.0,
                "max": 10.0,
                "description": "Wave amplitude"
            },
            "offset": {
                "type": "float",
                "default": 0.0,
                "min": -10.0,
                "max": 10.0,
                "description": "DC offset"
            },
            "phase": {
                "type": "float",
                "default": 0.0,
                "min": 0.0,
                "max": 2 * math.pi,
                "description": "Phase offset in radians"
            },
            "channels": {
                "type": "int",
                "default": 1,
                "min": 1,
                "max": 1000,
                "description": "Number of output channels"
            },
            "phase_shift": {
                "type": "float",
                "default": 0.0,
                "min": 0.0,
                "max": 2 * math.pi,
                "description": "Phase shift between channels"
            }
        }
    
    def sample(self, frame: Frame) -> Dict[str, NDArrayLike]:
        """Generate sine wave data for the current frame."""
        # Calculate base phase for this time
        base_phase = 2 * math.pi * self.freq * frame.t + self.phase
        
        # Generate data for each channel
        data = []
        for i in range(self.channels):
            # Add per-channel phase shift
            channel_phase = base_phase + (i * self.phase_shift)
            
            # Calculate sine value
            value = self.amplitude * math.sin(channel_phase) + self.offset
            data.append(value)
        
        return {"out": data}
    
    def port_schema(self, name: str) -> Schema:
        """Define output schema."""
        if name == "out":
            channels = []
            for i in range(self.channels):
                channels.append(
                    Channel(f"ch{i}", "unitless", Range(-10.0, 10.0))
                )
            
            return Schema(components=(
                Component(
                    name="Scalar",
                    channels=tuple(channels)
                ),
            ))
        
        raise ValueError(f"Unknown port: {name}")


class MultiSineSource(BaseSource):
    """
    Multiple independent sine waves with different frequencies.
    
    Useful for complex harmonic patterns and multi-frequency effects.
    """
    
    TYPE = "MultiSineSource"
    LIVENESS = Liveness.STREAM
    
    def __init__(
        self,
        *,
        frequencies: list[float] = None,
        amplitudes: list[float] = None,
        phases: list[float] = None,
        **kwargs
    ):
        super().__init__(**kwargs)
        
        # Default to single 1Hz sine if no frequencies provided
        self.frequencies = frequencies or [1.0]
        self.amplitudes = amplitudes or [1.0] * len(self.frequencies)
        self.phases = phases or [0.0] * len(self.frequencies)
        
        # Ensure all lists are the same length
        num_sines = len(self.frequencies)
        if len(self.amplitudes) < num_sines:
            self.amplitudes.extend([1.0] * (num_sines - len(self.amplitudes)))
        if len(self.phases) < num_sines:
            self.phases.extend([0.0] * (num_sines - len(self.phases)))
    
    def param_spec(self) -> Mapping[str, Mapping[str, Any]]:
        return {
            "frequencies": {
                "type": "list[float]",
                "default": [1.0],
                "description": "List of frequencies for each sine wave"
            },
            "amplitudes": {
                "type": "list[float]", 
                "default": [1.0],
                "description": "List of amplitudes for each sine wave"
            },
            "phases": {
                "type": "list[float]",
                "default": [0.0],
                "description": "List of phase offsets for each sine wave"
            }
        }
    
    def sample(self, frame: Frame) -> Dict[str, NDArrayLike]:
        """Generate multi-sine wave data."""
        data = []
        
        for freq, amp, phase in zip(self.frequencies, self.amplitudes, self.phases):
            wave_phase = 2 * math.pi * freq * frame.t + phase
            value = amp * math.sin(wave_phase)
            data.append(value)
        
        return {"out": data}
    
    def port_schema(self, name: str) -> Schema:
        """Define output schema based on number of sine waves."""
        if name == "out":
            channels = []
            for i in range(len(self.frequencies)):
                channels.append(
                    Channel(f"sine{i}", "unitless", Range(-10.0, 10.0))
                )
            
            return Schema(components=(
                Component(
                    name="MultiSine",
                    channels=tuple(channels)
                ),
            ))
        
        raise ValueError(f"Unknown port: {name}")
