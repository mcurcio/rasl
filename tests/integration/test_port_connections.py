"""
Integration tests for port-based connections.

Tests that the new explicit port connection syntax works correctly
and that node-level connections are properly removed.
"""

import pytest
import subprocess
import tempfile
from pathlib import Path


class TestPortConnections:
    """Test explicit port connection functionality."""
    
    def test_port_connection_syntax_works(self):
        """
        Test that explicit port connections work in scripts.
        
        Verifies that sine.ports.out >> console.ports["in"] syntax works.
        """
        # Create a test script with explicit port connections
        test_script_content = '''
from rasl import *

# Create nodes with matching channel counts
sine = SineSource(freq=1.0, channels=4)
console = ConsoleSink(format="table", update_interval=0.1)

# Connect using explicit port syntax
sine.ports.out >> console.ports["in"]
'''
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as temp_file:
            temp_file.write(test_script_content)
            temp_script = Path(temp_file.name)
        
        try:
            # Test that the script runs without syntax errors
            process = subprocess.Popen([
                "python", "-m", "rasl", "run", str(temp_script)
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            
            # Let it run briefly
            import time
            time.sleep(2)
            
            # Should be running successfully
            assert process.poll() is None, "Script with port connections should run successfully"
            
            # Terminate and check for errors
            process.terminate()
            stdout, stderr = process.communicate(timeout=5)
            
            # Should not have syntax errors or connection errors
            assert "SyntaxError" not in stderr, "Should not have syntax errors"
            assert "ConnectionError" not in stderr, "Should not have connection errors"
            
        finally:
            temp_script.unlink(missing_ok=True)
    
    def test_node_level_connections_removed(self):
        """
        Test that node-level connections (sine >> console) no longer work.
        
        This verifies that we successfully removed the node-level >> operator.
        """
        # Create a test script with old node-level connection syntax
        test_script_content = '''
from rasl import *

sine = SineSource(freq=1.0, channels=2)
console = ConsoleSink(format="table")

# This should fail - node-level connections removed
sine >> console
'''
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as temp_file:
            temp_file.write(test_script_content)
            temp_script = Path(temp_file.name)
        
        try:
            # This should fail during script loading
            process = subprocess.Popen([
                "python", "-m", "rasl", "run", str(temp_script)
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            
            # Wait for it to fail
            import time
            time.sleep(3)
            
            # Should have exited with error
            return_code = process.poll()
            if return_code is None:
                process.terminate()
                stdout, stderr = process.communicate(timeout=5)
            else:
                stdout, stderr = process.communicate()
            
            # Should have failed with TypeError about unsupported operand types
            assert "TypeError" in stderr or "unsupported operand type" in stderr, \
                "Should fail with TypeError for node-level connections"
            
        finally:
            temp_script.unlink(missing_ok=True)
    
    def test_chained_port_connections(self):
        """
        Test that chained port connections work correctly.
        
        Tests: sine.ports.out >> transform.ports["in"] >> sink.ports["in"]
        """
        test_script_content = '''
from rasl import *

# Create a 3-node chain with matching channels
sine = SineSource(freq=1.0, channels=4)
scaler = ScaleBias(scale=0.5, bias=0.2)
console = ConsoleSink(format="table", update_interval=0.1)

# Chain connections
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
            
            import time
            time.sleep(3)
            
            # Should be running successfully
            assert process.poll() is None, "Chained port connections should work"
            
            process.terminate()
            stdout, stderr = process.communicate(timeout=5)
            
            # Should see data flowing through the chain
            assert "in:" in stdout, "Should see data output from console sink"
            
            # Should not have connection errors
            assert "Failed to materialize" not in stderr, "Should not have materialization errors"
            
        finally:
            temp_script.unlink(missing_ok=True)
    
    def test_port_access_methods(self):
        """
        Test different ways of accessing ports.
        
        Tests both attribute access (ports.out) and bracket access (ports["in"]).
        """
        test_script_content = '''
from rasl import *

sine = SineSource(freq=1.0, channels=4)
console = ConsoleSink(format="raw")

# Test attribute access for 'out' (not a Python keyword)
out_port = sine.ports.out

# Test bracket access for 'in' (Python keyword)
in_port = console.ports["in"]

# Connect them
out_port >> in_port
'''
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as temp_file:
            temp_file.write(test_script_content)
            temp_script = Path(temp_file.name)
        
        try:
            process = subprocess.Popen([
                "python", "-m", "rasl", "run", str(temp_script)
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            
            import time
            time.sleep(2)
            
            assert process.poll() is None, "Different port access methods should work"
            
            process.terminate()
            process.wait(timeout=5)
            
        finally:
            temp_script.unlink(missing_ok=True)
    
    def test_invalid_port_names(self):
        """
        Test error handling for invalid port names.
        
        Should get clear error messages for non-existent ports.
        """
        test_script_content = '''
from rasl import *

sine = SineSource(freq=1.0, channels=4)
console = ConsoleSink()

# Try to access non-existent port
try:
    bad_port = sine.ports["nonexistent"]
except ValueError as e:
    print(f"Expected error: {e}")

# This should work
sine.ports.out >> console.ports["in"]
'''
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as temp_file:
            temp_file.write(test_script_content)
            temp_script = Path(temp_file.name)
        
        try:
            process = subprocess.Popen([
                "python", "-m", "rasl", "run", str(temp_script)
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            
            import time
            time.sleep(2)
            
            # Should handle the error gracefully and continue
            assert process.poll() is None, "Should handle port access errors gracefully"
            
            process.terminate()
            stdout, stderr = process.communicate(timeout=5)
            
            # Should see the expected error message
            assert "Expected error" in stdout or "Expected error" in stderr, \
                "Should show error message for invalid port access"
            
        finally:
            temp_script.unlink(missing_ok=True)
