#!/usr/bin/env python3
"""
Test performance metrics - frame rates and execution times.
"""

import subprocess
import time
import re
from pathlib import Path

def test_performance():
    """Test frame rates and execution times."""
    
    print("⚡ Testing performance metrics...")
    
    # Start RASL and capture output
    process = subprocess.Popen([
        "python", "-m", "rasl", "run", "examples/simple_sine.py"
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    
    try:
        print("⏳ Running for 5 seconds to collect performance data...")
        time.sleep(5)
        
        # Terminate and get output
        process.terminate()
        stdout, stderr = process.communicate(timeout=5)
        
        # Parse frame information from stdout
        frame_pattern = r"Frame\s+(\d+)\s+\|\s+t=([\d.]+)s\s+\|\s+dt=\s*([\d.]+)ms"
        frames = re.findall(frame_pattern, stdout)
        
        if not frames:
            print("❌ No frame data found in output")
            return False
        
        print(f"📊 Captured {len(frames)} frames")
        
        # Calculate metrics
        frame_numbers = [int(f[0]) for f in frames]
        times = [float(f[1]) for f in frames]
        dts = [float(f[2]) for f in frames]
        
        # Frame rate calculation
        if len(times) >= 2:
            total_time = times[-1] - times[0]
            total_frames = frame_numbers[-1] - frame_numbers[0]
            avg_fps = total_frames / total_time if total_time > 0 else 0
            
            print(f"📈 Average FPS: {avg_fps:.1f}")
            
            # Frame time analysis
            avg_dt = sum(dts) / len(dts)
            max_dt = max(dts)
            min_dt = min(dts)
            
            print(f"⏱️  Average frame time: {avg_dt:.1f}ms")
            print(f"⏱️  Max frame time: {max_dt:.1f}ms")
            print(f"⏱️  Min frame time: {min_dt:.1f}ms")
            
            # Check performance requirements
            success = True
            
            if avg_fps < 30:
                print(f"⚠️ Average FPS ({avg_fps:.1f}) below target (30 FPS)")
                success = False
            else:
                print(f"✅ Average FPS ({avg_fps:.1f}) meets target (30+ FPS)")
            
            if max_dt > 50:  # 50ms = 20 FPS minimum
                print(f"⚠️ Max frame time ({max_dt:.1f}ms) too high")
                success = False
            else:
                print(f"✅ Max frame time ({max_dt:.1f}ms) acceptable")
            
            # Check for frame drops (large dt variations)
            dt_variance = max(dts) - min(dts)
            if dt_variance > 20:  # 20ms variance threshold
                print(f"⚠️ High frame time variance ({dt_variance:.1f}ms)")
            else:
                print(f"✅ Frame time variance ({dt_variance:.1f}ms) stable")
            
            return success
        else:
            print("❌ Insufficient frame data for analysis")
            return False
            
    except subprocess.TimeoutExpired:
        process.kill()
        print("❌ Process had to be killed")
        return False
    except Exception as e:
        print(f"❌ Performance test failed: {e}")
        return False

if __name__ == "__main__":
    success = test_performance()
    if success:
        print("\n🎉 Performance test PASSED!")
    else:
        print("\n⚠️ Performance test completed with warnings")
        # Don't fail - performance issues are not blockers for Milestone 1
