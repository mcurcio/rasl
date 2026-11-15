const state = {
  graph: null,
  cy: null,
  selectedNodeId: null,
  metricsByNode: {},
  ws: null,
};

const GRAPHQL_ENDPOINT = "/graphql";

function $(id) {
  return document.getElementById(id);
}

function setText(id, value) {
  const el = $(id);
  if (!el) return;
  el.textContent = value;
}

function setWsConnected(connected) {
  const dot = $("wsDot");
  const label = $("wsLabel");
  if (dot) dot.classList.toggle("connected", connected);
  if (label) label.textContent = connected ? "WS: connected" : "WS: disconnected";
}

async function fetchJson(path) {
  const res = await fetch(path);
  if (!res.ok) {
    throw new Error(`${path} failed: ${res.status}`);
  }
  return await res.json();
}

async function fetchGraphQL(query, variables = undefined) {
  const res = await fetch(GRAPHQL_ENDPOINT, {
    method: "POST",
    headers: {
      "content-type": "application/json",
    },
    body: JSON.stringify({ query, variables }),
  });
  if (!res.ok) {
    throw new Error(`GraphQL request failed: ${res.status}`);
  }
  const payload = await res.json();
  if (payload.errors && payload.errors.length) {
    const msg = payload.errors.map((e) => e.message).join("\n");
    throw new Error(msg);
  }
  return payload.data;
}

function metricsColor(stats) {
  if (!stats) return "#475569";
  if (stats.last_error) return "#f87171";
  const r = typeof stats.success_rate === "number" ? stats.success_rate : 1.0;
  if (r >= 0.99) return "#4ade80";
  if (r >= 0.9) return "#fbbf24";
  return "#f87171";
}

function metricsBorder(stats) {
  if (!stats) return "#22314d";
  const avg = typeof stats.avg_execution_time_ms === "number" ? stats.avg_execution_time_ms : 0;
  if (avg <= 1.0) return "#1d4ed8";
  if (avg <= 5.0) return "#38bdf8";
  return "#fbbf24";
}

function buildElements(graph) {
  const nodes = (graph.nodes || []).map((n) => ({
    data: {
      id: n.id,
      label: n.id,
      type: n.type,
      inputs: n.inputs,
      outputs: n.outputs,
    },
  }));

  const edges = (graph.edges || []).map((e, idx) => {
    const [source, sourcePort, target, targetPort] = e;
    return {
      data: {
        id: `e${idx}:${source}:${sourcePort}->${target}:${targetPort}`,
        source,
        target,
        sourcePort,
        targetPort,
        label: `${sourcePort} → ${targetPort}`,
      },
    };
  });

  return [...nodes, ...edges];
}

function ensureCy() {
  if (state.cy) return state.cy;

  state.cy = cytoscape({
    container: $("cy"),
    elements: [],
    style: [
      {
        selector: "node",
        style: {
          "background-color": "#475569",
          "border-color": "#22314d",
          "border-width": 2,
          label: "data(label)",
          color: "#e5e7eb",
          "text-outline-color": "#0b1220",
          "text-outline-width": 2,
          "font-size": 10,
          "text-valign": "center",
          "text-halign": "center",
          width: 44,
          height: 44,
        },
      },
      {
        selector: "node:selected",
        style: {
          "border-width": 4,
          "border-color": "#38bdf8",
        },
      },
      {
        selector: "edge",
        style: {
          width: 2,
          "line-color": "#334155",
          "target-arrow-color": "#334155",
          "target-arrow-shape": "triangle",
          "curve-style": "bezier",
          label: "data(label)",
          color: "#9ca3af",
          "font-size": 9,
          "text-background-color": "#0b1220",
          "text-background-opacity": 0.7,
          "text-background-padding": 2,
          "text-rotation": "autorotate",
        },
      },
    ],
    layout: {
      name: "breadthfirst",
      directed: true,
      padding: 20,
      spacingFactor: 1.2,
      animate: false,
    },
  });

  state.cy.on("tap", "node", async (evt) => {
    const node = evt.target;
    const nodeId = node.id();
    state.selectedNodeId = nodeId;
    await refreshInspector(nodeId);
  });

  state.cy.on("tap", (evt) => {
    if (evt.target === state.cy) {
      state.selectedNodeId = null;
      clearInspector();
    }
  });

  return state.cy;
}

function clearInspector() {
  setText("selectedSubtitle", "No selection");
  setText("nodeId", "-");
  setText("nodeType", "-");
  setText("nodeInputs", "-");
  setText("nodeOutputs", "-");
  setText("mHandles", "-");
  setText("mAvg", "-");
  setText("mSuccess", "-");
  setText("mError", "-");
  setText("edges", "-");
}

function formatList(v) {
  if (!Array.isArray(v) || v.length === 0) return "-";
  return v.join(", ");
}

function applyMetricsToCy() {
  if (!state.cy) return;
  state.cy.nodes().forEach((n) => {
    const id = n.id();
    const stats = state.metricsByNode[id];
    n.style("background-color", metricsColor(stats));
    n.style("border-color", metricsBorder(stats));
  });
}

async function refreshGraph() {
  const data = await fetchGraphQL(
    `query Graph {\n  graph {\n    nodes { id type inputs outputs }\n    edges { source sourcePort target targetPort }\n    topologicalOrder\n  }\n}`
  );
  const graph = data?.graph;
  if (!graph) {
    setText("graphSummary", "Graph unavailable");
    return;
  }
  state.graph = graph;

  const cy = ensureCy();
  cy.elements().remove();
  cy.add(buildElements({
    nodes: graph.nodes,
    edges: (graph.edges || []).map((e) => [e.source, e.sourcePort, e.target, e.targetPort]),
  }));

  cy.layout({
    name: "breadthfirst",
    directed: true,
    padding: 20,
    spacingFactor: 1.25,
    animate: false,
  }).run();

  const nodeCount = (graph.nodes || []).length;
  const edgeCount = (graph.edges || []).length;
  setText("graphSummary", `${nodeCount} nodes, ${edgeCount} edges`);

  applyMetricsToCy();

  if (state.selectedNodeId) {
    const selected = cy.getElementById(state.selectedNodeId);
    if (selected && selected.length) selected.select();
  }
}

function updateInspectorFromNodeDetail(detail) {
  setText("selectedSubtitle", detail.id);
  setText("nodeId", detail.id);
  setText("nodeType", detail.type);
  setText("nodeInputs", formatList(detail.inputs));
  setText("nodeOutputs", formatList(detail.outputs));

  const m = detail.metrics || state.metricsByNode[detail.id] || null;
  if (m) {
    setText("mHandles", String(m.handle_count ?? "-"));
    setText("mAvg", typeof m.avg_execution_time_ms === "number" ? m.avg_execution_time_ms.toFixed(3) : "-");
    setText("mSuccess", typeof m.success_rate === "number" ? `${(m.success_rate * 100).toFixed(2)}%` : "-");
    setText("mError", m.last_error ? String(m.last_error) : "-");
  } else {
    setText("mHandles", "-");
    setText("mAvg", "-");
    setText("mSuccess", "-");
    setText("mError", "-");
  }

  const edgesOut = Array.isArray(detail.edges) ? detail.edges : [];
  if (edgesOut.length === 0) {
    setText("edges", "-");
  } else {
    const lines = edgesOut.map((e) => `${detail.id}.${e.source_port} -> ${e.target}.${e.target_port}`);
    setText("edges", lines.join("\n"));
  }
}

async function refreshInspector(nodeId) {
  if (!nodeId) {
    clearInspector();
    return;
  }
  try {
    const data = await fetchGraphQL(
      `query Node($id: String!) {\n  node(nodeId: $id) {\n    id\n    type\n    inputs\n    outputs\n    edges { source sourcePort target targetPort }\n    metrics {\n      nodeId\n      handleCount\n      avgExecutionTimeMs\n      successRate\n      lastError\n    }\n  }\n}`,
      { id: nodeId }
    );
    const n = data.node;
    if (!n) {
      setText("selectedSubtitle", `${nodeId} (not found)`);
      return;
    }

    const detail = {
      id: n.id,
      type: n.type,
      inputs: n.inputs || [],
      outputs: n.outputs || [],
      edges: (n.edges || []).map((e) => ({
        target: e.target,
        source_port: e.sourcePort,
        target_port: e.targetPort,
      })),
      metrics: n.metrics
        ? {
            handle_count: n.metrics.handleCount ?? 0,
            avg_execution_time_ms: n.metrics.avgExecutionTimeMs ?? 0,
            success_rate: n.metrics.successRate ?? 1,
            last_error: n.metrics.lastError ?? null,
          }
        : null,
    };
    updateInspectorFromNodeDetail(detail);
  } catch (e) {
    setText("selectedSubtitle", `${nodeId} (error)`);
    setText("edges", String(e));
  }
}

async function refreshMetricsOnce() {
  const data = await fetchGraphQL(
    `query Metrics {\n  metrics {\n    timestamp\n    nodes {\n      nodeId\n      handleCount\n      avgExecutionTimeMs\n      successRate\n      lastError\n    }\n  }\n}`
  );

  const nodes = (data.metrics?.nodes || []).reduce((acc, n) => {
    acc[n.nodeId] = {
      node_id: n.nodeId,
      handle_count: n.handleCount ?? 0,
      avg_execution_time_ms: n.avgExecutionTimeMs ?? 0,
      success_rate: n.successRate ?? 1,
      last_error: n.lastError ?? null,
    };
    return acc;
  }, {});
  state.metricsByNode = nodes;
  applyMetricsToCy();

  if (state.selectedNodeId) {
    await refreshInspector(state.selectedNodeId);
  }
}

function connectMetricsWs() {
  try {
    if (!globalThis.graphqlWs) {
      setWsConnected(false);
      return;
    }

    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    const wsPaths = [GRAPHQL_ENDPOINT, `${GRAPHQL_ENDPOINT}/`];

    const subscribe = (client) => {
      client.subscribe(
        {
          query: `subscription MetricsStream($intervalMs: Int!) {\n  metricsStream(intervalMs: $intervalMs) {\n    timestamp\n    nodes {\n      nodeId\n      handleCount\n      avgExecutionTimeMs\n      successRate\n      lastError\n    }\n  }\n}`,
          variables: { intervalMs: 1000 },
        },
        {
          next: async (result) => {
            const payload = result.data?.metricsStream;
            if (!payload) return;

            const nodes = (payload.nodes || []).reduce((acc, n) => {
              acc[n.nodeId] = {
                node_id: n.nodeId,
                handle_count: n.handleCount ?? 0,
                avg_execution_time_ms: n.avgExecutionTimeMs ?? 0,
                success_rate: n.successRate ?? 1,
                last_error: n.lastError ?? null,
              };
              return acc;
            }, {});
            state.metricsByNode = nodes;
            applyMetricsToCy();

            if (state.selectedNodeId) {
              await refreshInspector(state.selectedNodeId);
            }
          },
          error: () => {
            setWsConnected(false);
          },
          complete: () => {
            setWsConnected(false);
          },
        }
      );
    };

    let connectedOnce = false;
    let attempted = 0;

    const start = () => {
      const path = wsPaths[Math.min(attempted, wsPaths.length - 1)];
      attempted += 1;
      const url = `${proto}//${location.host}${path}`;

      const client = globalThis.graphqlWs.createClient({
        url,
        retryAttempts: 3,
        shouldRetry: () => true,
        keepAlive: 10_000,
        lazy: true,
        on: {
          connected: () => {
            connectedOnce = true;
            setWsConnected(true);
          },
          closed: () => {
            setWsConnected(false);
            if (!connectedOnce && attempted < wsPaths.length) {
              try {
                client.dispose();
              } catch {
                // ignore
              }
              start();
            }
          },
        },
      });

      state.ws = client;
      subscribe(client);
    };

    start();
  } catch (e) {
    setWsConnected(false);
  }
}

async function init() {
  clearInspector();
  ensureCy();

  $("refresh")?.addEventListener("click", async () => {
    await refreshGraph();
    await refreshMetricsOnce();
  });

  await refreshGraph().catch((e) => {
    setText("graphSummary", `Graph error: ${String(e)}`);
  });
  await refreshMetricsOnce().catch(() => {});

  connectMetricsWs();
  setInterval(() => refreshMetricsOnce().catch(() => {}), 5000);
}

init().catch((e) => {
  console.error(e);
});
