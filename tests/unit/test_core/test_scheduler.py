"""
Tests for RASL schedulers and timing.
"""

import pytest
import asyncio
import time
from unittest.mock import Mock

from rasl.core.scheduler import (
    MonotonicClock, FixedRateScheduler, ManualScheduler, AdaptiveScheduler
)
from rasl.core.types import Frame


class MockClock:
    """Mock clock for deterministic testing."""
    
    def __init__(self, start_time: float = 0.0):
        self._time = start_time
    
    def now(self) -> float:
        return self._time
    
    def advance(self, seconds: float):
        """Advance the mock clock."""
        self._time += seconds


class TestMonotonicClock:
    """Test MonotonicClock implementation."""
    
    def test_monotonic_clock(self):
        """Test that clock returns increasing values."""
        clock = MonotonicClock()
        
        time1 = clock.now()
        time.sleep(0.001)  # Small delay
        time2 = clock.now()
        
        assert time2 > time1
        assert isinstance(time1, float)
        assert isinstance(time2, float)


class TestFixedRateScheduler:
    """Test FixedRateScheduler functionality."""
    
    def setup_method(self):
        """Set up test scheduler."""
        self.mock_clock = MockClock(0.0)
        self.scheduler = FixedRateScheduler(
            clock=self.mock_clock,
            target_hz=10.0,  # 10 FPS = 0.1s intervals
            cadence="drop"
        )
    
    @pytest.mark.asyncio
    async def test_frame_generation(self):
        """Test basic frame generation."""
        frames = []
        
        # Start scheduler
        frame_gen = self.scheduler.frames()
        
        # Collect a few frames
        for i in range(3):
            self.mock_clock.advance(0.1)  # Advance by frame interval
            frame = await frame_gen.__anext__()
            frames.append(frame)
        
        # Stop scheduler
        self.scheduler.stop()
        
        # Verify frames
        assert len(frames) == 3
        
        for i, frame in enumerate(frames):
            assert isinstance(frame, Frame)
            assert frame.seq == i
            assert frame.t == (i + 1) * 0.1  # Times should match clock advances
    
    @pytest.mark.asyncio
    async def test_frame_timing(self):
        """Test frame timing and intervals."""
        frames = []
        
        frame_gen = self.scheduler.frames()
        
        # Generate frames at exact intervals
        for i in range(3):
            self.mock_clock.advance(0.1)
            frame = await frame_gen.__anext__()
            frames.append(frame)
        
        self.scheduler.stop()
        
        # Check timing
        assert frames[0].dt == 0.0  # First frame has no delta
        assert frames[1].dt == 0.1  # Second frame has correct delta
        assert frames[2].dt == 0.1  # Third frame has correct delta
    
    @pytest.mark.asyncio
    async def test_cadence_drop(self):
        """Test drop cadence recovery."""
        scheduler = FixedRateScheduler(
            clock=self.mock_clock,
            target_hz=10.0,
            cadence="drop"
        )
        
        frames = []
        frame_gen = scheduler.frames()
        
        # First frame on time
        self.mock_clock.advance(0.1)
        frame1 = await frame_gen.__anext__()
        frames.append(frame1)
        
        # Second frame very late (should drop frames to catch up)
        self.mock_clock.advance(0.35)  # 3.5 intervals late
        frame2 = await frame_gen.__anext__()
        frames.append(frame2)
        
        scheduler.stop()
        
        # Should have dropped some frames
        assert scheduler.frames_dropped > 0
        assert scheduler.frames_late > 0
    
    def test_scheduler_stats(self):
        """Test scheduler statistics."""
        stats = self.scheduler.get_stats()
        
        assert "target_hz" in stats
        assert "cadence" in stats
        assert "frames_generated" in stats
        assert "frames_dropped" in stats
        assert "frames_late" in stats
        assert "actual_hz" in stats
        
        assert stats["target_hz"] == 10.0
        assert stats["cadence"] == "drop"


class TestManualScheduler:
    """Test ManualScheduler functionality."""
    
    def setup_method(self):
        """Set up test scheduler."""
        self.mock_clock = MockClock(0.0)
        self.scheduler = ManualScheduler(self.mock_clock)
    
    @pytest.mark.asyncio
    async def test_manual_frame_generation(self):
        """Test manual frame triggering."""
        frames = []
        
        # Start scheduler
        frame_gen = self.scheduler.frames()
        
        # Create task to collect frames
        async def collect_frames():
            async for frame in frame_gen:
                frames.append(frame)
                if len(frames) >= 3:
                    break
        
        collect_task = asyncio.create_task(collect_frames())
        
        # Manually trigger frames
        for i in range(3):
            self.mock_clock.advance(0.1)
            self.scheduler.tick()
            await asyncio.sleep(0.001)  # Let the async generator run
        
        # Stop and wait
        self.scheduler.stop()
        await collect_task
        
        # Verify frames
        assert len(frames) == 3
        for i, frame in enumerate(frames):
            assert frame.seq == i
    
    @pytest.mark.asyncio
    async def test_manual_scheduler_stop(self):
        """Test manual scheduler stopping."""
        frame_gen = self.scheduler.frames()
        
        # Start collecting frames
        frames = []
        async def collect():
            async for frame in frame_gen:
                frames.append(frame)
        
        collect_task = asyncio.create_task(collect())
        
        # Trigger one frame
        self.scheduler.tick()
        await asyncio.sleep(0.001)
        
        # Stop scheduler
        self.scheduler.stop()
        await collect_task
        
        assert len(frames) == 1


class TestAdaptiveScheduler:
    """Test AdaptiveScheduler functionality."""
    
    def setup_method(self):
        """Set up test scheduler."""
        self.mock_clock = MockClock(0.0)
        self.scheduler = AdaptiveScheduler(
            clock=self.mock_clock,
            target_hz=10.0,
            min_hz=5.0,
            adaptation_window=5
        )
    
    @pytest.mark.asyncio
    async def test_adaptive_frame_generation(self):
        """Test basic adaptive frame generation."""
        frames = []
        
        frame_gen = self.scheduler.frames()
        
        # Collect a few frames
        for i in range(3):
            self.mock_clock.advance(0.1)
            frame = await frame_gen.__anext__()
            frames.append(frame)
        
        self.scheduler.stop()
        
        # Should generate frames normally
        assert len(frames) == 3
        assert all(isinstance(f, Frame) for f in frames)
    
    def test_current_hz_tracking(self):
        """Test current frame rate tracking."""
        initial_hz = self.scheduler.get_current_hz()
        assert initial_hz == 10.0  # Should start at target
        
        # After adaptation, might be different
        # (This is hard to test without actually running the scheduler)


class TestSchedulerIntegration:
    """Integration tests for schedulers."""
    
    @pytest.mark.asyncio
    async def test_real_time_scheduler(self):
        """Test scheduler with real clock (timing sensitive)."""
        clock = MonotonicClock()
        scheduler = FixedRateScheduler(clock, target_hz=100.0)  # Fast rate for quick test
        
        frames = []
        start_time = clock.now()
        
        frame_gen = scheduler.frames()
        
        # Collect frames for a short time
        try:
            async with asyncio.timeout(0.1):  # 100ms timeout
                async for frame in frame_gen:
                    frames.append(frame)
        except asyncio.TimeoutError:
            pass
        
        scheduler.stop()
        
        # Should have generated some frames
        assert len(frames) > 0
        
        # Frames should have reasonable timing
        if len(frames) > 1:
            dt_values = [f.dt for f in frames[1:]]  # Skip first frame (dt=0)
            avg_dt = sum(dt_values) / len(dt_values)
            expected_dt = 1.0 / 100.0  # 0.01 seconds
            
            # Allow some tolerance for timing variations
            assert abs(avg_dt - expected_dt) < 0.005  # 5ms tolerance
