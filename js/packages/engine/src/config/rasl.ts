import {
  type DocumentLoader,
  getDirectiveArgs,
  getDirectiveName,
  getSpanForRange,
  type ICstDirective,
  type ICstDocument,
  type IToken,
  parse,
  TokenType,
} from "@rasl/config";
import { createFsLoader } from "@rasl/config/node";
import { ErrorCodes, RaslError } from "../errors.js";
import { getNodeClass } from "../runtime/index.js";

import { GraphBuilder } from "../execution/builder.js";
import type { IConnectOptions, IResolvedSlice } from "../execution/edge.js";

export interface IRaslConfigError {
  message: string;
  line: number;
  column: number;
}

export interface IRaslUiConfig {
  port?: number;
}

export interface IRaslLoadResult {
  ui: IRaslUiConfig;
  builder: GraphBuilder;
  errors: IRaslConfigError[];
}

function tokenText(t: IToken): string {
  return String(t.value);
}

function tokensToText(tokens: readonly IToken[]): string {
  return tokens.map(tokenText).join(" ");
}

function snakeToCamel(s: string): string {
  return s.replace(/_([a-z])/g, (_m, c: string) => c.toUpperCase());
}

function coerceScalar(tokens: readonly IToken[]): unknown {
  if (tokens.length === 0) return true;
  if (tokens.length === 1) {
    const t = tokens[0]!;
    if (t.type === TokenType.Number) return typeof t.value === "number" ? t.value : parseFloat(String(t.value));
    if (t.type === TokenType.String) return String(t.value);
    if (t.type === TokenType.Word) return t.value;
    return t.value;
  }

  // Common RASL patterns like: 20 hz => "20hz".
  if (tokens.length === 2 && tokens[0]!.type === TokenType.Number && tokens[1]!.type === TokenType.Word) {
    return `${tokens[0]!.value}${tokens[1]!.value}`;
  }

  return tokensToText(tokens);
}

function parseSliceTokens(
  tokens: readonly IToken[],
  startIndex: number,
): { slice: IResolvedSlice; nextIndex: number } | null {
  const t0 = tokens[startIndex];
  if (!t0 || t0.type !== TokenType.LeftBracket) return null;

  const t1 = tokens[startIndex + 1];
  const t2 = tokens[startIndex + 2];
  if (!t1 || t1.type !== TokenType.Number) return null;
  if (!t2 || t2.type !== TokenType.Colon) return null;

  const start = typeof t1.value === "number" ? t1.value : parseInt(String(t1.value), 10);
  if (!Number.isFinite(start)) return null;

  const t3 = tokens[startIndex + 3];
  if (!t3) return null;

  if (t3.type === TokenType.RightBracket) {
    return { slice: { start, end: null }, nextIndex: startIndex + 4 };
  }

  if (t3.type !== TokenType.Number) return null;
  const t4 = tokens[startIndex + 4];
  if (!t4 || t4.type !== TokenType.RightBracket) return null;

  const end = typeof t3.value === "number" ? t3.value : parseInt(String(t3.value), 10);
  if (!Number.isFinite(end)) return null;

  return { slice: { start, end }, nextIndex: startIndex + 5 };
}

function directiveLocation(doc: ICstDocument, dir: ICstDirective): { line: number; column: number } {
  const span = getSpanForRange(doc, dir.tokenRange);
  return { line: span.start.line, column: span.start.column };
}

function parsePortsBlock(doc: ICstDocument, dir: ICstDirective): string[] {
  if (!dir.body) return [];
  const out: string[] = [];
  for (const child of dir.body) {
    out.push(getDirectiveName(doc, child));
  }
  return out;
}

function parseModelArg(tokens: readonly IToken[]): string {
  // Accept both "color:hsl" style tokens and "color : hsl" split tokens.
  if (tokens.length === 1) return tokenText(tokens[0]!);
  if (tokens.length === 3 && tokens[1]!.type === TokenType.Colon) {
    return `${tokens[0]!.value}:${tokens[2]!.value}`;
  }
  return tokensToText(tokens);
}

function parseConnectArgs(tokens: readonly IToken[]): {
  sourceNode: string;
  sourcePort: string | null;
  sourceSlice: IResolvedSlice | null;
  targetPort: string | null;
  targetSlice: IResolvedSlice | null;
} {
  let i = 0;

  const expectWord = (): string => {
    const t = tokens[i];
    if (!t || t.type !== TokenType.Word) {
      throw new RaslError(ErrorCodes.ParseError, "Expected word");
    }
    i++;
    return String(t.value);
  };

  const sourceSpec = expectWord();
  const dotIdx = sourceSpec.indexOf(".");
  const sourceNode = dotIdx === -1 ? sourceSpec : sourceSpec.slice(0, dotIdx);

  let sourcePort: string | null = null;
  if (dotIdx !== -1) {
    sourcePort = sourceSpec.slice(dotIdx + 1);
  }

  let sourceSlice: IResolvedSlice | null = null;
  const srcSlice = parseSliceTokens(tokens, i);
  if (srcSlice) {
    sourceSlice = srcSlice.slice;
    i = srcSlice.nextIndex;
  }

  let targetPort: string | null = null;
  let targetSlice: IResolvedSlice | null = null;

  if (tokens[i]?.type === TokenType.Word) {
    targetPort = expectWord();
    const tgtSlice = parseSliceTokens(tokens, i);
    if (tgtSlice) {
      targetSlice = tgtSlice.slice;
      i = tgtSlice.nextIndex;
    }
  }

  return { sourceNode, sourcePort, sourceSlice, targetPort, targetSlice };
}

function parseConnectOptionsFromBody(doc: ICstDocument, dir: ICstDirective): Pick<IConnectOptions, "repeat"> {
  const repeat = 1;
  if (!dir.body) return { repeat };

  let outRepeat = repeat;
  for (const opt of dir.body) {
    if (getDirectiveName(doc, opt) === "repeat") {
      const v = coerceScalar(getDirectiveArgs(doc, opt));
      const n = typeof v === "number" ? v : parseInt(String(v), 10);
      if (Number.isFinite(n) && n > 0) outRepeat = Math.floor(n);
    }
  }

  return { repeat: outRepeat };
}

function buildNodeConfigFromBody(
  doc: ICstDocument,
  nodeDir: ICstDirective,
): {
  properties: Record<string, unknown>;
  fills: Record<string, number>;
  connects: Array<{ conn: ReturnType<typeof parseConnectArgs>; options: Pick<IConnectOptions, "repeat"> }>;
} {
  const properties: Record<string, unknown> = {};
  const fills: Record<string, number> = {};
  const connects: Array<{ conn: ReturnType<typeof parseConnectArgs>; options: Pick<IConnectOptions, "repeat"> }> = [];

  if (!nodeDir.body) return { properties, fills, connects };

  for (const stmt of nodeDir.body) {
    const stmtName = getDirectiveName(doc, stmt);
    const stmtArgs = getDirectiveArgs(doc, stmt);

    if (stmtName === "connect") {
      const conn = parseConnectArgs(stmtArgs);
      const options = parseConnectOptionsFromBody(doc, stmt);
      connects.push({ conn, options });
      continue;
    }

    if (stmtName === "fill") {
      if (stmtArgs.length >= 2 && stmtArgs[0]!.type === TokenType.Word) {
        const port = String(stmtArgs[0]!.value);
        const value = coerceScalar(stmtArgs.slice(1));
        const num = typeof value === "number" ? value : parseFloat(String(value));
        if (Number.isFinite(num)) fills[port] = num;
      }
      continue;
    }

    if (stmtName === "ports") {
      properties.ports = parsePortsBlock(doc, stmt);
      continue;
    }

    // Generic property: name args...;
    const value = coerceScalar(stmtArgs);
    properties[stmtName] = value;
  }

  return { properties, fills, connects };
}

function applySnakeCaseCompatibility(obj: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = { ...obj };
  for (const [k, v] of Object.entries(obj)) {
    const camel = snakeToCamel(k);
    if (!(camel in out)) out[camel] = v;
  }
  return out;
}

function loadGraphFromDirective(doc: ICstDocument): {
  ui: IRaslUiConfig;
  graph: ICstDirective | null;
} {
  let graph: ICstDirective | null = null;
  const ui: IRaslUiConfig = {};

  for (const dir of doc.children) {
    const dirName = getDirectiveName(doc, dir);
    if (dirName === "graph") graph = dir;
    if (dirName === "ui" && dir.body) {
      for (const stmt of dir.body) {
        if (getDirectiveName(doc, stmt) === "port") {
          const v = coerceScalar(getDirectiveArgs(doc, stmt));
          const n = typeof v === "number" ? v : parseInt(String(v), 10);
          if (Number.isFinite(n)) ui.port = n;
        }
      }
    }
  }

  return { ui, graph };
}

export async function loadRaslConfigFromSource(
  source: string,
  options?: { path?: string; loader?: DocumentLoader },
): Promise<IRaslLoadResult> {
  const graph = await parse(source, {
    path: options?.path ?? "<root>",
    loader: options?.loader ?? createFsLoader(),
  });

  const errors: IRaslConfigError[] = [];
  const fatal = graph.diagnostics.filter((d) => d.severity === "error");
  if (fatal.length > 0) {
    for (const e of fatal) {
      errors.push({ message: e.message, line: e.span.start.line, column: e.span.start.column });
    }
    return { ui: {}, builder: new GraphBuilder(), errors };
  }

  const rootDoc = graph.root.parseResult.cst;
  const { ui, graph: graphDir } = loadGraphFromDirective(rootDoc);
  if (!graphDir || !graphDir.body) {
    return {
      ui,
      builder: new GraphBuilder(),
      errors: [{ message: "No 'graph' block found in configuration", line: 0, column: 0 }],
    };
  }

  const builder = new GraphBuilder();

  // Pass 1: instantiate nodes.
  for (const dir of graphDir.body) {
    if (getDirectiveName(rootDoc, dir) !== "node") continue;
    const args = getDirectiveArgs(rootDoc, dir);

    // node <Type> <id> [extra...]
    const typeTok = args[0];
    const idTok = args[1];
    if (!typeTok || typeTok.type !== TokenType.Word) continue;
    if (!idTok || idTok.type !== TokenType.Word) continue;

    const typeName = String(typeTok.value);
    const nodeId = String(idTok.value);

    const NodeClass = getNodeClass(typeName);
    if (!NodeClass) {
      const loc = directiveLocation(rootDoc, dir);
      errors.push({ message: `Unknown node type: ${typeName}`, line: loc.line, column: loc.column });
      continue;
    }

    const { properties, fills, connects } = buildNodeConfigFromBody(rootDoc, dir);

    const extra = args.slice(2);
    if (extra.length > 0) {
      // RASL convention: third arg is a model discriminator for some nodes.
      // Special-case literal shorthand: node literal <id> <model> <data...>;
      if (typeName === "literal") {
        // Accept both "color:hsl" (one token) and "color : hsl" (three tokens)
        // and treat remaining tokens as the literal payload data.
        const modelTokens =
          extra.length >= 3 && extra[1]!.type === TokenType.Colon ? extra.slice(0, 3) : extra.slice(0, 1);
        const dataTokens = extra.slice(modelTokens.length);

        properties.model = parseModelArg(modelTokens);
        if (dataTokens.length > 0) {
          properties.data = coerceScalar(dataTokens);
        }
      } else {
        const model = parseModelArg(extra);
        // Color uses model.
        properties.model = model;
      }
    }

    const configObj = applySnakeCaseCompatibility({ id: nodeId, ...properties, fill: fills });

    try {
      const node = new NodeClass(configObj);
      builder.addNode(node);
    } catch (e) {
      const loc = directiveLocation(rootDoc, dir);
      errors.push({
        message: `Failed to create node ${nodeId}: ${(e as Error).message}`,
        line: loc.line,
        column: loc.column,
      });
    }

    // Store connects on directive for pass 2 via a side table.
    const nodeDir = dir as typeof dir & { __raslConnects?: typeof connects };
    nodeDir.__raslConnects = connects;
  }

  // Pass 2: connect edges.
  for (const dir of graphDir.body) {
    if (getDirectiveName(rootDoc, dir) !== "node") continue;
    const args = getDirectiveArgs(rootDoc, dir);

    const idTok = args[1];
    if (!idTok || idTok.type !== TokenType.Word) continue;
    const targetNode = String(idTok.value);

    const nodeDir = dir as typeof dir & {
      __raslConnects?: Array<{
        conn: ReturnType<typeof parseConnectArgs>;
        options: Pick<IConnectOptions, "repeat">;
      }>;
    };
    const connects = nodeDir.__raslConnects;
    if (!connects) continue;

    for (const { conn, options } of connects) {
      const srcPort = conn.sourcePort ?? "out";
      const tgtPort = conn.targetPort ?? "in";
      const connectOptions: IConnectOptions = {
        repeat: options.repeat,
        sourceSlice: conn.sourceSlice ?? undefined,
        targetSlice: conn.targetSlice ?? undefined,
      };

      try {
        builder.connect(conn.sourceNode, srcPort, targetNode, tgtPort, connectOptions);
      } catch (e) {
        const loc = directiveLocation(rootDoc, dir);
        errors.push({
          message: `Failed to connect ${conn.sourceNode} -> ${targetNode}: ${(e as Error).message}`,
          line: loc.line,
          column: loc.column,
        });
      }
    }
  }

  return { ui, builder, errors };
}
