"""How frames reach an input port: the copy and repeat operations compiled
for each connected input, and the program that runs them every tick.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Tuple

import numpy as np

from rasl.graph.ports.port import InputPort
from rasl.signal import Frame, MatrixPayload


@dataclass(slots=True)
class CopySliceOp:
    source: str
    source_port: str
    is_back_edge: bool
    src_start: int
    src_end: int
    dst_start: int
    dst_end: int

    def required_rows(self, src_rows: int) -> int:
        if self.dst_end >= 0:
            return self.dst_end
        src_len = (self.src_end - self.src_start) if self.src_end >= 0 else (src_rows - self.src_start)
        if src_len < 0:
            src_len = 0
        return self.dst_start + src_len

    def populate(self, dst: np.ndarray, src: np.ndarray) -> None:
        """Copy slice from src to dst.
        
        Slice indices are interpreted as element indices (rows in the matrix),
        not scalar channel indices. For ColorPayload with 3 components, [0] means
        the first RGB triplet, not the first scalar channel.
        """
        src_rows = int(src.shape[0])
        src_end = self.src_end if self.src_end >= 0 else src_rows
        if src_end < self.src_start:
            return
        src_view = src[self.src_start:src_end, :]
        if src_view.size == 0:
            return
        dst_rows = int(dst.shape[0])
        dst_end = self.dst_end if self.dst_end >= 0 else dst_rows
        if dst_end < self.dst_start:
            return
        max_len = max(0, min(dst_end, dst_rows) - self.dst_start)
        if max_len <= 0:
            return
        copy_len = min(int(src_view.shape[0]), max_len)
        if copy_len <= 0:
            return
        cols = min(int(dst.shape[1]), int(src_view.shape[1]))
        dst[self.dst_start : self.dst_start + copy_len, :cols] = src_view[:copy_len, :cols]


@dataclass(slots=True)
class RepeatSliceOp:
    source: str
    source_port: str
    is_back_edge: bool
    src_start: int
    src_end: int
    dst_start: int
    dst_end: int
    repeat: int
    repeat_until: int | None

    def required_rows(self, src_rows: int) -> int:
        if self.dst_end >= 0:
            return self.dst_end
        if self.repeat_until is not None:
            return self.dst_start + int(self.repeat_until)
        src_len = (self.src_end - self.src_start) if self.src_end >= 0 else (src_rows - self.src_start)
        if src_len < 0:
            src_len = 0
        return self.dst_start + (src_len * int(self.repeat))

    def populate(self, dst: np.ndarray, src: np.ndarray) -> None:
        """Repeat slice from src to dst.
        
        Slice indices are interpreted as element indices (rows in the matrix),
        not scalar channel indices. For ColorPayload with 3 components, [0:1]
        repeated 3 times means repeat the first RGB triplet 3 times.
        """
        src_rows = int(src.shape[0])
        src_end = self.src_end if self.src_end >= 0 else src_rows
        if src_end < self.src_start:
            return
        src_view = src[self.src_start:src_end, :]
        if src_view.size == 0:
            return

        dst_rows = int(dst.shape[0])
        dst_end = self.dst_end if self.dst_end >= 0 else dst_rows
        dst_end = min(dst_end, dst_rows)
        if dst_end <= self.dst_start:
            return

        window = dst_end - self.dst_start
        if window <= 0:
            return

        if self.repeat_until is not None:
            total = min(window, int(self.repeat_until))
            if total <= 0:
                return
            rep = (total + int(src_view.shape[0]) - 1) // int(src_view.shape[0])
        else:
            rep = int(self.repeat)
            total = min(window, int(src_view.shape[0]) * rep)

        cols = min(int(dst.shape[1]), int(src_view.shape[1]))
        src_block = src_view[:, :cols]
        block_rows = int(src_block.shape[0])
        if block_rows <= 0:
            return

        for i in range(rep):
            base = self.dst_start + (i * block_rows)
            if base >= dst_end:
                break
            end = min(base + block_rows, self.dst_start + total, dst_end)
            copy_len = end - base
            if copy_len > 0:
                dst[base:end, :cols] = src_block[:copy_len, :]


EdgeOp = CopySliceOp | RepeatSliceOp


# Module-level profiling state (outside dataclass to avoid mutable default issues)
_ipp_profile_enabled: bool = False
_ipp_profile_stats: dict = {}  # {buffer_key: {resolve_ms, asarray_ms, buffer_ms, copy_ms, total_ms, count}}


@dataclass(slots=True)
class InputPortProgram:
    target: InputPort
    buffer_key: Tuple[str, str]
    fixed_rows: int | None
    fixed_cols: int | None
    passthrough: Tuple[str, str] | None
    passthrough_is_back_edge: bool
    ops: Tuple[EdgeOp, ...]

    @staticmethod
    def enable_profiling(enabled: bool = True) -> None:
        global _ipp_profile_enabled, _ipp_profile_stats
        _ipp_profile_enabled = enabled
        if enabled:
            _ipp_profile_stats.clear()

    @staticmethod
    def get_profile_stats() -> dict:
        return dict(_ipp_profile_stats)

    def populate(
        self,
        tick: int,
        resolve: Callable[[str, str, bool, int], Frame | None],
        ensure_buffer: Callable[[Tuple[str, str], int, int], np.ndarray],
    ) -> Frame | None:
        if self.passthrough is not None:
            src_node, src_port = self.passthrough
            return resolve(src_node, src_port, self.passthrough_is_back_edge, tick)

        profile = _ipp_profile_enabled
        if profile:
            t0 = time.perf_counter()
            resolve_time = 0.0
            asarray_time = 0.0

        first: Frame | None = None
        rows = int(self.fixed_rows) if self.fixed_rows is not None else 0
        cols = int(self.fixed_cols) if self.fixed_cols is not None else 1
        sources: list[tuple[EdgeOp, np.ndarray]] = []

        for op in self.ops:
            if profile:
                t_resolve = time.perf_counter()
            frame = resolve(op.source, op.source_port, op.is_back_edge, tick)
            if profile:
                resolve_time += time.perf_counter() - t_resolve

            if frame is None or not hasattr(frame.payload, "data"):
                continue
            if first is None:
                first = frame

            if profile:
                t_asarray = time.perf_counter()
            src = np.asarray(frame.payload.data, dtype=np.float32)
            if profile:
                asarray_time += time.perf_counter() - t_asarray

            if src.ndim == 1:
                src = src.reshape(-1, 1)
            if src.ndim != 2:
                continue
            rows = max(rows, op.required_rows(int(src.shape[0])))
            if self.fixed_cols is None:
                cols = max(cols, int(src.shape[1]))
            sources.append((op, src))

        if first is None or rows <= 0 or cols <= 0:
            return None

        if profile:
            t_buffer = time.perf_counter()
        buf = ensure_buffer(self.buffer_key, rows, cols)
        view = buf[:rows, :cols]
        view.fill(0.0)
        if profile:
            buffer_time = time.perf_counter() - t_buffer
            t_copy = time.perf_counter()

        for op, src in sources:
            op.populate(view, src)

        if profile:
            copy_time = time.perf_counter() - t_copy
            total_time = time.perf_counter() - t0

            key = self.buffer_key
            stats = _ipp_profile_stats.get(key)
            if stats is None:
                stats = {"resolve_ms": 0.0, "asarray_ms": 0.0, "buffer_ms": 0.0, "copy_ms": 0.0, "total_ms": 0.0, "count": 0}
                _ipp_profile_stats[key] = stats
            stats["resolve_ms"] += resolve_time * 1000
            stats["asarray_ms"] += asarray_time * 1000
            stats["buffer_ms"] += buffer_time * 1000
            stats["copy_ms"] += copy_time * 1000
            stats["total_ms"] += total_time * 1000
            stats["count"] += 1

        return Frame(
            topic=first.topic,
            timestamp=first.timestamp,
            payload=MatrixPayload(view),
            metadata=first.metadata,
        )
