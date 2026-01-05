/**
 * Frame - Immutable data container for the RASL graph.
 */

import type { FramePayload } from "./payloads/base.js";

/**
 * Metadata attached to frames.
 */
export type Metadata = Readonly<Record<string, string>>;

/**
 * Empty metadata singleton.
 */
export const EMPTY_METADATA: Metadata = Object.freeze({});

/**
 * Frame configuration.
 */
export interface IFrameConfig {
  topic: string;
  timestamp: number;
  payload: FramePayload;
  metadata?: Metadata;
}

/**
 * Immutable container for data flowing through the node graph.
 *
 * Frames are the fundamental unit of data exchange in RASL.
 * They carry a payload (the actual data) along with metadata
 * about when and where the data originated.
 */
export class Frame {
  /**
   * Topic identifier for this frame.
   */
  readonly topic: string;

  /**
   * Timestamp when this frame was created (seconds).
   */
  readonly timestamp: number;

  /**
   * The payload data.
   */
  readonly payload: FramePayload;

  /**
   * Additional metadata.
   */
  readonly metadata: Metadata;

  constructor(config: IFrameConfig) {
    this.topic = config.topic;
    this.timestamp = config.timestamp;
    this.payload = config.payload;
    this.metadata = config.metadata ?? EMPTY_METADATA;
  }

  /**
   * Create a new frame with a different payload.
   */
  withPayload(payload: FramePayload): Frame {
    return new Frame({
      topic: this.topic,
      timestamp: this.timestamp,
      payload,
      metadata: this.metadata,
    });
  }

  /**
   * Create a new frame with additional metadata.
   */
  withMetadata(metadata: Metadata): Frame {
    return new Frame({
      topic: this.topic,
      timestamp: this.timestamp,
      payload: this.payload,
      metadata: { ...this.metadata, ...metadata },
    });
  }
}
