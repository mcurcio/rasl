"""
Parameter discovery for RASL nodes.

Automatically discovers and exposes parameters from nodes in the graph
without requiring manual expose_parameter() calls.
"""

import logging
from typing import Any, Dict, List

from rasl.core.nodes import Node

logger = logging.getLogger(__name__)


class ParameterDiscoverer:
    """
    Discovers parameters from nodes in a RASL graph.
    
    Automatically introspects node parameter specifications to create
    exposed parameter definitions for the web UI.
    """
    
    def __init__(self):
        pass
    
    def discover_parameters(self, nodes: List[Node]) -> List[Dict[str, Any]]:
        """
        Automatically discover parameters from all nodes in the graph.
        
        This replaces the need for manual expose_parameter() calls by introspecting
        each node's param_spec() to find all available parameters.
        
        Args:
            nodes: List of nodes to discover parameters from
            
        Returns:
            List of exposed parameter dictionaries
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
