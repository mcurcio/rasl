/**
 * @rasl/govee - Govee LAN protocol sink for RASL
 */

export {
  DEFAULT_BASE_BACKOFF,
  DEFAULT_CONNECT_TIMEOUT,
  DEFAULT_GOVEE_PORT,
  DEFAULT_MAX_BACKOFF,
  DEFAULT_READ_TIMEOUT,
  GoveeLightClient,
  type IGoveeColor,
  type IGoveeDeviceInfo,
  type IGoveeLightClientOptions,
  type IGoveeSegmentColor,
  type IGoveeSegmentInfo,
} from "./client.js";
export { GoveeLightNode, type IGoveeLightNodeConfig } from "./node.js";
