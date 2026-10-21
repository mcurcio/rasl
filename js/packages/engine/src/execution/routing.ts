import { RaslError, ErrorCodes } from "../errors.js";
import { Frame, MatrixPayload } from "../runtime/index.js";
import type { Edge, IResolvedSlice } from "./edge.js";

function sliceBounds(slice: IResolvedSlice | null, length: number): { start: number; end: number } {
  if (!slice) return { start: 0, end: length };
  const end = slice.end ?? length;
  if (slice.start < 0 || end < slice.start || end > length) {
    throw new RaslError(ErrorCodes.InvalidArgument, `Invalid slice [${slice.start}:${slice.end ?? ""}] for length ${length}`);
  }
  return { start: slice.start, end };
}

export function applyEdgeRouting(frame: Frame, edge: Edge): Frame {
  const payload = frame.payload;
  if (!(payload instanceof MatrixPayload)) {
    return frame;
  }

  const source = sliceBounds(edge.sourceSlice, payload.data.length);
  const sourceData = payload.data.slice(source.start, source.end);
  const repeated =
    edge.repeat <= 1
      ? sourceData
      : (() => {
          const out = new Float32Array(sourceData.length * edge.repeat);
          for (let i = 0; i < edge.repeat; i++) out.set(sourceData, i * sourceData.length);
          return out;
        })();

  if (!edge.targetSlice) {
    return frame.withPayload(new MatrixPayload(repeated, payload.channels));
  }

  const targetEnd = edge.targetSlice.end ?? edge.targetSlice.start + repeated.length;
  const out = new Float32Array(targetEnd);
  out.set(repeated, edge.targetSlice.start);
  return frame.withPayload(new MatrixPayload(out, payload.channels));
}

function scalarBoundsForRows(slice: IResolvedSlice | null, rows: number, channels: number): { start: number; end: number } {
  const rowBounds = sliceBounds(slice, rows);
  return { start: rowBounds.start * channels, end: rowBounds.end * channels };
}

export function composeInputFrame(sources: Array<{ edge: Edge; frame: Frame }>, fixedRows: number | null): Frame | null {
  if (sources.length === 0) return null;
  if (sources.length === 1) {
    const { edge, frame } = sources[0]!;
    if (!edge.sourceSlice && !edge.targetSlice && edge.repeat <= 1) return frame;
  }

  let first: Frame | null = null;
  let rows = fixedRows ?? 0;
  let channels = 1;
  const matrices: Array<{ edge: Edge; payload: MatrixPayload }> = [];

  for (const { edge, frame } of sources) {
    if (!(frame.payload instanceof MatrixPayload)) continue;
    if (!first) first = frame;
    const payload = frame.payload;
    channels = Math.max(channels, payload.channels);
    const sourceRows = edge.sourceSlice
      ? (edge.sourceSlice.end ?? payload.count) - edge.sourceSlice.start
      : payload.count;
    const repeatedRows = sourceRows * Math.max(1, edge.repeat);
    const targetEnd = edge.targetSlice?.end ?? (edge.targetSlice ? edge.targetSlice.start + repeatedRows : repeatedRows);
    rows = Math.max(rows, targetEnd);
    matrices.push({ edge, payload });
  }

  if (!first || rows <= 0) return null;

  const out = new Float32Array(rows * channels);
  for (const { edge, payload } of matrices) {
    const source = scalarBoundsForRows(edge.sourceSlice, payload.count, payload.channels);
    const sourceRows = (source.end - source.start) / payload.channels;
    const targetStartRow = edge.targetSlice?.start ?? 0;
    const repeat = Math.max(1, edge.repeat);

    for (let r = 0; r < repeat; r++) {
      for (let row = 0; row < sourceRows; row++) {
        const outRow = targetStartRow + r * sourceRows + row;
        if (edge.targetSlice?.end !== null && edge.targetSlice?.end !== undefined && outRow >= edge.targetSlice.end) break;
        const inOffset = source.start + row * payload.channels;
        const outOffset = outRow * channels;
        const cols = Math.min(payload.channels, channels);
        for (let col = 0; col < cols; col++) {
          out[outOffset + col] = payload.data[inOffset + col] ?? 0;
        }
      }
    }
  }

  return new Frame({
    topic: first.topic,
    timestamp: first.timestamp,
    payload: new MatrixPayload(out, channels),
    metadata: first.metadata,
  });
}

export function validateNonOverlappingTargets(edges: Edge[]): void {
  const ranges: Array<{ start: number; end: number }> = [];
  for (const edge of edges) {
    if (!edge.targetSlice) continue;
    const end = edge.targetSlice.end ?? Number.POSITIVE_INFINITY;
    ranges.push({ start: edge.targetSlice.start, end });
  }

  ranges.sort((a, b) => a.start - b.start);
  for (let i = 1; i < ranges.length; i++) {
    if (ranges[i]!.start < ranges[i - 1]!.end) {
      throw new RaslError(ErrorCodes.InvalidArgument, "Overlapping target slices for input port");
    }
  }
}
