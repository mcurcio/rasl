"""What flows through a graph: frames and their payloads.

- ``Frame``: an immutable container, a payload with a topic, a timestamp and metadata
- ``FramePayload``: the base of every payload type
- ``MatrixPayload``: numeric data, one row per element; ``BoolPayload``: a mask
- the payload registry: payload types by name (``@payload``, ``get_payload_type``)

Color payloads build on these and live in ``rasl.color``.
"""

from rasl.signal.frame import EMPTY_METADATA, Frame, Metadata
from rasl.signal.matrix import BoolPayload, MatrixPayload
from rasl.signal.payload import FramePayload, PayloadDescriptor
from rasl.signal.registry import get_payload_registry, get_payload_type, list_payload_types, payload

__all__ = [
    "EMPTY_METADATA",
    "BoolPayload",
    "Frame",
    "FramePayload",
    "MatrixPayload",
    "Metadata",
    "PayloadDescriptor",
    "get_payload_registry",
    "get_payload_type",
    "list_payload_types",
    "payload",
]
