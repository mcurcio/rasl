# @rasl/server

HTTP/WebSocket server for RASL runtime control and monitoring.

## Overview

This package provides a server for:

- REST API for graph inspection and control
- WebSocket streaming for real-time node data
- Static file serving for the web UI

## Key Types

### Server Configuration

```typescript
interface IServerConfig {
  port: number;
  host?: string;
  staticDir?: string;
  corsOrigins?: string[];
}
```

### WebSocket Messages

```typescript
interface IWsMessage {
  type: "subscribe" | "unsubscribe" | "data" | "error";
  topic?: string;
  payload?: unknown;
}

interface INodeDataMessage {
  type: "data";
  nodeId: string;
  portName: string;
  timestamp: number;
  values: number[];
}
```

### REST API Endpoints

- `GET /api/health` - Health check
- `GET /api/graph` - Get current graph description
- `GET /api/nodes` - List all nodes
- `GET /api/nodes/:id` - Get node details
- `GET /api/stats` - Get execution statistics
- `POST /api/control/start` - Start scheduler
- `POST /api/control/stop` - Stop scheduler

## Usage

```typescript
import { RaslServer } from "@rasl/server";

const server = new RaslServer({
  port: 8080,
  staticDir: "./public",
});

await server.start(scheduler);
```

## WebSocket Protocol

Connect to `ws://host:port/ws` for real-time updates.

```javascript
const ws = new WebSocket("ws://localhost:8080/ws");

// Subscribe to node output
ws.send(
  JSON.stringify({
    type: "subscribe",
    topic: "node:sine.out",
  }),
);

// Receive data
ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);
  if (msg.type === "data") {
    console.log(msg.values);
  }
};
```
