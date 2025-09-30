"""
Core type definitions for RASL.

Defines fundamental data structures used throughout the system:
- Frame: timing context for execution
- NodeState: health and status tracking
- Schema: type contracts for port connections
- Component/Channel: data structure definitions
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
import time


class NodeState(Enum):
    """Node health and execution state."""
    HEALTHY = "healthy"
    FAILED = "failed"
    RECOVERING = "recovering"
    DISABLED = "disabled"
    INITIALIZING = "initializing"


class RangeRule(Enum):
    """How values outside [min,max] are handled by transforms."""
    CLIP = "clip"      # Clamp to bounds
    WRAP = "wrap"      # Circular wrap (e.g., hue)
    ERROR = "error"    # Raise validation error


class Liveness(Enum):
    """Source capability (declared at type level)."""
    STREAM = "stream"  # Potentially unbounded stream
    FINITE = "finite"  # Bounded media that will emit EOS once
    EVENT = "event"    # Sparse/bursty events with timestamps


@dataclass(frozen=True)
class Frame:
    """
    Monotonic frame context emitted by the scheduler.
    All nodes see the same Frame during a tick.
    """
    t: float   # Absolute time (seconds)
    dt: float  # Delta time since previous frame (seconds)
    seq: int   # Monotonically increasing sequence number
    
    @classmethod
    def now(cls, seq: int, last_time: Optional[float] = None) -> "Frame":
        """Create a frame with current time."""
        current_time = time.perf_counter()
        dt = current_time - last_time if last_time is not None else 0.0
        return cls(t=current_time, dt=dt, seq=seq)


@dataclass(frozen=True)
class Range:
    """Value range with handling rule for out-of-bounds values."""
    min: float = 0.0
    max: float = 1.0
    rule: RangeRule = RangeRule.CLIP
    
    def normalize(self, value: float) -> float:
        """Apply range rule to a value."""
        if self.rule == RangeRule.CLIP:
            return max(self.min, min(self.max, value))
        elif self.rule == RangeRule.WRAP:
            range_size = self.max - self.min
            if range_size <= 0:
                return self.min
            normalized = (value - self.min) % range_size
            return self.min + normalized
        elif self.rule == RangeRule.ERROR:
            if not (self.min <= value <= self.max):
                raise ValueError(f"Value {value} outside range [{self.min}, {self.max}]")
            return value
        else:
            return value


@dataclass(frozen=True)
class Channel:
    """A single scalar signal (leaf)."""
    id: str                          # e.g., "r", "g", "b", "h"
    units: Optional[str] = None      # e.g., "unitless", "turns", "rad", "mm"
    range: Range = Range()           # Semantic range; default [0,1], rule=clip


@dataclass(frozen=True)
class Component:
    """
    A bundle of related channels that travel together and share invariants.
    Examples: Color(HSV), Color(linear_srgb), Vector3(mm).
    """
    name: str                        # e.g., "Color", "Vector3"
    flavor: Optional[str] = None     # e.g., "HSV", "linear_srgb", "cartesian"
    channels: Tuple[Channel, ...] = ()
    colorspace: Optional[str] = None # Normalized color math context


@dataclass(frozen=True)
class Schema:
    """
    Port contract: ordered components, each with their channels.
    Connections align by component/channel ids, not positional index.
    """
    components: Tuple[Component, ...]
    
    def channel_count(self) -> int:
        """Total number of channels across all components."""
        return sum(len(comp.channels) for comp in self.components)
    
    def get_channel_names(self) -> List[str]:
        """Get flat list of all channel names."""
        names = []
        for comp in self.components:
            for channel in comp.channels:
                names.append(f"{comp.name}.{channel.id}")
        return names
    
    def is_compatible(self, other: "Schema") -> bool:
        """Check if this schema is compatible with another for connections."""
        # For MVP: Allow connections if channel counts match
        # This enables flexible connections between different node types
        # TODO: Implement full compatibility checking including units, colorspace, names
        return self.channel_count() == other.channel_count()


@dataclass
class NodeStatus:
    """Runtime status tracking for a node."""
    state: NodeState = NodeState.HEALTHY
    last_error: Optional[Exception] = None
    error_count: int = 0
    last_success: float = 0.0
    total_evaluations: int = 0
    avg_eval_time: float = 0.0  # Exponential moving average
    
    def update_success(self, eval_time: float, frame_time: float):
        """Update status after successful evaluation."""
        self.state = NodeState.HEALTHY
        self.last_success = frame_time
        self.total_evaluations += 1
        self.error_count = 0
        
        # Update exponential moving average
        alpha = 0.1  # Smoothing factor
        self.avg_eval_time = (1 - alpha) * self.avg_eval_time + alpha * eval_time
    
    def update_error(self, error: Exception):
        """Update status after evaluation error."""
        self.last_error = error
        self.error_count += 1
        
        if self.error_count >= 3:  # TODO: Make configurable
            self.state = NodeState.FAILED
        else:
            self.state = NodeState.RECOVERING


# Common schema definitions for built-in types
RGB_SCHEMA = Schema(components=(
    Component(
        name="Color",
        flavor="linear_srgb",
        channels=(
            Channel("r", "unitless", Range(0.0, 1.0)),
            Channel("g", "unitless", Range(0.0, 1.0)),
            Channel("b", "unitless", Range(0.0, 1.0)),
        ),
        colorspace="linear_srgb"
    ),
))

HSV_SCHEMA = Schema(components=(
    Component(
        name="Color",
        flavor="HSV",
        channels=(
            Channel("h", "turns", Range(0.0, 1.0, RangeRule.WRAP)),
            Channel("s", "unitless", Range(0.0, 1.0)),
            Channel("v", "unitless", Range(0.0, 1.0)),
        ),
        colorspace="HSV"
    ),
))

SCALAR_SCHEMA = Schema(components=(
    Component(
        name="Scalar",
        channels=(Channel("value", "unitless", Range(0.0, 1.0)),)
    ),
))
