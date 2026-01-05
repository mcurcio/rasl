/**
 * Routing utilities for applying edge slices and repeat to frames.
 *
 * Handles the transformation of frames as they flow through edges,
 * applying source slices, repeat, and target slices as specified.
 */

import { ErrorCodes, RaslError } from "../errors.js";
import type { Edge, IResolvedSlice } from "../graph/edge.js";
import { Frame } from "../runtime/frame.js";
import { MatrixPayload } from "../runtime/payloads/matrix.js";

/**
 * Apply edge routing (slice + repeat) to a frame.
 *
 * Routing semantics:
 * 1. Apply sourceSlice to extract a subset of elements from the source
 * 2. Apply repeat to tile the sliced data
 * 3. Apply targetSlice to place data into the target range
 *
 * @param frame - Source frame to route
 * @param edge - Edge with slice/repeat metadata
 * @returns Routed frame (may be same instance if no transformation needed)
 */
export function applyEdgeRouting(frame: Frame, edge: Edge): Frame {
  const { sourceSlice, targetSlice, repeat } = edge;

  // Fast path: no routing needed
  if (sourceSlice === null && targetSlice === null && repeat === 1) {
    return frame;
  }

  const payload = frame.payload;

  // Only MatrixPayload supports slicing
  if (!(payload instanceof MatrixPayload)) {
    if (sourceSlice !== null || targetSlice !== null) {
      throw new RaslError(
        ErrorCodes.InvalidArgument,
        `Slicing requires MatrixPayload, got ${payload.constructor.name}`,
      );
    }
    return frame;
  }

  // Apply source slice
  let slicedPayload = payload;
  if (sourceSlice !== null) {
    slicedPayload = slicePayload(payload, sourceSlice);
  }

  // Apply repeat
  let repeatedPayload = slicedPayload;
  if (repeat > 1) {
    repeatedPayload = slicedPayload.repeat(repeat);
  }

  // Apply target slice (write into a specific range)
  // For now, target slice just validates the size matches
  if (targetSlice !== null) {
    const targetLen = targetSlice.end !== null ? targetSlice.end - targetSlice.start : null;
    if (targetLen !== null && repeatedPayload.count !== targetLen) {
      throw new RaslError(
        ErrorCodes.InvalidArgument,
        `Routed payload count ${repeatedPayload.count} does not match target slice length ${targetLen}`,
      );
    }
  }

  // Return new frame if payload changed
  if (repeatedPayload === payload) {
    return frame;
  }

  return frame.withPayload(repeatedPayload);
}

/**
 * Extract a slice of elements from a MatrixPayload.
 *
 * @param payload - Source payload
 * @param slice - Slice specification (start, end)
 * @returns New payload with sliced data
 */
export function slicePayload(payload: MatrixPayload, slice: IResolvedSlice): MatrixPayload {
  const { start, end } = slice;
  const actualEnd = end ?? payload.count;

  // Validate bounds
  if (start < 0 || start > payload.count) {
    throw new RaslError(ErrorCodes.InvalidArgument, `Slice start ${start} out of bounds [0, ${payload.count}]`);
  }
  if (actualEnd < start || actualEnd > payload.count) {
    throw new RaslError(
      ErrorCodes.InvalidArgument,
      `Slice end ${actualEnd} out of bounds [${start}, ${payload.count}]`,
    );
  }

  // Fast path: full slice
  if (start === 0 && actualEnd === payload.count) {
    return payload;
  }

  // Extract slice using subarray (zero-copy view)
  const startIdx = start * payload.channels;
  const endIdx = actualEnd * payload.channels;
  const slicedData = payload.data.subarray(startIdx, endIdx);

  // Create new payload with sliced data
  // Note: subarray creates a view, so we copy to ensure independence
  return new MatrixPayload(new Float32Array(slicedData), payload.channels);
}

/**
 * Validate that destination slices don't overlap.
 *
 * @param edges - Edges targeting the same input port
 * @throws RaslError if overlapping ranges detected
 */
export function validateNonOverlappingTargets(edges: readonly Edge[]): void {
  // Collect all target ranges
  const ranges: Array<{ edge: Edge; start: number; end: number | null }> = [];

  for (const edge of edges) {
    if (edge.targetSlice !== null) {
      ranges.push({
        edge,
        start: edge.targetSlice.start,
        end: edge.targetSlice.end,
      });
    }
  }

  // Check for overlaps
  for (let i = 0; i < ranges.length; i++) {
    for (let j = i + 1; j < ranges.length; j++) {
      const a = ranges[i];
      const b = ranges[j];

      // Check if ranges overlap
      // null end means "to the end", which we treat as infinity for overlap detection
      const aEnd = a.end ?? Infinity;
      const bEnd = b.end ?? Infinity;

      if (a.start < bEnd && b.start < aEnd) {
        throw new RaslError(
          ErrorCodes.InvalidArgument,
          `Overlapping target slices: ${a.edge.source}.${a.edge.sourcePort}[${a.start}:${a.end ?? ""}] ` +
            `and ${b.edge.source}.${b.edge.sourcePort}[${b.start}:${b.end ?? ""}] ` +
            `both target ${a.edge.target}.${a.edge.targetPort}`,
        );
      }
    }
  }
}
