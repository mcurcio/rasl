"""
Node monitoring and health tracking for RASL.

Tracks node performance, health states, and system-wide metrics
for observability and debugging.
"""

import logging
import time
from typing import Any, Callable, Dict, List, Optional
from collections import defaultdict, deque

from .types import NodeState, NodeStatus

logger = logging.getLogger(__name__)


class NodeMonitor:
    """
    Centralized monitoring for all node states and performance.
    
    Tracks:
    - Node health and error states
    - Performance metrics (execution times, throughput)
    - System events (failures, state changes)
    - Historical data for analysis
    """
    
    def __init__(self, history_size: int = 1000):
        self.history_size = history_size
        
        # Node status tracking
        self._node_statuses: Dict[str, NodeStatus] = {}
        
        # Event handling
        self._event_handlers: List[Callable[[str, Dict], None]] = []
        
        # Metrics history
        self._metrics_history: deque = deque(maxlen=history_size)
        self._event_history: deque = deque(maxlen=history_size)
        
        # Performance counters
        self._frame_count = 0
        self._total_frame_time = 0.0
        self._start_time = time.time()
    
    def register_event_handler(self, handler: Callable[[str, Dict], None]) -> None:
        """Register a handler for monitoring events."""
        self._event_handlers.append(handler)
    
    def unregister_event_handler(self, handler: Callable[[str, Dict], None]) -> None:
        """Unregister an event handler."""
        if handler in self._event_handlers:
            self._event_handlers.remove(handler)
    
    def emit_event(self, event_type: str, **data) -> None:
        """Emit a monitoring event to all registered handlers."""
        event = {
            "type": event_type,
            "timestamp": time.time(),
            **data
        }
        
        # Store in history
        self._event_history.append(event)
        
        # Notify handlers
        for handler in self._event_handlers:
            try:
                handler(event_type, event)
            except Exception as e:
                # Don't let monitoring failures break the system
                logger.warning(f"Event handler failed: {e}")
    
    def record_node_success(self, node_id: str, frame_time: float, eval_time: float = 0.0) -> None:
        """Record successful node evaluation."""
        status = self._get_or_create_status(node_id)
        status.update_success(eval_time, frame_time)
        
        # Emit success event for high-frequency monitoring
        if status.total_evaluations % 100 == 0:  # Throttle events
            self.emit_event("node_milestone", 
                          node_id=node_id, 
                          evaluations=status.total_evaluations,
                          avg_time=status.avg_eval_time)
    
    def record_node_error(self, node_id: str, error: Exception) -> None:
        """Record node evaluation error."""
        status = self._get_or_create_status(node_id)
        old_state = status.state
        status.update_error(error)
        
        # Emit appropriate event based on state change
        if status.state != old_state:
            if status.state == NodeState.FAILED:
                self.emit_event("node_failed", 
                              node_id=node_id, 
                              error=str(error),
                              error_count=status.error_count)
            elif status.state == NodeState.RECOVERING:
                self.emit_event("node_recovering", 
                              node_id=node_id, 
                              error=str(error),
                              error_count=status.error_count)
        else:
            self.emit_event("node_error", 
                          node_id=node_id, 
                          error=str(error),
                          error_count=status.error_count)
    
    def record_frame_completion(self, frame_seq: int, frame_time: float, processing_time: float) -> None:
        """Record completion of a frame."""
        self._frame_count += 1
        self._total_frame_time += processing_time
        
        # Store metrics
        metrics = {
            "timestamp": time.time(),
            "frame": frame_seq,
            "frame_time": frame_time,
            "processing_time": processing_time,
            "fps": self.get_current_fps()
        }
        self._metrics_history.append(metrics)
        
        # Emit periodic frame events
        if frame_seq % 30 == 0:  # Every 30 frames (~1 second at 30fps)
            self.emit_event("frame_stats", **metrics)
    
    def get_node_status(self, node_id: str) -> Optional[NodeStatus]:
        """Get current status for a specific node."""
        return self._node_statuses.get(node_id)
    
    def get_all_node_statuses(self) -> Dict[str, NodeStatus]:
        """Get status for all monitored nodes."""
        return dict(self._node_statuses)
    
    def get_health_summary(self) -> Dict[str, Any]:
        """Get overall system health summary."""
        if not self._node_statuses:
            return {
                "total_nodes": 0,
                "healthy": 0,
                "failed": 0,
                "recovering": 0,
                "disabled": 0,
                "overall_health": "unknown"
            }
        
        states = [status.state for status in self._node_statuses.values()]
        state_counts = {
            "healthy": states.count(NodeState.HEALTHY),
            "failed": states.count(NodeState.FAILED),
            "recovering": states.count(NodeState.RECOVERING),
            "disabled": states.count(NodeState.DISABLED),
            "initializing": states.count(NodeState.INITIALIZING)
        }
        
        # Determine overall health
        if state_counts["failed"] > 0:
            overall_health = "critical"
        elif state_counts["recovering"] > 0:
            overall_health = "degraded"
        elif state_counts["healthy"] == len(states):
            overall_health = "healthy"
        else:
            overall_health = "unknown"
        
        return {
            "total_nodes": len(states),
            "overall_health": overall_health,
            **state_counts
        }
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """Get performance metrics summary."""
        current_fps = self.get_current_fps()
        avg_frame_time = self._total_frame_time / max(self._frame_count, 1)
        
        # Node performance stats
        node_perf = {}
        for node_id, status in self._node_statuses.items():
            node_perf[node_id] = {
                "avg_eval_time_ms": status.avg_eval_time * 1000,
                "total_evaluations": status.total_evaluations,
                "error_rate": status.error_count / max(status.total_evaluations, 1),
                "last_success": status.last_success
            }
        
        return {
            "uptime_seconds": time.time() - self._start_time,
            "total_frames": self._frame_count,
            "current_fps": current_fps,
            "avg_frame_time_ms": avg_frame_time * 1000,
            "nodes": node_perf
        }
    
    def get_current_fps(self) -> float:
        """Calculate current frames per second."""
        if self._frame_count == 0:
            return 0.0
        
        elapsed = time.time() - self._start_time
        if elapsed <= 0:
            return 0.0
        
        return self._frame_count / elapsed
    
    def get_recent_events(self, event_type: Optional[str] = None, limit: int = 50) -> List[Dict]:
        """Get recent events, optionally filtered by type."""
        events = list(self._event_history)
        
        if event_type:
            events = [e for e in events if e["type"] == event_type]
        
        return events[-limit:]
    
    def get_metrics_history(self, limit: int = 100) -> List[Dict]:
        """Get recent performance metrics."""
        return list(self._metrics_history)[-limit:]
    
    def reset_statistics(self) -> None:
        """Reset all statistics (for testing or restart)."""
        self._node_statuses.clear()
        self._metrics_history.clear()
        self._event_history.clear()
        self._frame_count = 0
        self._total_frame_time = 0.0
        self._start_time = time.time()
    
    def _get_or_create_status(self, node_id: str) -> NodeStatus:
        """Get existing node status or create a new one."""
        if node_id not in self._node_statuses:
            self._node_statuses[node_id] = NodeStatus()
        return self._node_statuses[node_id]


class PerformanceProfiler:
    """
    Detailed performance profiler for identifying bottlenecks.
    
    Provides more detailed timing and analysis than the basic monitor.
    """
    
    def __init__(self):
        self._timing_data: Dict[str, List[float]] = defaultdict(list)
        self._call_counts: Dict[str, int] = defaultdict(int)
        self._active_timers: Dict[str, float] = {}
    
    def start_timer(self, name: str) -> None:
        """Start timing an operation."""
        self._active_timers[name] = time.perf_counter()
    
    def end_timer(self, name: str) -> float:
        """End timing and record the duration."""
        if name not in self._active_timers:
            raise ValueError(f"Timer '{name}' was not started")
        
        duration = time.perf_counter() - self._active_timers[name]
        del self._active_timers[name]
        
        self._timing_data[name].append(duration)
        self._call_counts[name] += 1
        
        return duration
    
    def get_profile_report(self) -> Dict[str, Any]:
        """Generate a performance profile report."""
        report = {}
        
        for name, times in self._timing_data.items():
            if not times:
                continue
            
            report[name] = {
                "count": len(times),
                "total_time": sum(times),
                "avg_time": sum(times) / len(times),
                "min_time": min(times),
                "max_time": max(times),
                "total_time_ms": sum(times) * 1000,
                "avg_time_ms": (sum(times) / len(times)) * 1000
            }
        
        return report
    
    def reset(self) -> None:
        """Reset all profiling data."""
        self._timing_data.clear()
        self._call_counts.clear()
        self._active_timers.clear()


# Context manager for easy profiling
class ProfiledOperation:
    """Context manager for profiling operations."""
    
    def __init__(self, profiler: PerformanceProfiler, name: str):
        self.profiler = profiler
        self.name = name
    
    def __enter__(self):
        self.profiler.start_timer(self.name)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.profiler.end_timer(self.name)
