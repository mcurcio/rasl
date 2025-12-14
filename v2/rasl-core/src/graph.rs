//! Graph construction and execution plan.
//!
//! The GraphBuilder assembles nodes and edges into an ExecutionPlan
//! that the scheduler can execute.

use crate::node::{Node, NodeId, NodeError, NodeResult};
use std::collections::{HashMap, HashSet};
use thiserror::Error;

/// Errors during graph construction.
#[derive(Debug, Error)]
pub enum GraphError {
    #[error("Duplicate node ID: {0}")]
    DuplicateNode(NodeId),

    #[error("Node not found: {0}")]
    NodeNotFound(NodeId),

    #[error("Port not found: {0}.{1}")]
    PortNotFound(NodeId, String),

    #[error("Cycle detected in graph")]
    CycleDetected,

    #[error("Invalid connection: {0}")]
    InvalidConnection(String),
}

/// Edge connecting two node ports.
#[derive(Debug, Clone)]
pub struct Edge {
    /// Source node ID.
    pub source: NodeId,

    /// Source port name.
    pub source_port: String,

    /// Target node ID.
    pub target: NodeId,

    /// Target port name.
    pub target_port: String,

    /// Repeat the source data N times.
    pub repeat: Option<usize>,

    /// Repeat until reaching this many elements.
    pub repeat_until: Option<usize>,
}

impl Edge {
    /// Create a new edge.
    pub fn new(
        source: impl Into<NodeId>,
        source_port: impl Into<String>,
        target: impl Into<NodeId>,
        target_port: impl Into<String>,
    ) -> Self {
        Self {
            source: source.into(),
            source_port: source_port.into(),
            target: target.into(),
            target_port: target_port.into(),
            repeat: None,
            repeat_until: None,
        }
    }

    /// Set repeat count.
    pub fn with_repeat(mut self, n: usize) -> Self {
        self.repeat = Some(n);
        self
    }

    /// Set repeat_until count.
    pub fn with_repeat_until(mut self, n: usize) -> Self {
        self.repeat_until = Some(n);
        self
    }
}

/// Compiled graph ready for execution.
#[derive(Default)]
pub struct ExecutionPlan {
    /// Nodes by ID.
    pub nodes: HashMap<NodeId, Box<dyn Node>>,

    /// Edges (adjacency list: source -> edges).
    pub adjacency: HashMap<NodeId, Vec<Edge>>,

    /// Reverse adjacency (target -> edges).
    pub incoming: HashMap<NodeId, Vec<Edge>>,

    /// Topological order for execution.
    pub topo_order: Vec<NodeId>,

    /// Rate-driving sinks (node_id -> hz).
    pub rate_drivers: HashMap<NodeId, f64>,
}

impl ExecutionPlan {
    /// Get a node by ID.
    pub fn get_node(&self, id: &str) -> Option<&dyn Node> {
        self.nodes.get(id).map(|n| n.as_ref())
    }

    /// Get a mutable node by ID.
    pub fn get_node_mut(&mut self, id: &str) -> Option<&mut Box<dyn Node>> {
        self.nodes.get_mut(id)
    }

    /// Iterate over all nodes.
    pub fn iter_nodes(&self) -> impl Iterator<Item = (&NodeId, &dyn Node)> {
        self.nodes.iter().map(|(id, n)| (id, n.as_ref()))
    }

    /// Get edges from a source node.
    pub fn edges_from(&self, source: &str) -> &[Edge] {
        self.adjacency.get(source).map(|v| v.as_slice()).unwrap_or(&[])
    }

    /// Get edges to a target node.
    pub fn edges_to(&self, target: &str) -> &[Edge] {
        self.incoming.get(target).map(|v| v.as_slice()).unwrap_or(&[])
    }

    /// Check if the graph is empty.
    pub fn is_empty(&self) -> bool {
        self.nodes.is_empty()
    }

    /// Number of nodes.
    pub fn len(&self) -> usize {
        self.nodes.len()
    }
}

impl std::fmt::Debug for ExecutionPlan {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("ExecutionPlan")
            .field("nodes", &self.nodes.keys().collect::<Vec<_>>())
            .field("edges", &self.adjacency.values().flatten().count())
            .field("rate_drivers", &self.rate_drivers)
            .finish()
    }
}

/// Builder for constructing graphs.
pub struct GraphBuilder {
    nodes: HashMap<NodeId, Box<dyn Node>>,
    edges: Vec<Edge>,
}

impl GraphBuilder {
    /// Create a new graph builder.
    pub fn new() -> Self {
        Self {
            nodes: HashMap::new(),
            edges: Vec::new(),
        }
    }

    /// Add a node to the graph.
    pub fn add_node(&mut self, node: Box<dyn Node>) -> Result<&mut Self, GraphError> {
        let id = node.id().to_string();
        if self.nodes.contains_key(&id) {
            return Err(GraphError::DuplicateNode(id));
        }
        self.nodes.insert(id, node);
        Ok(self)
    }

    /// Add an edge connecting two ports.
    pub fn add_edge(&mut self, edge: Edge) -> Result<&mut Self, GraphError> {
        // Validate source exists
        if !self.nodes.contains_key(&edge.source) {
            return Err(GraphError::NodeNotFound(edge.source.clone()));
        }

        // Validate target exists
        if !self.nodes.contains_key(&edge.target) {
            return Err(GraphError::NodeNotFound(edge.target.clone()));
        }

        self.edges.push(edge);
        Ok(self)
    }

    /// Connect two ports with a new edge.
    pub fn connect(
        &mut self,
        source: impl Into<NodeId>,
        source_port: impl Into<String>,
        target: impl Into<NodeId>,
        target_port: impl Into<String>,
    ) -> Result<&mut Self, GraphError> {
        self.add_edge(Edge::new(source, source_port, target, target_port))
    }

    /// Build the execution plan.
    pub fn build(self) -> Result<ExecutionPlan, GraphError> {
        let mut plan = ExecutionPlan {
            nodes: self.nodes,
            adjacency: HashMap::new(),
            incoming: HashMap::new(),
            topo_order: Vec::new(),
            rate_drivers: HashMap::new(),
        };

        // Build adjacency lists
        for edge in self.edges {
            plan.adjacency
                .entry(edge.source.clone())
                .or_default()
                .push(edge.clone());
            plan.incoming
                .entry(edge.target.clone())
                .or_default()
                .push(edge);
        }

        // Compute topological order
        plan.topo_order = topological_sort(&plan.nodes, &plan.adjacency)?;

        // Find rate drivers
        for (id, node) in &plan.nodes {
            if let Some(hz) = node.pull_rate() {
                plan.rate_drivers.insert(id.clone(), hz);
            }
        }

        Ok(plan)
    }
}

impl Default for GraphBuilder {
    fn default() -> Self {
        Self::new()
    }
}

/// Compute topological order using Kahn's algorithm.
fn topological_sort(
    nodes: &HashMap<NodeId, Box<dyn Node>>,
    adjacency: &HashMap<NodeId, Vec<Edge>>,
) -> Result<Vec<NodeId>, GraphError> {
    let mut in_degree: HashMap<NodeId, usize> = HashMap::new();
    let mut result = Vec::new();

    // Initialize in-degrees
    for id in nodes.keys() {
        in_degree.insert(id.clone(), 0);
    }

    // Count incoming edges
    for edges in adjacency.values() {
        for edge in edges {
            *in_degree.entry(edge.target.clone()).or_default() += 1;
        }
    }

    // Start with nodes that have no incoming edges
    let mut queue: Vec<NodeId> = in_degree
        .iter()
        .filter(|(_, &deg)| deg == 0)
        .map(|(id, _)| id.clone())
        .collect();

    queue.sort(); // Deterministic order

    while let Some(node_id) = queue.pop() {
        result.push(node_id.clone());

        if let Some(edges) = adjacency.get(&node_id) {
            for edge in edges {
                if let Some(deg) = in_degree.get_mut(&edge.target) {
                    *deg -= 1;
                    if *deg == 0 {
                        queue.push(edge.target.clone());
                        queue.sort();
                    }
                }
            }
        }
    }

    // Check for cycles
    if result.len() != nodes.len() {
        // Note: RASL allows cycles (back-edges), so we just warn
        // and include remaining nodes
        for id in nodes.keys() {
            if !result.contains(id) {
                result.push(id.clone());
            }
        }
    }

    Ok(result)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::port::{InputPorts, OutputPorts};
    use crate::tick::TickContext;

    struct DummyNode {
        id: String,
        inputs: InputPorts,
        outputs: OutputPorts,
    }

    impl DummyNode {
        fn new(id: &str) -> Self {
            Self {
                id: id.to_string(),
                inputs: InputPorts::new(),
                outputs: OutputPorts::new(),
            }
        }
    }

    impl Node for DummyNode {
        crate::impl_node_basics!(DummyNode, id, inputs, outputs);

        fn pull(&mut self, _tick: &TickContext) -> NodeResult<()> {
            Ok(())
        }
    }

    #[test]
    fn test_graph_builder() {
        let mut builder = GraphBuilder::new();
        builder.add_node(Box::new(DummyNode::new("a"))).unwrap();
        builder.add_node(Box::new(DummyNode::new("b"))).unwrap();
        builder.connect("a", "out", "b", "in").unwrap();

        let plan = builder.build().unwrap();
        assert_eq!(plan.len(), 2);
    }

    #[test]
    fn test_duplicate_node() {
        let mut builder = GraphBuilder::new();
        builder.add_node(Box::new(DummyNode::new("a"))).unwrap();
        let result = builder.add_node(Box::new(DummyNode::new("a")));
        assert!(result.is_err());
    }
}
