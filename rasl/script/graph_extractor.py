"""
Graph extraction from executed RASL scripts.

Handles discovery of nodes, sinks, and connections from script execution
results.
"""

import logging
from typing import Any, Dict, List, Set

from rasl.core.nodes import Node, Sink
from rasl.core.ports import get_connection_registry
from .syntax_validator import ScriptLoadError

logger = logging.getLogger(__name__)


class GraphExtractor:
    """
    Extracts graph structure from executed RASL scripts.
    
    Discovers nodes, sinks, and connections by analyzing script execution
    results and connection registry.
    """
    
    def __init__(self):
        self._discovered_nodes: Dict[str, Node] = {}
    
    def extract_graph(self, script_globals: Dict[str, Any]) -> tuple[List[Node], List[Sink]]:
        """
        Extract nodes and sinks from script execution globals.
        
        Args:
            script_globals: Dictionary containing script execution results
            
        Returns:
            Tuple of (nodes, sinks) discovered in the script
            
        Raises:
            ScriptLoadError: If no sinks are found or graph is invalid
        """
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
        
        # Store discovered nodes for later use
        self._discovered_nodes = all_nodes
        
        logger.info(f"Discovered graph: {len(nodes)} nodes, {len(sinks)} sinks, {len(registry.get_edges())} connections")
        return nodes, sinks
    
    @property
    def discovered_nodes(self) -> Dict[str, Node]:
        """Get all discovered nodes by ID."""
        return self._discovered_nodes.copy()
