"""FastAPI application for RASL web interface.

Provides REST API endpoints for graph inspection and metrics,
WebSocket streaming for real-time updates, and an embedded
HTML dashboard.
"""

from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, Dict

import structlog
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from .state import AppState

if TYPE_CHECKING:
    from rasl.engine.graph import ExecutionPlan
    from rasl.runtime import Runtime

logger = structlog.get_logger()


def _get_state(request: Request) -> AppState:
    """Get the AppState from the request."""
    return request.app.state.rasl


def _get_state_ws(websocket: WebSocket) -> AppState:
    """Get the AppState from a WebSocket."""
    return websocket.app.state.rasl


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage WebSocket broadcast task lifecycle."""
    state: AppState = app.state.rasl
    state.start_time = time.time()
    
    # Start metrics broadcast task
    state.metrics_task = asyncio.create_task(_broadcast_metrics_loop(state))
    logger.info("api_server_started")
    
    yield
    
    # Cleanup
    if state.metrics_task:
        state.metrics_task.cancel()
        try:
            await state.metrics_task
        except asyncio.CancelledError:
            pass
    logger.info("api_server_stopped")


def create_app(runtime: "Runtime", plan: "ExecutionPlan") -> FastAPI:
    """Create the RASL FastAPI application.
    
    Args:
        runtime: The active Runtime instance for metrics access.
        plan: The ExecutionPlan for graph structure.
    
    Returns:
        Configured FastAPI application.
    """
    app = FastAPI(
        title="RASL API",
        description="Real-time Async Streaming for Lighting - Monitoring API",
        version="0.1.0",
        lifespan=lifespan,
    )
    
    # Store state in app.state (no globals!)
    app.state.rasl = AppState(runtime=runtime, plan=plan)
    
    # Register routes
    app.get("/", response_class=HTMLResponse)(dashboard)
    app.get("/api/v1/health")(health)
    app.get("/api/v1/graph")(graph)
    app.get("/api/v1/metrics")(metrics)
    app.get("/api/v1/nodes/{node_id}")(get_node)
    app.websocket("/api/v1/ws/metrics")(ws_metrics)
    
    return app


# -----------------------------------------------------------------------------
# REST Endpoints
# -----------------------------------------------------------------------------

async def health(request: Request) -> Dict[str, Any]:
    """Health check endpoint."""
    state = _get_state(request)
    return {
        "status": "ok",
        "uptime_seconds": round(state.uptime_seconds, 1),
    }


async def graph(request: Request) -> Dict[str, Any]:
    """Get graph structure."""
    state = _get_state(request)
    return state.plan.describe()


async def metrics(request: Request) -> Dict[str, Any]:
    """Get all node metrics."""
    state = _get_state(request)
    return {
        "timestamp": time.time(),
        "nodes": state.runtime.get_node_stats(),
    }


async def get_node(request: Request, node_id: str) -> Dict[str, Any]:
    """Get single node details and metrics."""
    state = _get_state(request)
    
    if node_id not in state.plan.nodes:
        raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found")
    
    node = state.plan.nodes[node_id]
    stats = state.runtime.get_node_stats(node_id)
    
    # Get edges for this node
    edges_out = []
    if node_id in state.plan.adjacency:
        for edge in state.plan.adjacency[node_id]:
            edges_out.append({
                "target": edge.target,
                "source_port": edge.source_port,
                "target_port": edge.target_port,
            })
    
    return {
        "id": node.id,
        "type": type(node).__name__,
        "inputs": list(node.inputs),
        "outputs": list(node.outputs),
        "edges": edges_out,
        "metrics": stats if stats else None,
    }


# -----------------------------------------------------------------------------
# WebSocket Endpoint
# -----------------------------------------------------------------------------

async def ws_metrics(websocket: WebSocket) -> None:
    """WebSocket endpoint for real-time metrics streaming."""
    state = _get_state_ws(websocket)
    
    await websocket.accept()
    state.add_client(websocket)
    logger.info("ws_client_connected", total_clients=state.client_count)
    
    try:
        # Keep connection alive, handle pings
        while True:
            try:
                # Wait for any message (ping/pong handled by protocol)
                await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
            except asyncio.TimeoutError:
                # Send ping to keep alive
                await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        pass
    finally:
        state.remove_client(websocket)
        logger.info("ws_client_disconnected", total_clients=state.client_count)


async def _broadcast_metrics_loop(state: AppState) -> None:
    """Background task to broadcast metrics to all WebSocket clients."""
    while True:
        await asyncio.sleep(1.0)  # Broadcast every second
        
        if not state.ws_clients:
            continue
        
        message = {
            "type": "metrics",
            "timestamp": time.time(),
            "nodes": state.runtime.get_node_stats(),
        }
        
        # Broadcast to all clients
        disconnected = set()
        for ws in state.ws_clients:
            try:
                await ws.send_json(message)
            except Exception:
                disconnected.add(ws)
        
        # Clean up disconnected clients
        state.ws_clients.difference_update(disconnected)


# -----------------------------------------------------------------------------
# Dashboard HTML
# -----------------------------------------------------------------------------

async def dashboard() -> HTMLResponse:
    """Serve the embedded monitoring dashboard."""
    return HTMLResponse(content=DASHBOARD_HTML)


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>RASL Dashboard</title>
    <script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js"></script>
    <style>
        :root {
            --bg: #0f172a;
            --card: #1e293b;
            --border: #334155;
            --text: #e2e8f0;
            --muted: #94a3b8;
            --accent: #38bdf8;
            --success: #4ade80;
            --warning: #fbbf24;
            --error: #f87171;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: system-ui, -apple-system, sans-serif;
            background: var(--bg);
            color: var(--text);
            padding: 1.5rem;
            min-height: 100vh;
        }
        header {
            display: flex;
            align-items: center;
            gap: 1rem;
            margin-bottom: 1.5rem;
            padding-bottom: 1rem;
            border-bottom: 1px solid var(--border);
        }
        header h1 { font-size: 1.5rem; font-weight: 600; }
        .status {
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            padding: 0.25rem 0.75rem;
            border-radius: 9999px;
            font-size: 0.875rem;
            font-weight: 500;
        }
        .status.ok { background: rgba(74, 222, 128, 0.15); color: var(--success); }
        .status.error { background: rgba(248, 113, 113, 0.15); color: var(--error); }
        .status::before {
            content: '';
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: currentColor;
        }
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
            gap: 1rem;
        }
        .card {
            background: var(--card);
            border: 1px solid var(--border);
            border-radius: 0.5rem;
            padding: 1rem;
        }
        .card h2 {
            font-size: 0.875rem;
            font-weight: 600;
            color: var(--muted);
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 1rem;
        }
        table { width: 100%; border-collapse: collapse; }
        th, td {
            text-align: left;
            padding: 0.5rem;
            border-bottom: 1px solid var(--border);
        }
        th { color: var(--muted); font-weight: 500; font-size: 0.75rem; text-transform: uppercase; }
        td { font-size: 0.875rem; }
        .mono { font-family: ui-monospace, monospace; }
        .num { text-align: right; }
        .good { color: var(--success); }
        .warn { color: var(--warning); }
        .bad { color: var(--error); }
        .node-type { color: var(--accent); }
        .edge-list { font-size: 0.75rem; color: var(--muted); }
        .uptime { color: var(--muted); font-size: 0.875rem; margin-left: auto; }
        .ws-indicator {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: var(--muted);
        }
        .ws-indicator.connected { background: var(--success); }
        footer {
            margin-top: 2rem;
            padding-top: 1rem;
            border-top: 1px solid var(--border);
            font-size: 0.75rem;
            color: var(--muted);
            display: flex;
            gap: 1rem;
        }
    </style>
</head>
<body x-data="dashboard()" x-init="init()">
    <header>
        <h1>RASL</h1>
        <span class="status" :class="health.status === 'ok' ? 'ok' : 'error'" x-text="health.status || 'connecting...'"></span>
        <span class="uptime" x-show="health.uptime_seconds">
            Uptime: <span x-text="formatUptime(health.uptime_seconds)"></span>
        </span>
    </header>
    
    <div class="grid">
        <div class="card">
            <h2>Graph</h2>
            <table>
                <thead>
                    <tr>
                        <th>Node</th>
                        <th>Type</th>
                        <th>Ports</th>
                    </tr>
                </thead>
                <tbody>
                    <template x-for="node in graph.nodes || []" :key="node.id">
                        <tr>
                            <td class="mono" x-text="node.id"></td>
                            <td class="node-type" x-text="node.type"></td>
                            <td class="edge-list">
                                <span x-show="node.inputs.length" x-text="'← ' + node.inputs.join(', ')"></span>
                                <span x-show="node.outputs.length" x-text="'→ ' + node.outputs.join(', ')"></span>
                            </td>
                        </tr>
                    </template>
                </tbody>
            </table>
        </div>
        
        <div class="card">
            <h2>Node Metrics</h2>
            <table>
                <thead>
                    <tr>
                        <th>Node</th>
                        <th class="num">Handles</th>
                        <th class="num">Avg (ms)</th>
                        <th class="num">Success</th>
                    </tr>
                </thead>
                <tbody>
                    <template x-for="(stats, nodeId) in metrics.nodes || {}" :key="nodeId">
                        <tr>
                            <td class="mono" x-text="nodeId"></td>
                            <td class="num mono" x-text="stats.handle_count.toLocaleString()"></td>
                            <td class="num mono" x-text="stats.avg_execution_time_ms.toFixed(2)"></td>
                            <td class="num" :class="successClass(stats.success_rate)">
                                <span x-text="(stats.success_rate * 100).toFixed(1) + '%'"></span>
                            </td>
                        </tr>
                    </template>
                </tbody>
            </table>
        </div>
        
        <div class="card" x-show="Object.values(metrics.nodes || {}).some(n => n.last_error)">
            <h2>Recent Errors</h2>
            <table>
                <thead>
                    <tr>
                        <th>Node</th>
                        <th>Error</th>
                        <th class="num">Failures</th>
                    </tr>
                </thead>
                <tbody>
                    <template x-for="(stats, nodeId) in metrics.nodes || {}" :key="nodeId">
                        <tr x-show="stats.last_error">
                            <td class="mono" x-text="nodeId"></td>
                            <td class="bad" x-text="stats.last_error"></td>
                            <td class="num bad" x-text="stats.consecutive_failures"></td>
                        </tr>
                    </template>
                </tbody>
            </table>
        </div>
    </div>
    
    <footer>
        <span>WebSocket: <span class="ws-indicator" :class="wsConnected && 'connected'"></span></span>
        <span>Last update: <span x-text="lastUpdate"></span></span>
    </footer>
    
    <script>
        function dashboard() {
            return {
                health: {},
                graph: {},
                metrics: { nodes: {} },
                wsConnected: false,
                lastUpdate: 'never',
                ws: null,
                
                async init() {
                    // Initial data fetch
                    await this.fetchData();
                    
                    // Setup WebSocket
                    this.connectWs();
                    
                    // Fallback polling every 5s
                    setInterval(() => this.fetchData(), 5000);
                },
                
                async fetchData() {
                    try {
                        const [health, graph, metrics] = await Promise.all([
                            fetch('/api/v1/health').then(r => r.json()),
                            fetch('/api/v1/graph').then(r => r.json()),
                            fetch('/api/v1/metrics').then(r => r.json()),
                        ]);
                        this.health = health;
                        this.graph = graph;
                        this.metrics = metrics;
                        this.lastUpdate = new Date().toLocaleTimeString();
                    } catch (e) {
                        console.error('Fetch error:', e);
                        this.health = { status: 'error' };
                    }
                },
                
                connectWs() {
                    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
                    this.ws = new WebSocket(`${proto}//${location.host}/api/v1/ws/metrics`);
                    
                    this.ws.onopen = () => {
                        this.wsConnected = true;
                    };
                    
                    this.ws.onmessage = (event) => {
                        const data = JSON.parse(event.data);
                        if (data.type === 'metrics') {
                            this.metrics = data;
                            this.lastUpdate = new Date().toLocaleTimeString();
                        }
                    };
                    
                    this.ws.onclose = () => {
                        this.wsConnected = false;
                        // Reconnect after 2s
                        setTimeout(() => this.connectWs(), 2000);
                    };
                    
                    this.ws.onerror = () => {
                        this.ws.close();
                    };
                },
                
                formatUptime(seconds) {
                    if (!seconds) return '';
                    const h = Math.floor(seconds / 3600);
                    const m = Math.floor((seconds % 3600) / 60);
                    const s = Math.floor(seconds % 60);
                    if (h > 0) return `${h}h ${m}m`;
                    if (m > 0) return `${m}m ${s}s`;
                    return `${s}s`;
                },
                
                successClass(rate) {
                    if (rate >= 0.99) return 'good';
                    if (rate >= 0.95) return 'warn';
                    return 'bad';
                }
            };
        }
    </script>
</body>
</html>
"""


async def run_server(
    app: FastAPI,
    host: str = "127.0.0.1",
    port: int = 8080,
) -> None:
    """Run the API server.
    
    This is a convenience function for running the server programmatically.
    In production, use uvicorn directly.
    
    Args:
        app: The FastAPI application.
        host: Host to bind to.
        port: Port to bind to.
    """
    import uvicorn
    
    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="warning",  # Reduce uvicorn noise
    )
    server = uvicorn.Server(config)
    await server.serve()
