"""
Timing and frame generation for RASL.

Provides different scheduling strategies for generating frames at
consistent intervals with various cadence recovery policies.
"""

import asyncio
import time
from abc import ABC, abstractmethod
from typing import AsyncIterator, Optional, Protocol

from .types import Frame


class Clock(Protocol):
    """Loop-safe wall-clock interface."""
    
    def now(self) -> float:
        """Return monotonic time in seconds."""
        ...


class MonotonicClock:
    """Default clock implementation using time.perf_counter()."""
    
    def now(self) -> float:
        return time.perf_counter()


class Scheduler(ABC):
    """
    Abstract base class for frame schedulers.
    
    Schedulers are responsible for generating Frame objects at appropriate
    intervals with various cadence recovery policies.
    """
    
    @abstractmethod
    async def frames(self) -> AsyncIterator[Frame]:
        """Generate frames asynchronously."""
        ...
    
    @abstractmethod
    def stop(self) -> None:
        """Stop frame generation."""
        ...


class FixedRateScheduler(Scheduler):
    """
    Fixed frame rate scheduler with configurable cadence recovery.
    
    Generates frames at a target rate with different policies for handling
    timing overruns or system delays.
    """
    
    def __init__(
        self,
        clock: Clock,
        target_hz: float,
        cadence: str = "drop",  # "drop", "skip", "slow"
        max_frame_time: float = 0.1,  # Maximum time per frame before warning
    ):
        self.clock = clock
        self.target_hz = target_hz
        self.cadence = cadence
        self.max_frame_time = max_frame_time
        
        self.frame_interval = 1.0 / target_hz
        self._running = False
        self._start_time: Optional[float] = None
        self._last_frame_time: Optional[float] = None
        self._frame_seq = 0
        
        # Statistics
        self.frames_generated = 0
        self.frames_dropped = 0
        self.frames_late = 0
    
    async def frames(self) -> AsyncIterator[Frame]:
        """Generate frames at the target rate."""
        self._running = True
        self._start_time = self.clock.now()
        self._last_frame_time = self._start_time
        self._frame_seq = 0
        
        next_frame_time = self._start_time
        
        while self._running:
            current_time = self.clock.now()
            
            # Check if we're behind schedule
            if current_time >= next_frame_time:
                # Generate frame
                dt = current_time - self._last_frame_time if self._last_frame_time else 0.0
                frame = Frame(t=current_time, dt=dt, seq=self._frame_seq)
                
                self._last_frame_time = current_time
                self._frame_seq += 1
                self.frames_generated += 1
                
                # Handle cadence recovery
                if current_time > next_frame_time + self.frame_interval:
                    # We're running late
                    self.frames_late += 1
                    
                    if self.cadence == "drop":
                        # Skip frames to catch up
                        missed_frames = int((current_time - next_frame_time) / self.frame_interval)
                        self.frames_dropped += missed_frames
                        next_frame_time += (missed_frames + 1) * self.frame_interval
                    elif self.cadence == "skip":
                        # Just move to next scheduled frame
                        next_frame_time += self.frame_interval
                    elif self.cadence == "slow":
                        # Run at actual rate, don't try to catch up
                        next_frame_time = current_time + self.frame_interval
                else:
                    # On time, schedule next frame normally
                    next_frame_time += self.frame_interval
                
                yield frame
            else:
                # Wait until next frame time
                sleep_time = next_frame_time - current_time
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
    
    def stop(self) -> None:
        """Stop frame generation."""
        self._running = False
    
    def get_stats(self) -> dict:
        """Get scheduler statistics."""
        return {
            "target_hz": self.target_hz,
            "cadence": self.cadence,
            "frames_generated": self.frames_generated,
            "frames_dropped": self.frames_dropped,
            "frames_late": self.frames_late,
            "actual_hz": self._calculate_actual_hz(),
        }
    
    def _calculate_actual_hz(self) -> float:
        """Calculate actual frame rate."""
        if not self._start_time or self.frames_generated == 0:
            return 0.0
        
        elapsed = self.clock.now() - self._start_time
        if elapsed <= 0:
            return 0.0
        
        return self.frames_generated / elapsed


class ManualScheduler(Scheduler):
    """
    Manual scheduler for testing and step-by-step execution.
    
    Frames are generated only when explicitly requested.
    """
    
    def __init__(self, clock: Clock):
        self.clock = clock
        self._frame_queue: asyncio.Queue = asyncio.Queue()
        self._running = False
        self._frame_seq = 0
        self._last_frame_time: Optional[float] = None
    
    async def frames(self) -> AsyncIterator[Frame]:
        """Yield frames from the manual queue."""
        self._running = True
        
        while self._running:
            try:
                # Wait for next frame request
                await self._frame_queue.get()
                
                if not self._running:
                    break
                
                current_time = self.clock.now()
                dt = current_time - self._last_frame_time if self._last_frame_time else 0.0
                
                frame = Frame(t=current_time, dt=dt, seq=self._frame_seq)
                self._last_frame_time = current_time
                self._frame_seq += 1
                
                yield frame
                
            except asyncio.CancelledError:
                break
    
    def stop(self) -> None:
        """Stop the scheduler."""
        self._running = False
        # Wake up the frames() generator
        self._frame_queue.put_nowait(None)
    
    def tick(self) -> None:
        """Request generation of the next frame."""
        if self._running:
            self._frame_queue.put_nowait(True)


class AdaptiveScheduler(Scheduler):
    """
    Adaptive scheduler that adjusts frame rate based on system performance.
    
    Monitors execution time and automatically reduces frame rate if the
    system cannot keep up with the target rate.
    """
    
    def __init__(
        self,
        clock: Clock,
        target_hz: float,
        min_hz: float = 1.0,
        adaptation_window: int = 30,  # Frames to average over
        load_threshold: float = 0.8,  # CPU load threshold for adaptation
    ):
        self.clock = clock
        self.target_hz = target_hz
        self.min_hz = min_hz
        self.adaptation_window = adaptation_window
        self.load_threshold = load_threshold
        
        self._running = False
        self._current_hz = target_hz
        self._frame_times: list = []
        self._frame_seq = 0
        self._last_frame_time: Optional[float] = None
    
    async def frames(self) -> AsyncIterator[Frame]:
        """Generate frames with adaptive rate control."""
        self._running = True
        self._current_hz = self.target_hz
        self._frame_seq = 0
        self._last_frame_time = self.clock.now()
        
        while self._running:
            frame_start = self.clock.now()
            
            # Generate frame
            dt = frame_start - self._last_frame_time if self._last_frame_time else 0.0
            frame = Frame(t=frame_start, dt=dt, seq=self._frame_seq)
            
            self._last_frame_time = frame_start
            self._frame_seq += 1
            
            yield frame
            
            # Measure frame processing time
            frame_end = self.clock.now()
            frame_duration = frame_end - frame_start
            
            # Update performance tracking
            self._frame_times.append(frame_duration)
            if len(self._frame_times) > self.adaptation_window:
                self._frame_times.pop(0)
            
            # Adapt frame rate if needed
            self._adapt_frame_rate()
            
            # Sleep until next frame
            frame_interval = 1.0 / self._current_hz
            sleep_time = frame_interval - frame_duration
            
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)
    
    def stop(self) -> None:
        """Stop the scheduler."""
        self._running = False
    
    def _adapt_frame_rate(self) -> None:
        """Adapt frame rate based on recent performance."""
        if len(self._frame_times) < self.adaptation_window:
            return
        
        # Calculate average frame processing time
        avg_frame_time = sum(self._frame_times) / len(self._frame_times)
        current_interval = 1.0 / self._current_hz
        
        # Calculate CPU load (frame time / total time)
        cpu_load = avg_frame_time / current_interval
        
        if cpu_load > self.load_threshold:
            # System is overloaded, reduce frame rate
            new_hz = max(self.min_hz, self._current_hz * 0.9)
            if new_hz != self._current_hz:
                self._current_hz = new_hz
        elif cpu_load < self.load_threshold * 0.5 and self._current_hz < self.target_hz:
            # System has headroom, increase frame rate
            new_hz = min(self.target_hz, self._current_hz * 1.1)
            if new_hz != self._current_hz:
                self._current_hz = new_hz
    
    def get_current_hz(self) -> float:
        """Get current adaptive frame rate."""
        return self._current_hz
