/**
 * WebSocket message types for RASL server.
 */

/**
 * Base WebSocket message.
 */
export interface IWsMessage {
  type: string;
  topic?: string;
  payload?: unknown;
}

/**
 * Subscribe to a topic.
 */
export interface ISubscribeMessage extends IWsMessage {
  type: "subscribe";
  topic: string;
}

/**
 * Unsubscribe from a topic.
 */
export interface IUnsubscribeMessage extends IWsMessage {
  type: "unsubscribe";
  topic: string;
}

/**
 * Node data update message.
 */
export interface INodeDataMessage extends IWsMessage {
  type: "data";
  nodeId: string;
  portName: string;
  timestamp: number;
  values: number[];
}

/**
 * Error message.
 */
export interface IErrorMessage extends IWsMessage {
  type: "error";
  message: string;
  code?: string;
}

export interface IExternalUpdateMessage extends IWsMessage {
  type: "external:update";
  graphId: string;
  nodeId: string;
  values: number[];
}

export interface IExternalAckMessage extends IWsMessage {
  type: "external:ack";
  graphId: string;
  nodeId: string;
  size: number;
}
