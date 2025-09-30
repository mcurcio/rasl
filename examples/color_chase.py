"""
Color chase effect example

Creates a traveling wave of color across multiple channels,
perfect for LED strips and lighting arrays.

This demonstrates:
- Multi-channel sources with phase relationships
- Color processing pipeline  
- Multiple sinks (console + sACN output)
- Parameter exposure for real-time control

When run with `rasl run color_chase.py`, RASL will:
1. Discover two sinks: console and sacn
2. Trace back to find: chase -> color_temp -> rgb -> [console, sacn]
3. Create engine with both sinks
4. Start execution loop outputting to both console and sACN network
"""

from rasl import SineSource, ScaleBias, ConsoleSink

# Create multiple sine waves with phase shifts for chase effect
chase = SineSource(
    freq=0.5,           # Slow chase speed
    amplitude=1.0,
    channels=20,        # 20 LED channels
    phase_shift=0.314   # π/10 radians between channels (36 degrees)
)

# Convert to color temperature (warm to cool)
color_temp = ColorTemperature(
    min_temp=2000,      # Warm orange
    max_temp=6500       # Cool blue
)

# Convert to RGB values
rgb = ToRGB()

# Output to console for monitoring
console = ConsoleSink(
    format="summary",
    update_interval=0.2
)

# Output to sACN lighting network
sacn = SACNSink(
    universe=1,
    start_channel=1,
    target_hz=30
)

# Connect the pipeline - fan out to multiple sinks
chase >> color_temp >> rgb >> [console, sacn]

# RASL will find both 'console' and 'sacn' sinks in globals
# and trace back through the connections to discover the full graph

# Expose key parameters for real-time control via web UI
expose_parameter("chase.freq", min=0.1, max=5.0, step=0.1)
expose_parameter("color_temp.min_temp", min=1000, max=4000, step=100)
expose_parameter("color_temp.max_temp", min=4000, max=8000, step=100)
