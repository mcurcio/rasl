"""
Tests for node monitoring and performance tracking.
"""

import pytest
import time
from unittest.mock import Mock

from rasl.core.monitor import NodeMonitor, PerformanceProfiler, ProfiledOperation
from rasl.core.types import NodeState


class TestNodeMonitor:
    """Test NodeMonitor functionality."""
    
    def setup_method(self):
        """Set up test monitor."""
        self.monitor = NodeMonitor(history_size=10)
    
    def test_monitor_creation(self):
        """Test basic monitor creation."""
        assert self.monitor.history_size == 10
        assert len(self.monitor._node_statuses) == 0
        assert len(self.monitor._event_handlers) == 0
    
    def test_event_handler_registration(self):
        """Test event handler registration and unregistration."""
        handler1 = Mock()
        handler2 = Mock()
        
        # Register handlers
        self.monitor.register_event_handler(handler1)
        self.monitor.register_event_handler(handler2)
        
        assert len(self.monitor._event_handlers) == 2
        
        # Unregister one handler
        self.monitor.unregister_event_handler(handler1)
        assert len(self.monitor._event_handlers) == 1
        assert handler2 in self.monitor._event_handlers
    
    def test_event_emission(self):
        """Test event emission to handlers."""
        handler = Mock()
        self.monitor.register_event_handler(handler)
        
        # Emit an event
        self.monitor.emit_event("test_event", node_id="test_node", value=42)
        
        # Handler should have been called
        handler.assert_called_once()
        
        # Check call arguments
        event_type, event_data = handler.call_args[0]
        assert event_type == "test_event"
        assert event_data["type"] == "test_event"
        assert event_data["node_id"] == "test_node"
        assert event_data["value"] == 42
        assert "timestamp" in event_data
    
    def test_event_handler_failure_isolation(self):
        """Test that handler failures don't break monitoring."""
        good_handler = Mock()
        bad_handler = Mock(side_effect=Exception("Handler failed"))
        
        self.monitor.register_event_handler(good_handler)
        self.monitor.register_event_handler(bad_handler)
        
        # Emit event - should not raise despite bad handler
        self.monitor.emit_event("test_event")
        
        # Good handler should still be called
        good_handler.assert_called_once()
        bad_handler.assert_called_once()
    
    def test_record_node_success(self):
        """Test recording successful node evaluations."""
        node_id = "test_node"
        
        # Record success
        self.monitor.record_node_success(node_id, frame_time=1.0, eval_time=0.001)
        
        # Check status
        status = self.monitor.get_node_status(node_id)
        assert status is not None
        assert status.state == NodeState.HEALTHY
        assert status.total_evaluations == 1
        assert status.error_count == 0
        assert status.last_success == 1.0
        assert status.avg_eval_time == 0.001
    
    def test_record_node_error(self):
        """Test recording node errors."""
        node_id = "test_node"
        error = ValueError("Test error")
        
        # Record error
        self.monitor.record_node_error(node_id, error)
        
        # Check status
        status = self.monitor.get_node_status(node_id)
        assert status is not None
        assert status.state == NodeState.RECOVERING
        assert status.error_count == 1
        assert status.last_error == error
    
    def test_node_state_progression(self):
        """Test node state progression through errors."""
        node_id = "test_node"
        error = ValueError("Test error")
        
        # First error -> RECOVERING
        self.monitor.record_node_error(node_id, error)
        status = self.monitor.get_node_status(node_id)
        assert status.state == NodeState.RECOVERING
        
        # More errors -> FAILED
        self.monitor.record_node_error(node_id, error)
        self.monitor.record_node_error(node_id, error)
        status = self.monitor.get_node_status(node_id)
        assert status.state == NodeState.FAILED
        
        # Success should reset to HEALTHY
        self.monitor.record_node_success(node_id, frame_time=2.0, eval_time=0.001)
        status = self.monitor.get_node_status(node_id)
        assert status.state == NodeState.HEALTHY
        assert status.error_count == 0
    
    def test_frame_completion_recording(self):
        """Test recording frame completion metrics."""
        # Record some frame completions
        for i in range(5):
            self.monitor.record_frame_completion(
                frame_seq=i,
                frame_time=i * 0.1,
                processing_time=0.01
            )
        
        # Check metrics history
        metrics = self.monitor.get_metrics_history()
        assert len(metrics) == 5
        
        # Check FPS calculation
        fps = self.monitor.get_current_fps()
        assert fps > 0
    
    def test_health_summary(self):
        """Test health summary generation."""
        # Initially no nodes
        summary = self.monitor.get_health_summary()
        assert summary["total_nodes"] == 0
        assert summary["overall_health"] == "unknown"
        
        # Add some nodes with different states
        self.monitor.record_node_success("healthy_node", 1.0, 0.001)
        self.monitor.record_node_error("failing_node", ValueError("error"))
        
        summary = self.monitor.get_health_summary()
        assert summary["total_nodes"] == 2
        assert summary["healthy"] == 1
        assert summary["recovering"] == 1
        assert summary["overall_health"] == "degraded"
    
    def test_performance_summary(self):
        """Test performance summary generation."""
        node_id = "test_node"
        
        # Record some activity
        self.monitor.record_node_success(node_id, 1.0, 0.001)
        self.monitor.record_node_success(node_id, 1.1, 0.002)
        
        summary = self.monitor.get_performance_summary()
        
        assert "uptime_seconds" in summary
        assert "total_frames" in summary
        assert "current_fps" in summary
        assert "nodes" in summary
        
        node_perf = summary["nodes"][node_id]
        assert node_perf["total_evaluations"] == 2
        assert node_perf["avg_eval_time_ms"] > 0
        assert node_perf["error_rate"] == 0.0
    
    def test_recent_events(self):
        """Test recent events retrieval."""
        # Emit some events
        self.monitor.emit_event("event1", data="a")
        self.monitor.emit_event("event2", data="b")
        self.monitor.emit_event("event1", data="c")
        
        # Get all recent events
        all_events = self.monitor.get_recent_events()
        assert len(all_events) == 3
        
        # Get filtered events
        event1_only = self.monitor.get_recent_events(event_type="event1")
        assert len(event1_only) == 2
        assert all(e["type"] == "event1" for e in event1_only)
        
        # Test limit
        limited = self.monitor.get_recent_events(limit=2)
        assert len(limited) == 2
    
    def test_statistics_reset(self):
        """Test resetting all statistics."""
        # Add some data
        self.monitor.record_node_success("test_node", 1.0, 0.001)
        self.monitor.emit_event("test_event")
        self.monitor.record_frame_completion(0, 1.0, 0.01)
        
        # Verify data exists
        assert len(self.monitor._node_statuses) > 0
        assert len(self.monitor._event_history) > 0
        assert len(self.monitor._metrics_history) > 0
        
        # Reset
        self.monitor.reset_statistics()
        
        # Verify data is cleared
        assert len(self.monitor._node_statuses) == 0
        assert len(self.monitor._event_history) == 0
        assert len(self.monitor._metrics_history) == 0
        assert self.monitor._frame_count == 0


class TestPerformanceProfiler:
    """Test PerformanceProfiler functionality."""
    
    def setup_method(self):
        """Set up test profiler."""
        self.profiler = PerformanceProfiler()
    
    def test_timer_operations(self):
        """Test basic timer start/stop operations."""
        # Start timer
        self.profiler.start_timer("test_op")
        
        # Simulate some work
        time.sleep(0.001)
        
        # End timer
        duration = self.profiler.end_timer("test_op")
        
        assert duration > 0
        assert duration < 0.1  # Should be very small
    
    def test_timer_not_started_error(self):
        """Test error when ending timer that wasn't started."""
        with pytest.raises(ValueError, match="Timer 'nonexistent' was not started"):
            self.profiler.end_timer("nonexistent")
    
    def test_multiple_timings(self):
        """Test multiple timings of the same operation."""
        # Time the same operation multiple times
        for i in range(3):
            self.profiler.start_timer("repeated_op")
            time.sleep(0.001)
            self.profiler.end_timer("repeated_op")
        
        # Check profile report
        report = self.profiler.get_profile_report()
        
        assert "repeated_op" in report
        op_stats = report["repeated_op"]
        
        assert op_stats["count"] == 3
        assert op_stats["total_time"] > 0
        assert op_stats["avg_time"] > 0
        assert op_stats["min_time"] > 0
        assert op_stats["max_time"] > 0
    
    def test_profile_report(self):
        """Test profile report generation."""
        # Time different operations
        operations = ["op1", "op2", "op3"]
        
        for op in operations:
            self.profiler.start_timer(op)
            time.sleep(0.001)
            self.profiler.end_timer(op)
        
        report = self.profiler.get_profile_report()
        
        # Should have stats for all operations
        for op in operations:
            assert op in report
            stats = report[op]
            assert "count" in stats
            assert "total_time" in stats
            assert "avg_time" in stats
            assert "min_time" in stats
            assert "max_time" in stats
            assert "total_time_ms" in stats
            assert "avg_time_ms" in stats
    
    def test_profiler_reset(self):
        """Test profiler reset functionality."""
        # Add some timing data
        self.profiler.start_timer("test_op")
        time.sleep(0.001)
        self.profiler.end_timer("test_op")
        
        # Verify data exists
        report = self.profiler.get_profile_report()
        assert len(report) > 0
        
        # Reset
        self.profiler.reset()
        
        # Verify data is cleared
        report = self.profiler.get_profile_report()
        assert len(report) == 0


class TestProfiledOperation:
    """Test ProfiledOperation context manager."""
    
    def setup_method(self):
        """Set up test profiler."""
        self.profiler = PerformanceProfiler()
    
    def test_context_manager_success(self):
        """Test successful operation profiling."""
        with ProfiledOperation(self.profiler, "test_operation"):
            time.sleep(0.001)
        
        report = self.profiler.get_profile_report()
        assert "test_operation" in report
        assert report["test_operation"]["count"] == 1
    
    def test_context_manager_with_exception(self):
        """Test profiling when operation raises exception."""
        with pytest.raises(ValueError):
            with ProfiledOperation(self.profiler, "failing_operation"):
                raise ValueError("Test error")
        
        # Should still record the timing
        report = self.profiler.get_profile_report()
        assert "failing_operation" in report
        assert report["failing_operation"]["count"] == 1
