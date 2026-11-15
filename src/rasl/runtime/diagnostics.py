"""Timing diagnostics: how late ticks run, how long pulls take, what was dropped."""

from __future__ import annotations

import gc
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import structlog

from rasl.graph import InputPortProgram

logger = structlog.get_logger()


@dataclass
class TickTrace:
    """Detailed timing trace for a single tick."""
    
    tick: int
    sink_id: str
    start_time: float
    node_timings: List[Tuple[str, float, float]] = field(default_factory=list)  # (node_id, duration_ms, cumulative_ms)
    slice_timings: List[Tuple[str, str, float]] = field(default_factory=list)  # (source, target, duration_ms)
    total_ms: float = 0.0
    
    def add_node(self, node_id: str, duration_ms: float) -> None:
        cumulative = sum(t[1] for t in self.node_timings) + duration_ms
        self.node_timings.append((node_id, round(duration_ms, 3), round(cumulative, 3)))
    
    def add_slice(self, source: str, target: str, duration_ms: float) -> None:
        self.slice_timings.append((source, target, round(duration_ms, 3)))
    
    def finalize(self, end_time: float) -> None:
        self.total_ms = (end_time - self.start_time) * 1000
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "tick": self.tick,
            "sink": self.sink_id,
            "total_ms": round(self.total_ms, 2),
            "nodes": {n: {"ms": d, "cumulative": c} for n, d, c in self.node_timings},
            "slices": {f"{s}->{t}": ms for s, t, ms in self.slice_timings} if self.slice_timings else None,
        }


@dataclass
class TimingStats:
    """Timing diagnostics for scheduler performance monitoring."""

    # Per-sink tracking
    sink_last_pull: Dict[str, float] = field(default_factory=dict)
    sink_target_interval: Dict[str, float] = field(default_factory=dict)
    sink_last_target_time: Dict[str, float] = field(default_factory=dict)
    
    # Latency tracking (rolling window)
    latency_samples: deque = field(default_factory=lambda: deque(maxlen=100))
    pull_duration_samples: Dict[str, deque] = field(default_factory=dict)
    
    # Per-node timing (rolling window per node)
    node_duration_samples: Dict[str, deque] = field(default_factory=dict)
    
    # Jitter detection
    jitter_threshold_ms: float = 10.0  # Log warning if >10ms late
    slow_tick_threshold_ms: float = 20.0  # Log detailed trace if tick takes >20ms
    last_report_time: float = 0.0
    report_interval: float = 5.0  # Report stats every 5 seconds
    
    # Counters
    total_ticks: int = 0
    late_ticks: int = 0
    max_latency_ms: float = 0.0
    dropped_ticks: Dict[str, int] = field(default_factory=dict)
    """Due times each rate driver skipped because it had fallen behind."""
    dropped_since_report: Dict[str, int] = field(default_factory=dict)
    last_drop_log_time: float = 0.0
    
    # GC tracking
    gc_collections: int = 0
    
    # Current tick trace (for detailed logging)
    current_trace: Optional[TickTrace] = None
    
    # Populate profiling
    profile_populate: bool = False

    def report(self, now: float) -> None:
        """Log periodic timing diagnostics."""
        stats = self
        
        # Calculate averages
        avg_latency = sum(stats.latency_samples) / len(stats.latency_samples) if stats.latency_samples else 0
        
        # Per-sink frame rate analysis
        sink_stats = {}
        for sink_id, samples in stats.pull_duration_samples.items():
            if samples:
                avg_duration = sum(samples) / len(samples)
                max_duration = max(samples)
                target_interval_ms = stats.sink_target_interval.get(sink_id, 0) * 1000
                
                # Check if pull duration exceeds frame budget
                if max_duration > target_interval_ms * 0.8:  # >80% of budget
                    sink_stats[sink_id] = {
                        "avg_ms": round(avg_duration, 2),
                        "max_ms": round(max_duration, 2),
                        "budget_ms": round(target_interval_ms, 2),
                        "warning": "exceeds_budget" if max_duration > target_interval_ms else "near_budget",
                    }
        
        # Get GC stats
        gc_stats = gc.get_stats()
        gc_collections = sum(s.get("collections", 0) for s in gc_stats)
        gc_delta = gc_collections - stats.gc_collections
        stats.gc_collections = gc_collections
        
        # Per-node timing stats (always report all nodes when profiling)
        node_stats = {}
        for node_id, samples in stats.node_duration_samples.items():
            if samples:
                avg_ms = sum(samples) / len(samples)
                max_ms = max(samples)
                # When profiling, report all nodes; otherwise only slow ones
                if stats.profile_populate or avg_ms > 0.5 or max_ms > 2.0:
                    node_stats[node_id] = {
                        "avg_ms": round(avg_ms, 3),
                        "max_ms": round(max_ms, 3),
                    }
        
        # Populate profiling stats
        populate_stats = None
        if stats.profile_populate:
            raw_stats = InputPortProgram.get_profile_stats()
            if raw_stats:
                populate_stats = {}
                for key, s in raw_stats.items():
                    if s["count"] > 0:
                        populate_stats[f"{key[0]}.{key[1]}"] = {
                            "avg_total_ms": round(s["total_ms"] / s["count"], 3),
                            "avg_resolve_ms": round(s["resolve_ms"] / s["count"], 3),
                            "avg_asarray_ms": round(s["asarray_ms"] / s["count"], 3),
                            "avg_buffer_ms": round(s["buffer_ms"] / s["count"], 3),
                            "avg_copy_ms": round(s["copy_ms"] / s["count"], 3),
                            "count": s["count"],
                        }
                # Clear stats for next period
                InputPortProgram.enable_profiling(True)
        
        logger.info(
            "timing_report",
            total_ticks=stats.total_ticks,
            late_ticks=stats.late_ticks,
            late_pct=round(100 * stats.late_ticks / max(stats.total_ticks, 1), 1),
            avg_latency_ms=round(avg_latency, 2),
            max_latency_ms=round(stats.max_latency_ms, 2),
            dropped_ticks=dict(stats.dropped_ticks) if stats.dropped_ticks else None,
            gc_collections=gc_delta,
            sink_warnings=sink_stats if sink_stats else None,
            node_stats=node_stats if node_stats else None,
            populate_stats=populate_stats,
        )

    def record_dropped(self, dropped: Dict[str, int], now: float) -> None:
        """Count due times that were skipped, and say so at most once a second."""
        for sink_id, count in dropped.items():
            self.dropped_ticks[sink_id] = self.dropped_ticks.get(sink_id, 0) + count
            self.dropped_since_report[sink_id] = self.dropped_since_report.get(sink_id, 0) + count
        if now - self.last_drop_log_time >= 1.0:
            logger.warning("ticks_dropped", dropped=dict(self.dropped_since_report))
            self.dropped_since_report.clear()
            self.last_drop_log_time = now

    def set_rates(self, rates: Dict[str, float]) -> None:
        """Note each rate driver's target interval."""
        for sink_id, hz in rates.items():
            self.sink_target_interval[sink_id] = 1.0 / hz
            self.pull_duration_samples.setdefault(sink_id, deque(maxlen=100))

    def forget(self, node_ids: set[str]) -> None:
        """Drop what was measured for nodes that were stopped: it says nothing
        about what replaces them."""
        for node_id in node_ids:
            self.sink_target_interval.pop(node_id, None)
            self.pull_duration_samples.pop(node_id, None)
            self.sink_last_pull.pop(node_id, None)
            self.sink_last_target_time.pop(node_id, None)
