"""
Integration tests for error-free execution of simple cases.

Tests that basic RASL scripts run without throwing errors or warnings.
"""

import pytest
import subprocess
import time
import os
import tempfile
from pathlib import Path


class TestErrorFreeExecution:
    """Test that simple cases execute without errors."""
    
    def test_simple_sine_runs_without_errors(self):
        """
        Test that examples/simple_sine.py runs for a few seconds without any errors.
        
        This test should FAIL initially, demonstrating that the current
        implementation has execution errors that need to be fixed.
        """
        script_path = Path("examples/simple_sine.py")
        
        # Create temporary files to capture output
        with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.out') as stdout_file, \
             tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.err') as stderr_file:
            
            stdout_path = stdout_file.name
            stderr_path = stderr_file.name
        
        pid_file = f"/tmp/rasl_test_error_free_{os.getpid()}.pid"
        
        try:
            # Start the process and capture all output
            cmd = f"cd {os.getcwd()} && source .venv/bin/activate && python -m rasl run {script_path} > {stdout_path} 2> {stderr_path} & echo $! > {pid_file}"
            
            exit_code = os.system(cmd)
            if exit_code != 0:
                pytest.fail(f"Failed to start process: exit code {exit_code}")
            
            # Wait for PID file
            time.sleep(0.5)
            if not os.path.exists(pid_file):
                pytest.fail("PID file not created")
            
            with open(pid_file, 'r') as f:
                pid = int(f.read().strip())
            
            # Let it run for 3 seconds to capture any errors
            print(f"Letting process {pid} run for 3 seconds to capture errors...")
            time.sleep(3.0)
            
            # Check if process is still running
            try:
                os.kill(pid, 0)
                print("✅ Process is still running")
            except ProcessLookupError:
                pytest.fail("Process died unexpectedly during execution")
            
            # Kill the process
            try:
                os.kill(pid, 15)  # SIGTERM
                time.sleep(1.0)
            except ProcessLookupError:
                pass
            
            # Read captured output
            with open(stdout_path, 'r') as f:
                stdout_content = f.read()
            
            with open(stderr_path, 'r') as f:
                stderr_content = f.read()
            
            print(f"STDOUT length: {len(stdout_content)} chars")
            print(f"STDERR length: {len(stderr_content)} chars")
            
            # Check for errors in the output
            error_indicators = [
                "ERROR",
                "CRITICAL", 
                "Exception",
                "Traceback",
                "failed on frame",
                "property object",
                "did not produce output"
            ]
            
            found_errors = []
            all_output = stdout_content + stderr_content
            
            for indicator in error_indicators:
                if indicator in all_output:
                    # Count occurrences
                    count = all_output.count(indicator)
                    found_errors.append(f"{indicator} ({count} times)")
            
            # Print some sample output for debugging
            if stderr_content:
                print("\n--- STDERR SAMPLE (first 1000 chars) ---")
                print(stderr_content[:1000])
                if len(stderr_content) > 1000:
                    print("... (truncated)")
            
            if found_errors:
                error_summary = ", ".join(found_errors)
                pytest.fail(f"❌ EXPECTED FAILURE: Found errors in execution: {error_summary}")
            
            print("🎉 SUCCESS: No errors found in execution!")
            
        finally:
            # Cleanup
            try:
                os.unlink(pid_file)
            except FileNotFoundError:
                pass
            
            try:
                os.unlink(stdout_path)
                os.unlink(stderr_path)
            except FileNotFoundError:
                pass
            
            # Kill any remaining processes
            os.system("pkill -f 'python -m rasl' 2>/dev/null")
    
    def test_simple_sine_produces_expected_output(self):
        """
        Test that examples/simple_sine.py produces the expected console output.
        
        This validates that the ConsoleSink is working correctly and producing
        the expected sine wave data.
        """
        script_path = Path("examples/simple_sine.py")
        
        with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.out') as stdout_file:
            stdout_path = stdout_file.name
        
        pid_file = f"/tmp/rasl_test_output_{os.getpid()}.pid"
        
        try:
            # Start the process and capture stdout only
            cmd = f"cd {os.getcwd()} && source .venv/bin/activate && python -m rasl run {script_path} > {stdout_path} 2>/dev/null & echo $! > {pid_file}"
            
            exit_code = os.system(cmd)
            if exit_code != 0:
                pytest.fail(f"Failed to start process: exit code {exit_code}")
            
            # Wait for PID file
            time.sleep(0.5)
            if not os.path.exists(pid_file):
                pytest.fail("PID file not created")
            
            with open(pid_file, 'r') as f:
                pid = int(f.read().strip())
            
            # Let it run for 2 seconds to generate some output
            time.sleep(2.0)
            
            # Kill the process
            try:
                os.kill(pid, 15)  # SIGTERM
                time.sleep(0.5)
            except ProcessLookupError:
                pass
            
            # Read captured output
            with open(stdout_path, 'r') as f:
                output_content = f.read()
            
            print(f"Output content length: {len(output_content)} chars")
            print("--- OUTPUT SAMPLE ---")
            print(output_content[:500] if output_content else "(no output)")
            
            # Check that we got some meaningful output
            if not output_content.strip():
                pytest.fail("No output produced - ConsoleSink may not be working")
            
            # Look for expected patterns (sine wave data)
            expected_patterns = [
                "Frame",  # Frame info
                "in:",    # Input port data
                "0.",     # Decimal numbers (sine values)
            ]
            
            missing_patterns = []
            for pattern in expected_patterns:
                if pattern not in output_content:
                    missing_patterns.append(pattern)
            
            if missing_patterns:
                pytest.fail(f"Missing expected output patterns: {missing_patterns}")
            
            print("🎉 SUCCESS: Found expected output patterns!")
            
        finally:
            # Cleanup
            try:
                os.unlink(pid_file)
                os.unlink(stdout_path)
            except FileNotFoundError:
                pass
            
            # Kill any remaining processes
            os.system("pkill -f 'python -m rasl' 2>/dev/null")
