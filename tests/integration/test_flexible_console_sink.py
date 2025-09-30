"""
Integration tests for flexible ConsoleSink functionality.

Tests that ConsoleSink works with various channel configurations
in real execution scenarios.
"""

import pytest
import subprocess
import tempfile
import time
from pathlib import Path


class TestFlexibleConsoleSinkIntegration:
    """Integration tests for flexible ConsoleSink."""
    
    def test_console_sink_with_various_channel_counts(self):
        """
        Test ConsoleSink with different channel counts in real execution.
        
        Verifies that scripts with various channel configurations run successfully.
        """
        channel_configs = [1, 2, 3, 5, 8, 16]
        
        for channels in channel_configs:
            # Create test script with specific channel count
            test_script_content = f'''
from rasl import *

# Create source with {channels} channels
sine = SineSource(freq=1.0, channels={channels})
console = ConsoleSink(format="table", update_interval=0.1)

# Connect using flexible port connections
sine.ports.out >> console.ports["in"]
'''
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as temp_file:
                temp_file.write(test_script_content)
                temp_script = Path(temp_file.name)
            
            try:
                # Test that the script runs successfully
                process = subprocess.Popen([
                    "python", "-m", "rasl", "run", str(temp_script)
                ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                
                # Let it run briefly
                time.sleep(2)
                
                # Should be running successfully
                assert process.poll() is None, f"Script with {channels} channels should run successfully"
                
                # Terminate and check for errors
                process.terminate()
                stdout, stderr = process.communicate(timeout=5)
                
                # Should not have connection errors
                assert "ConnectionError" not in stderr, f"Should not have connection errors with {channels} channels"
                assert "Schema mismatch" not in stderr, f"Should not have schema mismatch with {channels} channels"
                
            finally:
                temp_script.unlink(missing_ok=True)
    
    def test_console_sink_with_transform_chain(self):
        """
        Test ConsoleSink at the end of a transform chain with flexible channels.
        
        Tests: Source -> Transform -> ConsoleSink with various channel counts.
        """
        test_script_content = '''
from rasl import *

# Create a chain with flexible channel handling
sine = SineSource(freq=2.0, channels=6)
scaler = ScaleBias(scale=0.8, bias=0.1)
console = ConsoleSink(format="raw", update_interval=0.1)

# Chain connections - all should be flexible
sine.ports.out >> scaler.ports["in"]
scaler.ports.out >> console.ports["in"]
'''
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as temp_file:
            temp_file.write(test_script_content)
            temp_script = Path(temp_file.name)
        
        try:
            process = subprocess.Popen([
                "python", "-m", "rasl", "run", str(temp_script)
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            
            time.sleep(2)
            
            # Should be running successfully
            assert process.poll() is None, "Transform chain should run successfully"
            
            process.terminate()
            stdout, stderr = process.communicate(timeout=5)
            
            # Should see data flowing through
            assert "in:" in stdout, "Should see console output"
            
            # Should not have errors
            assert "ERROR" not in stderr, "Should not have execution errors"
            
        finally:
            temp_script.unlink(missing_ok=True)
    
    def test_console_sink_backwards_compatibility(self):
        """
        Test that existing scripts still work with the flexible ConsoleSink.
        
        Ensures we didn't break existing functionality.
        """
        # Test the original simple_sine.py example
        process = subprocess.Popen([
            "python", "-m", "rasl", "run", "examples/simple_sine.py"
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        
        try:
            time.sleep(2)
            
            # Should still work
            assert process.poll() is None, "Original simple_sine.py should still work"
            
            process.terminate()
            stdout, stderr = process.communicate(timeout=5)
            
            # Should see expected output
            assert "in:" in stdout, "Should see console output from simple_sine.py"
            
        except subprocess.TimeoutExpired:
            process.kill()
            pytest.fail("simple_sine.py did not terminate gracefully")
    
    def test_multiple_console_sinks_different_channels(self):
        """
        Test multiple ConsoleSinks with different channel requirements.
        
        Verifies that different sinks can coexist with different schemas.
        """
        test_script_content = '''
from rasl import *

# Create sources with different channel counts
sine1 = SineSource(freq=1.0, channels=2)
sine2 = SineSource(freq=2.0, channels=8)

# Create console sinks with different formats
console1 = ConsoleSink(format="raw", update_interval=0.2)
console2 = ConsoleSink(format="table", update_interval=0.3)

# Connect different sources to different sinks
sine1.ports.out >> console1.ports["in"]
sine2.ports.out >> console2.ports["in"]
'''
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as temp_file:
            temp_file.write(test_script_content)
            temp_script = Path(temp_file.name)
        
        try:
            process = subprocess.Popen([
                "python", "-m", "rasl", "run", str(temp_script)
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            
            time.sleep(3)  # Let both sinks output
            
            assert process.poll() is None, "Multiple console sinks should work"
            
            process.terminate()
            stdout, stderr = process.communicate(timeout=5)
            
            # Should see output from both sinks
            assert "in:" in stdout, "Should see console output"
            
            # Should not have connection errors
            assert "ConnectionError" not in stderr, "Should not have connection errors"
            
        finally:
            temp_script.unlink(missing_ok=True)
    
    def test_console_sink_performance_with_many_channels(self):
        """
        Test ConsoleSink performance with large channel counts.
        
        Ensures the flexible schema doesn't cause performance issues.
        """
        test_script_content = '''
from rasl import *

# Create source with many channels
sine = SineSource(freq=0.5, channels=64)
console = ConsoleSink(format="summary", update_interval=0.2, max_channels=10)

# Should handle large channel counts gracefully
sine.ports.out >> console.ports["in"]
'''
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as temp_file:
            temp_file.write(test_script_content)
            temp_script = Path(temp_file.name)
        
        try:
            start_time = time.time()
            
            process = subprocess.Popen([
                "python", "-m", "rasl", "run", str(temp_script)
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            
            time.sleep(3)
            
            # Should still be running (not crashed from large data)
            assert process.poll() is None, "Should handle large channel counts"
            
            process.terminate()
            stdout, stderr = process.communicate(timeout=5)
            
            # Should not have performance-related errors
            assert "timeout" not in stderr.lower(), "Should not have timeout errors"
            assert "memory" not in stderr.lower(), "Should not have memory errors"
            
        finally:
            temp_script.unlink(missing_ok=True)
