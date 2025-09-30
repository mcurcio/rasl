"""
Script execution environment for RASL.

Handles safe execution of user scripts in a controlled environment
with proper namespace setup.
"""

import logging
from pathlib import Path
from typing import Any, Dict

import rasl
from .syntax_validator import ScriptLoadError

logger = logging.getLogger(__name__)


class ScriptExecutor:
    """
    Executes RASL scripts in a controlled environment.
    
    Provides safe execution with proper namespace setup and error handling.
    """
    
    def __init__(self):
        pass
    
    def create_script_environment(self) -> Dict[str, Any]:
        """
        Create a controlled execution environment for scripts.
        
        Returns:
            Dictionary containing the script execution namespace
            
        Raises:
            ScriptLoadError: If RASL components cannot be imported
        """
        # Import RASL components into script namespace
        script_globals = {
            '__builtins__': __builtins__,
            '__name__': '__rasl_script__',
        }
        
        # Import all RASL components
        try:
            # Add all public RASL exports to script globals
            for name in rasl.__all__:
                script_globals[name] = getattr(rasl, name)
            
            # Add convenience imports
            script_globals['rasl'] = rasl
            
        except ImportError as e:
            raise ScriptLoadError(f"Failed to import RASL components: {e}")
        
        return script_globals
    
    def execute_script(self, content: str, script_path: Path, script_globals: Dict[str, Any]) -> None:
        """
        Execute script in the prepared environment.
        
        Args:
            content: Script content to execute
            script_path: Path to script file (for error reporting)
            script_globals: Execution environment namespace
            
        Raises:
            ScriptLoadError: If script execution fails
        """
        try:
            # Compile and execute
            code = compile(content, str(script_path), 'exec')
            exec(code, script_globals)
            
        except Exception as e:
            raise ScriptLoadError(f"Script execution failed: {e}")
