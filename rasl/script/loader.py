"""
Script loading and graph extraction for RASL.

Safely loads user Python scripts and extracts the graph definition
for execution by the RASL engine.
"""

import ast
import sys
import importlib.util
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

from rasl.core.nodes import Node, Sink
from rasl.core.ports import get_connection_registry, reset_connections
from .api import get_exposed_parameters, clear_exposed_parameters, _set_engine

logger = logging.getLogger(__name__)


@dataclass
class GraphSpec:
    """Specification of a loaded graph."""
    nodes: List[Node]
    sinks: List[Sink]
    exposed_parameters: List[Dict[str, Any]]
    script_path: Path
    script_hash: str


class ScriptLoadError(Exception):
    """Raised when script loading fails."""
    pass


class ScriptLoader:
    """
    Loads and validates user RASL scripts.
    
    Provides safe execution environment and extracts graph definitions
    for use by the RASL engine.
    """
    
    def __init__(self):
        self._loaded_modules: Dict[str, Any] = {}
        self._last_hash: Optional[str] = None
    
    async def load_script(self, script_path: Path) -> GraphSpec:
        """
        Load a RASL script and extract the graph definition.
        
        Args:
            script_path: Path to the Python script file
            
        Returns:
            GraphSpec containing nodes, sinks, and metadata
            
        Raises:
            ScriptLoadError: If script loading or validation fails
        """
        if not script_path.exists():
            raise ScriptLoadError(f"Script file not found: {script_path}")
        
        if not script_path.suffix == ".py":
            raise ScriptLoadError(f"Script must be a Python file: {script_path}")
        
        logger.info(f"Loading script: {script_path}")
        
        try:
            # Calculate script hash for change detection
            script_content = script_path.read_text()
            script_hash = str(hash(script_content))
            
            # Reset global state
            reset_connections()
            clear_exposed_parameters()
            
            # Validate script syntax
            self._validate_script_syntax(script_content, script_path)
            
            # Execute script in controlled environment
            script_globals = self._create_script_environment()
            self._execute_script(script_content, script_path, script_globals)
            
            # Extract graph from execution results
            nodes, sinks = self._extract_graph_from_globals(script_globals)
            
            # Auto-discover parameters from all nodes instead of requiring expose_parameter calls
            exposed_params = self._auto_discover_parameters(nodes)
            
            # Validate the extracted graph
            self._validate_graph(nodes, sinks)
            
            self._last_hash = script_hash
            
            return GraphSpec(
                nodes=nodes,
                sinks=sinks,
                exposed_parameters=exposed_params,
                script_path=script_path,
                script_hash=script_hash
            )
            
        except Exception as e:
            logger.error(f"Failed to load script {script_path}: {e}")
            raise ScriptLoadError(f"Script loading failed: {e}") from e
    
    def has_script_changed(self, script_path: Path) -> bool:
        """Check if script has changed since last load."""
        if not script_path.exists():
            return True
        
        try:
            current_content = script_path.read_text()
            current_hash = str(hash(current_content))
            return current_hash != self._last_hash
        except Exception:
            return True
    
    def _validate_script_syntax(self, content: str, script_path: Path) -> None:
        """Validate Python syntax without executing."""
        try:
            ast.parse(content, filename=str(script_path))
        except SyntaxError as e:
            raise ScriptLoadError(f"Syntax error in {script_path}:{e.lineno}: {e.msg}")
    
    def _create_script_environment(self) -> Dict[str, Any]:
        """Create a controlled execution environment for scripts."""
        # Import RASL components into script namespace
        script_globals = {
            '__builtins__': __builtins__,
            '__name__': '__rasl_script__',
        }
        
        # Import all RASL components
        try:
            import rasl
            
            # Add all public RASL exports to script globals
            for name in rasl.__all__:
                script_globals[name] = getattr(rasl, name)
            
            # Add convenience imports
            script_globals['rasl'] = rasl
            
        except ImportError as e:
            raise ScriptLoadError(f"Failed to import RASL components: {e}")
        
        return script_globals
    
    def _execute_script(self, content: str, script_path: Path, script_globals: Dict[str, Any]) -> None:
        """Execute script in the prepared environment."""
        try:
            # Compile and execute
            code = compile(content, str(script_path), 'exec')
            exec(code, script_globals)
            
        except Exception as e:
            raise ScriptLoadError(f"Script execution failed: {e}")
    
    def _extract_graph_from_globals(self, script_globals: Dict[str, Any]) -> tuple[List[Node], List[Sink]]:
        """Extract nodes and sinks from script execution globals."""
        # Find all Node instances in the script globals
        all_nodes = {}  # id -> node mapping
        sinks = []
        
        for name, obj in script_globals.items():
            # Only consider actual instances, not classes
            if isinstance(obj, Node) and not isinstance(obj, type):
                all_nodes[obj.id] = obj
                if isinstance(obj, Sink):
                    sinks.append(obj)
        
        if not sinks:
            raise ScriptLoadError("No sinks found in script - at least one sink is required")
        
        # Now discover the full graph by tracing backwards from sinks
        registry = get_connection_registry()
        discovered_nodes = set()
        
        def discover_upstream(node_id: str):
            """Recursively discover nodes upstream from the given node."""
            if node_id in discovered_nodes:
                return
            
            discovered_nodes.add(node_id)
            
            # Find all edges that feed into this node
            for edge in registry.get_edges():
                if edge.dst_id == node_id:
                    # This edge feeds into our node, discover its source
                    discover_upstream(edge.src_id)
        
        # Start discovery from all sinks
        for sink in sinks:
            discover_upstream(sink.id)
        
        # Collect all discovered nodes
        nodes = []
        for node_id in discovered_nodes:
            if node_id in all_nodes:
                nodes.append(all_nodes[node_id])
            else:
                logger.warning(f"Node {node_id} referenced in connections but not found in script globals")
        
        # Also register nodes with the executor for later use
        # (This is a bit of a hack - we should have a proper node registry)
        self._discovered_nodes = all_nodes
        
        logger.info(f"Discovered graph: {len(nodes)} nodes, {len(sinks)} sinks, {len(registry.get_edges())} connections")
        return nodes, sinks
    
    def _validate_graph(self, nodes: List[Node], sinks: List[Sink]) -> None:
        """Validate the extracted graph structure."""
        # Basic validation
        if not nodes:
            raise ScriptLoadError("Graph contains no nodes")
        
        if not sinks:
            raise ScriptLoadError("Graph contains no sinks")
        
        # Check for duplicate node IDs
        node_ids = [node.id for node in nodes]
        if len(node_ids) != len(set(node_ids)):
            duplicates = [id for id in set(node_ids) if node_ids.count(id) > 1]
            raise ScriptLoadError(f"Duplicate node IDs found: {duplicates}")
        
        # Validate connections exist
        registry = get_connection_registry()
        edges = registry.get_edges()
        
        if not edges:
            logger.warning("No connections found in graph - nodes may be isolated")
        
        logger.info(f"Graph validation passed: {len(nodes)} nodes, {len(edges)} connections")
    
    def _auto_discover_parameters(self, nodes: List[Node]) -> List[Dict[str, Any]]:
        """
        Automatically discover parameters from all nodes in the graph.
        
        This replaces the need for manual expose_parameter() calls by introspecting
        each node's param_spec() to find all available parameters.
        """
        exposed_params = []
        
        for node in nodes:
            try:
                # Debug: check if this is actually a node instance
                if not hasattr(node, 'id'):
                    logger.warning(f"Skipping non-node object in parameter discovery: {node} (type: {type(node)})")
                    continue
                
                # Get parameter specification from the node
                param_spec = node.param_spec()
                
                # Convert each parameter to the exposed parameter format
                for param_name, spec in param_spec.items():
                    exposed_param = {
                        "node_path": node.id,  # Use node ID as path
                        "param_name": param_name,
                        "min": spec.get("min"),
                        "max": spec.get("max"),
                        "step": spec.get("step", 0.01),  # Default step
                        "enum": spec.get("enum"),
                        "description": spec.get("description", f"{node.TYPE}.{param_name}")
                    }
                    exposed_params.append(exposed_param)
                    
            except Exception as e:
                # Skip nodes that don't have proper param_spec
                logger.warning(f"Could not discover parameters for node {node.id}: {e}")
                continue
        
        logger.info(f"Auto-discovered {len(exposed_params)} parameters from {len(nodes)} nodes")
        return exposed_params


class ScriptValidator:
    """
    Static analysis and validation of RASL scripts.
    
    Provides additional safety checks and analysis without execution.
    """
    
    def __init__(self):
        pass
    
    def validate_script_safety(self, script_path: Path) -> List[str]:
        """
        Perform static safety analysis of a script.
        
        Returns list of warnings/issues found.
        """
        warnings = []
        
        try:
            content = script_path.read_text()
            tree = ast.parse(content)
            
            # Check for potentially dangerous operations
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name in ('os', 'subprocess', 'sys'):
                            warnings.append(f"Potentially unsafe import: {alias.name}")
                
                elif isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name):
                        if node.func.id in ('exec', 'eval', 'open'):
                            warnings.append(f"Potentially unsafe function call: {node.func.id}")
        
        except Exception as e:
            warnings.append(f"Failed to analyze script: {e}")
        
        return warnings
    
    def extract_script_metadata(self, script_path: Path) -> Dict[str, Any]:
        """Extract metadata from script without execution."""
        metadata = {
            "path": str(script_path),
            "size_bytes": script_path.stat().st_size,
            "modified_time": script_path.stat().st_mtime,
            "imports": [],
            "node_types": [],
            "estimated_complexity": "unknown"
        }
        
        try:
            content = script_path.read_text()
            tree = ast.parse(content)
            
            # Extract imports
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        metadata["imports"].append(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        metadata["imports"].append(node.module)
            
            # Estimate complexity based on AST size
            node_count = len(list(ast.walk(tree)))
            if node_count < 50:
                metadata["estimated_complexity"] = "simple"
            elif node_count < 200:
                metadata["estimated_complexity"] = "moderate"
            else:
                metadata["estimated_complexity"] = "complex"
        
        except Exception as e:
            metadata["parse_error"] = str(e)
        
        return metadata
