# Phase 3: Web Interface & Monitoring

**Duration**: 7-10 days  
**Goal**: Complete web-based monitoring and control interface

## Objectives

1. **REST API**: Complete HTTP endpoints for graph inspection and control
2. **WebSocket Streams**: Real-time data and event streaming  
3. **Web UI**: Interactive monitoring dashboard with parameter controls
4. **Graph Visualization**: Visual representation of node graphs
5. **Performance Monitoring**: Real-time metrics and diagnostics

## Success Criteria

- [ ] Web UI accessible at http://localhost:8080
- [ ] Real-time graph visualization with live data
- [ ] Parameter controls work with immediate feedback
- [ ] Performance metrics displayed accurately
- [ ] WebSocket streams handle high-frequency updates
- [ ] Mobile-responsive interface

## Implementation Strategy

### 1. FastAPI Backend Enhancement

**Enhanced Web Server** (`rasl/server/api.py`):
```python
from fastapi import FastAPI, WebSocket, HTTPException
from fastapi.staticfiles import StaticFiles
import asyncio
from typing import Dict, Any, List

class RASLWebServer:
    def __init__(self, engine: Engine):
        self.engine = engine
        self.app = FastAPI(title="RASL API", version="0.1.0")
        self.websocket_clients = set()
        self._setup_routes()
    
    def _setup_routes(self):
        @self.app.get("/api/graph")
        async def get_graph():
            graph = self.engine.graph()
            return {
                "nodes": [self._serialize_node(n) for n in graph.nodes()],
                "edges": [self._serialize_edge(e) for e in graph.edges()]
            }
        
        @self.app.patch("/api/nodes/{node_id}")
        async def update_node(node_id: str, params: Dict[str, Any]):
            node = self._find_node(node_id)
            self.engine.patch(node, **params)
            await self._broadcast_parameter_change(node_id, params)
            return {"status": "updated"}
        
        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            await self._handle_websocket(websocket)
```

### 2. Web UI Implementation

**Main Dashboard** (`rasl/ui/static/index.html`):
```html
<!DOCTYPE html>
<html>
<head>
    <title>RASL Control Panel</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
</head>
<body>
    <div id="app">
        <header class="header">
            <h1>RASL Control Panel</h1>
            <div class="status" id="connection-status">Connecting...</div>
        </header>
        
        <main class="main">
            <div class="graph-panel">
                <h2>Graph Visualization</h2>
                <div id="graph-container"></div>
            </div>
            
            <div class="control-panel">
                <h2>Parameters</h2>
                <div id="parameters-container"></div>
            </div>
        </main>
    </div>
    
    <script src="/static/js/main.js"></script>
</body>
</html>
```

**JavaScript Client** (`rasl/ui/static/js/main.js`):
```javascript
class RASLClient {
    constructor() {
        this.ws = null;
        this.graph = null;
        this.initWebSocket();
        this.initUI();
    }
    
    initWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws`;
        
        this.ws = new WebSocket(wsUrl);
        
        this.ws.onmessage = (event) => {
            const message = JSON.parse(event.data);
            this.handleMessage(message);
        };
    }
    
    handleMessage(message) {
        switch (message.type) {
            case 'graph_state':
                this.updateGraph(message.data);
                break;
            case 'parameter_change':
                this.updateParameter(message.node_id, message.params);
                break;
        }
    }
}
```

## Implementation Order

1. **Days 1-2**: FastAPI backend with REST endpoints
2. **Days 3-4**: WebSocket implementation  
3. **Days 5-6**: Basic web UI with graph visualization
4. **Days 7-8**: Parameter controls
5. **Days 9-10**: Performance monitoring and polish

## Dependencies

**Requires**: Phase 1 (Engine)  
**Parallel with**: Phase 2 (Nodes)
