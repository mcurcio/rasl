"""
Integration tests for complete script execution pipeline.

Tests the full workflow: script loading → engine creation → execution.
"""

import pytest
import asyncio
from pathlib import Path

from rasl.script.loader import ScriptLoader
from rasl.core.engine import Engine
from rasl.core.executor import Executor
from rasl.core.scheduler import FixedRateScheduler, MonotonicClock
from rasl.core.ports import reset_connections


class TestScriptExecution:
    """Test complete script-to-execution pipeline."""
    
    def setup_method(self):
        """Reset connections before each test."""
        reset_connections()
    
    @pytest.mark.asyncio
    async def test_simple_sine_script_execution(self):
        """
        Test that examples/simple_sine.py can be loaded and executed end-to-end.
        
        This is the ultimate integration test - if this passes, the entire
        script loading → engine → execution pipeline is working.
        """
        # Load the script
        loader = ScriptLoader()
        script_path = Path("examples/simple_sine.py")
        spec = await loader.load_script(script_path)
        
        # Verify script was loaded correctly
        assert len(spec.nodes) > 0, "Script should contain nodes"
        assert len(spec.sinks) > 0, "Script should contain sinks"
        assert len(spec.exposed_parameters) > 10, "Script should auto-discover many parameters"
        
        # Create executor and register all discovered nodes
        executor = Executor()
        for node in spec.nodes:
            executor.register_node(node)
        
        # Create engine with discovered sinks
        scheduler = FixedRateScheduler(MonotonicClock(), target_hz=30.0)
        engine = Engine(sinks=spec.sinks, scheduler=scheduler, executor=executor)
        
        # Test single frame execution
        await engine.tick_once()
        
        # Verify that the engine executed without errors
        # If we get here without exceptions, the pipeline is working
        assert True, "Engine executed successfully"
    
    @pytest.mark.asyncio
    async def test_automatic_parameter_discovery(self):
        """Test that parameters are automatically discovered from node specs."""
        loader = ScriptLoader()
        script_path = Path("examples/simple_sine.py")
        spec = await loader.load_script(script_path)
        
        # Check that parameters were auto-discovered
        param_names = [p['param_name'] for p in spec.exposed_parameters]
        
        # Should include key parameters from each node type
        expected_params = ["freq", "amplitude", "scale", "bias", "format", "update_interval"]
        for expected in expected_params:
            assert expected in param_names, f"Expected parameter {expected} not auto-discovered"
        
        # Verify parameters have proper metadata
        freq_params = [p for p in spec.exposed_parameters if p['param_name'] == 'freq']
        assert len(freq_params) > 0, "Should find frequency parameter"
        freq_param = freq_params[0]
        assert freq_param['min'] is not None, "Frequency should have min value"
        assert freq_param['max'] is not None, "Frequency should have max value"
        assert freq_param['description'] is not None, "Frequency should have description"
    
    @pytest.mark.asyncio 
    async def test_script_hot_reload_detection(self):
        """Test that script change detection works."""
        loader = ScriptLoader()
        script_path = Path("examples/simple_sine.py")
        
        # Load script first time
        spec1 = await loader.load_script(script_path)
        
        # Check if script has changed (should be False immediately)
        has_changed = loader.has_script_changed(script_path)
        assert not has_changed, "Script should not appear changed immediately after loading"
        
        # Load again (should work without issues)
        spec2 = await loader.load_script(script_path)
        assert len(spec2.nodes) == len(spec1.nodes), "Reloaded script should have same structure"
