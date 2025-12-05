from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping


class NodeKind(str, Enum):
    SOURCE = "source"
    TRANSFORM = "transform"
    SINK = "sink"


@dataclass(frozen=True)
class TimingConfig:
    fps: float | None = None


@dataclass(frozen=True)
class PortIOConfig:
    channels: int
    port: str


@dataclass(frozen=True)
class NodeConfig:
    id: str
    type_id: str
    kind: NodeKind
    timing: TimingConfig
    params: Mapping[str, Any]


@dataclass(frozen=True)
class SourceNodeConfig(NodeConfig):
    input: None = None
    output: PortIOConfig | None = None


@dataclass(frozen=True)
class SinkNodeConfig(NodeConfig):
    input: PortIOConfig | None = None
    output: None = None


@dataclass(frozen=True)
class TransformNodeConfig(NodeConfig):
    input: PortIOConfig | None = None
    output: PortIOConfig | None = None


@dataclass(frozen=True)
class TimingHints:
    default_fps: float | None = None
    min_fps: float | None = None
    max_fps: float | None = None


@dataclass(frozen=True)
class IOHints:
    default_channels: int | None = None
    default_port: str | None = None


@dataclass(frozen=True)
class NodeEngineHints:
    timing: TimingHints = TimingHints()
    input: IOHints | None = None
    output: IOHints | None = None
