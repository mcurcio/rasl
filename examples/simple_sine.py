"""
Simple sine wave example - RASL's "Hello World"

Demonstrates basic node creation, connection, and console output.
Perfect starting point for learning RASL.

When you run this with `rasl run simple_sine.py`, the RASL application:
1. Loads this script and discovers all nodes
2. Finds sinks (console) and traces backwards to find the full graph
3. Creates an engine with the discovered sinks
4. Starts the execution loop at 30 Hz by default
"""

from rasl import SineSource, ScaleBias, ConsoleSink

# Create a sine wave source
sine = SineSource(
    freq=1.0,           # 1 Hz frequency
    amplitude=0.8,      # 80% amplitude
    channels=4          # 4 output channels
)

# Scale and offset the values
scaler = ScaleBias(
    scale=0.5,          # Reduce amplitude by half
    bias=0.2            # Add 20% offset
)

# Output to console for debugging
console = ConsoleSink(
    format="table",     # Nice table format
    update_interval=0.1 # Update every 500ms
)

# Connect the nodes - this registers connections globally
sine.ports.out >> scaler.ports["in"]
scaler.ports.out >> console.ports["in"]

# The RASL application will:
# 1. Find 'console' (a Sink) in the script globals
# 2. Trace back through connections to find 'scaler' and 'sine'
# 3. Create an Engine with sinks=[console]
# 4. The engine discovers the full graph: sine -> scaler -> console
# 5. Start executing at the configured frame rate

# Parameters are automatically discovered from node specifications
# No need for manual expose_parameter() calls!
