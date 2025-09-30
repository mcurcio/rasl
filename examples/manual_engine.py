"""
Manual engine creation example

Shows how to explicitly create and control the RASL engine
for advanced use cases or when you need more control.

This approach is optional - normally `rasl run` handles engine creation automatically.
"""

import asyncio
from rasl import SineSource, ScaleBias, ConsoleSink
from rasl.core.engine import Engine
from rasl.core.scheduler import FixedRateScheduler, MonotonicClock
from rasl.core.monitor import NodeMonitor

async def main():
    """Manual engine setup and execution."""
    
    # Create nodes
    sine = SineSource(freq=2.0, channels=6)
    scaler = ScaleBias(scale=0.7, bias=0.1)
    console = ConsoleSink(format="summary", update_interval=0.3)
    
    # Connect nodes
    sine >> scaler >> console
    
    # Create engine components manually
    clock = MonotonicClock()
    scheduler = FixedRateScheduler(clock, target_hz=30)  # 30 FPS
    monitor = NodeMonitor()
    
    # Create engine with our sinks
    engine = Engine(
        sinks=[console],        # Engine discovers full graph from sinks
        scheduler=scheduler,
        monitor=monitor
    )
    
    print("Starting manual RASL engine...")
    print("Press Ctrl+C to stop")
    
    try:
        # Run for 10 seconds, then stop
        await asyncio.wait_for(engine.start(), timeout=10.0)
    except asyncio.TimeoutError:
        print("\nStopping after 10 seconds...")
    except KeyboardInterrupt:
        print("\nStopping on user request...")
    finally:
        await engine.stop()
        
        # Print final statistics
        health = monitor.get_health_summary()
        perf = monitor.get_performance_summary()
        
        print(f"\nFinal Statistics:")
        print(f"  Total frames: {perf['total_frames']}")
        print(f"  Average FPS: {perf['current_fps']:.1f}")
        print(f"  Nodes: {health['total_nodes']} ({health['healthy']} healthy)")


if __name__ == "__main__":
    # This script can be run directly with Python
    asyncio.run(main())
    
    # Or with RASL (which will ignore the manual engine and create its own)
    # rasl run manual_engine.py
