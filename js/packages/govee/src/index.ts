/**
 * @rasl/govee - Govee LAN protocol sink for RASL
 */

export {
  GoveeLightClient,
  DEFAULT_GOVEE_PORT,
  DEFAULT_CONNECT_TIMEOUT,
  DEFAULT_READ_TIMEOUT,
  DEFAULT_BASE_BACKOFF,
  DEFAULT_MAX_BACKOFF,
  type IGoveeSegmentInfo,
  type IGoveeDeviceInfo,
  type IGoveeColor,
  type IGoveeSegmentColor,
  type IGoveeLightClientOptions,
} from './client.js';

export { GoveeLightNode, type IGoveeLightNodeConfig } from './node.js';
