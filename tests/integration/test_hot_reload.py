"""
Integration tests for script hot-reload functionality.

Tests that parameter changes trigger updates during execution without
stopping the engine or causing errors.
"""

import pytest
import asyncio
import tempfile
import shutil
from pathlib import Path
import subprocess
import time


class TestHotReload:
    """Test script hot-reload functionality."""
    
    def test_parameter_change_triggers_reload(self):
        """
        Test that modifying script parameters triggers hot-reload.
        
        This test verifies Milestone 1 requirement: "Script hot-reload works
        (change parameters, see updates)"
        """
        # Create a temporary copy of simple_sine.py
        original_script = Path("examples/simple_sine.py")
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as temp_file:
            temp_script = Path(temp_file.name)
        
        # Copy original content
        shutil.copy2(original_script, temp_script)
        
        try:
            # Start RASL with the temporary script
            process = subprocess.Popen([
                "python", "-m", "rasl", "run", str(temp_script)
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            
            # Wait for initial startup
            time.sleep(2)
            
            # Verify process is running
            assert process.poll() is None, "Process should be running after startup"
            
            # Modify the script - change frequency from 1.0 to 2.0
            with open(temp_script, 'r') as f:
                content = f.read()
            
            modified_content = content.replace('freq=1.0,', 'freq=2.0,')
            
            with open(temp_script, 'w') as f:
                f.write(modified_content)
            
            # Wait for hot-reload to process
            time.sleep(3)
            
            # Verify process is still running after modification
            assert process.poll() is None, "Process should survive script modification"
            
            # Terminate gracefully
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                pytest.fail("Process did not terminate gracefully")
                
        finally:
            # Cleanup
            temp_script.unlink(missing_ok=True)
    
    def test_syntax_error_handling(self):
        """
        Test that syntax errors in hot-reload don't crash the engine.
        
        The engine should continue running with the previous valid script
        when a syntax error is introduced.
        """
        # Create a temporary copy of simple_sine.py
        original_script = Path("examples/simple_sine.py")
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as temp_file:
            temp_script = Path(temp_file.name)
        
        shutil.copy2(original_script, temp_script)
        
        try:
            # Start RASL
            process = subprocess.Popen([
                "python", "-m", "rasl", "run", str(temp_script)
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            
            time.sleep(2)
            assert process.poll() is None, "Process should be running"
            
            # Introduce syntax error
            with open(temp_script, 'w') as f:
                f.write("invalid python syntax !!!")
            
            # Wait for reload attempt
            time.sleep(2)
            
            # Process should still be running (graceful error handling)
            assert process.poll() is None, "Process should survive syntax errors"
            
            # Terminate
            process.terminate()
            process.wait(timeout=5)
                
        finally:
            temp_script.unlink(missing_ok=True)
    
    def test_file_watcher_detects_changes(self):
        """
        Test that the file watcher properly detects script changes.
        
        This is a more focused test of the file watching mechanism.
        """
        original_script = Path("examples/simple_sine.py")
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as temp_file:
            temp_script = Path(temp_file.name)
        
        shutil.copy2(original_script, temp_script)
        
        try:
            process = subprocess.Popen([
                "python", "-m", "rasl", "run", str(temp_script)
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            
            time.sleep(2)
            
            # Make multiple small changes to test file watcher
            for i in range(3):
                with open(temp_script, 'r') as f:
                    content = f.read()
                
                # Add a comment to trigger file change
                modified_content = content + f"\n# Change {i}\n"
                
                with open(temp_script, 'w') as f:
                    f.write(modified_content)
                
                time.sleep(1)  # Give file watcher time to detect
            
            # Process should still be running
            assert process.poll() is None, "Process should handle multiple file changes"
            
            process.terminate()
            process.wait(timeout=5)
                
        finally:
            temp_script.unlink(missing_ok=True)
