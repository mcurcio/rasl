"""
Main RASL execution engine.

Coordinates scheduler, executor, validation, and monitoring to run
animation graphs in real-time.
"""

import asyncio
import logging
from typing import List, Optional, Sequence

from .types import Frame, NodeStatus
from .nodes import Sink
from .scheduler import Scheduler
from .executor import Executor
from .validator import Validator
from .monitor import NodeMonitor
from .ports import get_connection_registry, PortRef

logger = logging.getLogger(__name__)


class Engine:
    """
    Main execution engine that coordinates all RASL components.
    
    Responsibilities:
    - Validate graph structure and connections
    - Run scheduler to generate frames
    - Execute nodes via executor for each frame
    - Monitor node health and performance
    - Handle graceful shutdown and error recovery
    """
    
    def __init__(
        self,
        *,
        sinks: Sequence[Sink],
        scheduler: Scheduler,
        executor: Optional[Executor] = None,
        validator: Optional[Validator] = None,
        monitor: Optional[NodeMonitor] = None,
        max_frame_errors: int = 10,
    ):
        self.sinks = list(sinks)
        self.scheduler = scheduler
        self.executor = executor or Executor()
        self.validator = validator or Validator()
        self.monitor = monitor or NodeMonitor()
        self.max_frame_errors = max_frame_errors
        
        self._running = False
        self._frame_task: Optional[asyncio.Task] = None
        self._consecutive_errors = 0
        
        # TODO: Fix graph validation - skip for MVP
        # self._validate_graph()
    
    async def start(self) -> None:
        """Start the execution engine."""
        if self._running:
            raise RuntimeError("Engine is already running")
        
        logger.info("Starting RASL engine...")
        self._running = True
        self._consecutive_errors = 0
        
        # Start frame processing task in background
        self._frame_task = asyncio.create_task(self._frame_loop())
        
        logger.info("RASL engine started")
        # Don't await the frame task here - let it run in background
        # The app will handle waiting for shutdown signals
    
    async def stop(self) -> None:
        """Stop the execution engine."""
        if not self._running:
            return
        
        logger.info("Stopping RASL engine...")
        self._running = False
        
        # Stop scheduler
        self.scheduler.stop()
        
        # Cancel frame processing
        if self._frame_task:
            self._frame_task.cancel()
            try:
                await self._frame_task
            except asyncio.CancelledError:
                pass
    
    async def restart(self) -> None:
        """Restart the engine (for hot-reload)."""
        logger.info("Restarting RASL engine...")
        await self.stop()
        
        # Re-validate graph
        self._validate_graph()
        
        await self.start()
    
    async def tick_once(self) -> None:
        """Execute exactly one frame (for testing)."""
        if self._running:
            raise RuntimeError("Cannot tick_once while engine is running")
        
        # Generate a single frame
        frame = Frame.now(seq=0)
        await self._process_frame(frame)
    
    def get_node_status(self, node_id: str) -> Optional[NodeStatus]:
        """Get status for a specific node."""
        return self.monitor.get_node_status(node_id)
    
    def get_health_summary(self):
        """Get overall engine health summary."""
        return self.monitor.get_health_summary()
    
    async def _frame_loop(self) -> None:
        """Main frame processing loop."""
        logger.info("Starting frame processing loop")
        
        async for frame in self.scheduler.frames():
            if not self._running:
                break
            
            try:
                await self._process_frame(frame)
                self._consecutive_errors = 0
                
            except Exception as e:
                self._consecutive_errors += 1
                logger.error(f"Frame {frame.seq} failed: {e}")
                
                self.monitor.emit_event("frame_error", 
                                      frame=frame.seq, 
                                      error=str(e),
                                      consecutive_errors=self._consecutive_errors)
                
                if self._consecutive_errors >= self.max_frame_errors:
                    logger.critical(f"Too many consecutive frame errors ({self._consecutive_errors}), stopping engine")
                    break
        
        logger.info("Frame processing loop ended")
    
    async def _process_frame(self, frame: Frame) -> None:
        """Process a single frame."""
        # Reset executor frame cache
        self.executor.reset_frame_cache(frame)
        
        # Process each sink
        for sink in self.sinks:
            try:
                await self._process_sink(sink, frame)
            except Exception as e:
                # Sink isolation - one sink failure doesn't stop others
                logger.warning(f"Sink {sink.id} failed on frame {frame.seq}: {e}")
                self.monitor.record_node_error(sink.id, e)
        
        # Emit frame completion event
        self.monitor.emit_event("frame_completed", 
                              frame=frame.seq, 
                              time=frame.t,
                              dt=frame.dt)
    
    async def _process_sink(self, sink: Sink, frame: Frame) -> None:
        """Process a single sink for the given frame."""
        # Check if sink should emit this frame
        # TODO: Implement rate limiting logic here
        
        # Materialize sink inputs by finding what's connected to them
        inputs = {}
        for port_ref in sink.ports.list("in"):
            try:
                # Find what output port is connected to this input port
                registry = get_connection_registry()
                
                # Look for a connection that feeds into this input port
                source_port = None
                for edge in registry.get_edges():
                    if edge.dst_id == sink.id and edge.dst_port == port_ref.name:
                        # Found the source that feeds this input
                        source_port = PortRef(
                            node_id=edge.src_id,
                            name=edge.src_port,
                            kind="out",
                            schema=None  # Will be filled by executor
                        )
                        break
                
                if source_port is None:
                    logger.warning(f"No connection found for {sink.id}.{port_ref.name}")
                    continue
                
                # Materialize the source output
                data = await self.executor.materialize(source_port, frame)
                inputs[port_ref.name] = data
                
            except Exception as e:
                logger.error(f"Failed to materialize input for {sink.id}.{port_ref.name}: {e}")
                raise
        
        # Emit to sink
        try:
            sink.emit(frame, **inputs)
            self.monitor.record_node_success(sink.id, frame.t)
        except Exception as e:
            self.monitor.record_node_error(sink.id, e)
            raise
    
    def _validate_graph(self) -> None:
        """Validate the current graph structure."""
        try:
            self.validator.validate_global(self.sinks)
            logger.info("Graph validation passed")
        except Exception as e:
            logger.error(f"Graph validation failed: {e}")
            raise


# Convenience function for creating engines
def create_engine(
    sinks: Sequence[Sink],
    scheduler: Scheduler,
    **kwargs
) -> Engine:
    """Create a new engine with default components."""
    return Engine(sinks=sinks, scheduler=scheduler, **kwargs)
