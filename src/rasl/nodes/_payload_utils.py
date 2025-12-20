"""Utility helpers for working with payload instances in nodes."""

from __future__ import annotations

from numpy.typing import NDArray

from rasl.engine.frames import ColorPayload, FramePayload, MatrixPayload


def clone_payload_like(payload: FramePayload, data: NDArray) -> FramePayload:
    """Recreate a payload of the same concrete type with new data.

    Args:
        payload: Existing payload instance whose type/metadata should be preserved.
        data: New numpy array (count, channels) to wrap.

    Returns:
        New payload instance of the same type.
    """
    if isinstance(payload, ColorPayload):
        payload_type = type(payload)
        if payload_type is ColorPayload:
            return ColorPayload(data, model=payload.model, encoding=payload.encoding)
        try:
            return payload_type(data, encoding=payload.encoding)
        except TypeError:
            return payload_type(data)

    if isinstance(payload, MatrixPayload):
        payload_type = type(payload)
        if payload_type is MatrixPayload:
            return MatrixPayload(data)
        return payload_type(data)

    payload_type = type(payload)
    return payload_type(data)
