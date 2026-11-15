"""How frames reach an input port: the copy and repeat operations compiled
for each connected input, and the program that runs them every tick.
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Callable, Dict, List, Set, Tuple

import numpy as np

from rasl.graph.edge import Edge
from rasl.graph.node.protocol import Node, get_inputs
from rasl.graph.ports.port import InputPort
from rasl.signal import Frame, MatrixPayload


@dataclass(slots=True)
class CopySliceOp:
    """Copy rows of one source output into rows of an input port's buffer.

    Rows are elements (see ``populate``). Ranges are half-open, and an end of -1 leaves the
    range open.

    Attributes:
        source: ID of the node whose output is read.
        source_port: Name of that node's output port.
        is_back_edge: True if the edge closes a cycle, so the previous tick's frame is read.
        src_start: First source row copied.
        src_end: One past the last source row copied; -1 for the source's last row.
        dst_start: First destination row written.
        dst_end: One past the last destination row written; -1 for as many as are copied.
    """

    source: str
    source_port: str
    is_back_edge: bool
    src_start: int
    src_end: int
    dst_start: int
    dst_end: int

    def required_rows(self, src_rows: int) -> int:
        """Number of destination rows this op needs for a source of ``src_rows`` rows.

        ``dst_end`` when it is set, else ``dst_start`` plus the length of the source slice.
        """
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
    """Tile rows of one source output across rows of an input port's buffer.

    The fields shared with ``CopySliceOp`` mean the same.

    Attributes:
        source: ID of the node whose output is read.
        source_port: Name of that node's output port.
        is_back_edge: True if the edge closes a cycle, so the previous tick's frame is read.
        src_start: First source row of the slice repeated.
        src_end: One past the last source row of the slice; -1 for the source's last row.
        dst_start: First destination row written.
        dst_end: One past the last destination row written; -1 for as many as are produced.
        repeat: Number of copies of the slice written back to back. Ignored when
            ``repeat_until`` is set.
        repeat_until: Number of destination rows to fill, counted from ``dst_start``; the last
            copy is cut short to fit. None to write ``repeat`` whole copies.
    """

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
        """Number of destination rows this op needs for a source of ``src_rows`` rows.

        ``dst_end`` when it is set, else ``dst_start + repeat_until``, else ``dst_start`` plus
        ``repeat`` times the length of the source slice.
        """
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
    """The compiled steps that build one input port's frame each tick.

    Attributes:
        target: The input port the frame is for.
        buffer_key: (node ID, port name) of ``target``; names the buffer the frame is built in.
        fixed_rows: Element count fixed by the port's spec, or None. The built frame has at
            least this many rows, and more if an op needs more.
        fixed_cols: Components per element when every payload type the port accepts has the
            same number, else None (the widest source sets the width).
        passthrough: (source node ID, output port) when one edge with no slice and no repeat
            feeds the port: that frame is handed over as it is, and ``ops`` is empty.
        passthrough_is_back_edge: True if the passthrough edge closes a cycle.
        ops: The copy and repeat operations, in edge order. Where two write the same rows, the
            later one wins.
    """

    target: InputPort
    buffer_key: Tuple[str, str]
    fixed_rows: int | None
    fixed_cols: int | None
    passthrough: Tuple[str, str] | None
    passthrough_is_back_edge: bool
    ops: Tuple[EdgeOp, ...]

    @staticmethod
    def enable_profiling(enabled: bool = True) -> None:
        """Turn timing of ``populate`` on or off for every program in the process.

        Turning it on, also when it is already on, clears the stats collected so far.
        """
        global _ipp_profile_enabled, _ipp_profile_stats
        _ipp_profile_enabled = enabled
        if enabled:
            _ipp_profile_stats.clear()

    @staticmethod
    def get_profile_stats() -> dict:
        """Timings collected while profiling, keyed by ``buffer_key``.

        Each value has ``resolve_ms``, ``asarray_ms``, ``buffer_ms``, ``copy_ms`` and ``total_ms``
        (sums, in milliseconds) and ``count`` (``populate`` calls that built a frame).
        Passthrough programs are not timed.
        """
        return dict(_ipp_profile_stats)

    def populate(
        self,
        tick: int,
        resolve: Callable[[str, str, bool, int], Frame | None],
        ensure_buffer: Callable[[Tuple[str, str], int, int], np.ndarray],
    ) -> Frame | None:
        """Build this tick's frame for the target port.

        A passthrough returns its source's frame unchanged. Otherwise each op's source is
        written, in op order, into a zero-filled float32 buffer. A source with no frame, a
        payload with no ``data``, or data of more than two dimensions is skipped.

        Args:
            tick: Tick number, passed on to ``resolve``.
            resolve: Returns the frame last written to (node ID, output port), or None; called
                with (node ID, output port, is_back_edge, tick).
            ensure_buffer: Returns an array of at least (rows, cols) for a buffer key.

        Returns:
            A frame whose ``MatrixPayload`` is a view of the buffer, with the topic, timestamp and
            metadata of the first source that had a frame; None if no source had one. The buffer
            is reused, so the payload holds only until the next call.
        """
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


def compile_input_programs(
    nodes: Mapping[str, Node],
    incoming_by_node: Dict[str, List[Edge]],
    back_edges: Set[Tuple[str, str, str, str]],
) -> Dict[Tuple[str, str], InputPortProgram]:
    """Compile an ``InputPortProgram`` for every connected input port.

    Args:
        nodes: Node ID to node.
        incoming_by_node: Target node ID to the edges that end at that node.
        back_edges: The edges that close a cycle, as (source, source_port, target,
            target_port).

    Returns:
        The programs, keyed by (target node ID, input port name). Edges to a port name the
        target node does not have are left out.
    """
    programs: Dict[Tuple[str, str], InputPortProgram] = {}

    for target_node_id, edges in incoming_by_node.items():
        node = nodes[target_node_id]
        inputs = get_inputs(node)

        by_port: Dict[str, List[Edge]] = {}
        for e in edges:
            by_port.setdefault(e.target_port, []).append(e)

        for port_name, port_edges in by_port.items():
            port = inputs.get(port_name)
            if port is None or not isinstance(port, InputPort):
                continue

            fixed_rows = port.spec.fixed_count

            fixed_cols: int | None = None
            resolved = port.spec.resolve_payload_types()
            if resolved:
                comps = [getattr(t, "components", None) for t in resolved]
                if comps and all((c is not None and c == comps[0]) for c in comps):
                    fixed_cols = int(comps[0])

            passthrough: Tuple[str, str] | None = None
            passthrough_is_back = False
            ops: List[EdgeOp] = []

            if len(port_edges) == 1:
                e = port_edges[0]
                if (
                    e.source_slice is None
                    and e.target_slice is None
                    and e.repeat <= 1
                    and e.repeat_until is None
                ):
                    passthrough = (e.source, e.source_port)
                    passthrough_is_back = (
                        (e.source, e.source_port, e.target, e.target_port) in back_edges
                    )
                    programs[(target_node_id, port_name)] = InputPortProgram(
                        target=port,
                        buffer_key=(target_node_id, port_name),
                        fixed_rows=fixed_rows,
                        fixed_cols=fixed_cols,
                        passthrough=passthrough,
                        passthrough_is_back_edge=passthrough_is_back,
                        ops=(),
                    )
                    continue

            for e in port_edges:
                is_back = (e.source, e.source_port, e.target, e.target_port) in back_edges

                src_start = e.source_slice.start if e.source_slice else 0
                src_end = e.source_slice.end if (e.source_slice and e.source_slice.end is not None) else -1

                dst_start = e.target_slice.start if e.target_slice else 0
                dst_end = e.target_slice.end if (e.target_slice and e.target_slice.end is not None) else -1

                if e.repeat > 1 or e.repeat_until is not None:
                    ops.append(
                        RepeatSliceOp(
                            source=e.source,
                            source_port=e.source_port,
                            is_back_edge=is_back,
                            src_start=src_start,
                            src_end=src_end,
                            dst_start=dst_start,
                            dst_end=dst_end,
                            repeat=int(e.repeat),
                            repeat_until=e.repeat_until,
                        )
                    )
                else:
                    ops.append(
                        CopySliceOp(
                            source=e.source,
                            source_port=e.source_port,
                            is_back_edge=is_back,
                            src_start=src_start,
                            src_end=src_end,
                            dst_start=dst_start,
                            dst_end=dst_end,
                        )
                    )

            programs[(target_node_id, port_name)] = InputPortProgram(
                target=port,
                buffer_key=(target_node_id, port_name),
                fixed_rows=fixed_rows,
                fixed_cols=fixed_cols,
                passthrough=None,
                passthrough_is_back_edge=False,
                ops=tuple(ops),
            )

    return programs
