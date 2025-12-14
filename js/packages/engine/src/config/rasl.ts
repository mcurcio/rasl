import { parse, type ICstDirective, type ICstDocument, type IToken, TokenType } from '@rasl/config';
import { GraphBuilder } from '../graph/builder.js';
import type { IConnectOptions, IResolvedSlice } from '../graph/edge.js';
import { getNodeClass } from '../runtime/registry.js';

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
  return t.value;
}

function tokensToText(tokens: readonly IToken[]): string {
  return tokens.map(tokenText).join(' ');
}

function snakeToCamel(s: string): string {
  return s.replace(/_([a-z])/g, (_m, c: string) => c.toUpperCase());
}

function coerceScalar(tokens: readonly IToken[]): unknown {
  if (tokens.length === 0) return true;
  if (tokens.length === 1) {
    const t = tokens[0]!;
    if (t.type === TokenType.Number) return parseFloat(t.value);
    if (t.type === TokenType.Boolean) return t.value === 'true';
    if (t.type === TokenType.String) return t.value;
    if (t.type === TokenType.Identifier) return t.value;
    return t.value;
  }

  // Common RASL patterns like: 20 hz => "20hz".
  if (tokens.length === 2 && tokens[0]!.type === TokenType.Number && tokens[1]!.type === TokenType.Identifier) {
    return `${tokens[0]!.value}${tokens[1]!.value}`;
  }

  return tokensToText(tokens);
}

function parseSliceToken(t: IToken | null): IResolvedSlice | null {
  if (!t) return null;
  if (t.type !== TokenType.String) return null;
  const s = t.value.trim();
  if (!s.startsWith('[') || !s.endsWith(']')) return null;
  const inner = s.slice(1, -1);
  const parts = inner.split(':');
  if (parts.length !== 2) return null;
  const start = parseInt(parts[0]!, 10);
  const endStr = parts[1]!.trim();
  const end = endStr.length === 0 ? null : parseInt(endStr, 10);
  if (!Number.isFinite(start)) return null;
  if (end !== null && !Number.isFinite(end)) return null;
  return { start, end };
}

function parsePortsBlock(dir: ICstDirective): string[] {
  if (!dir.body) return [];
  const out: string[] = [];
  for (const child of dir.body) {
    out.push(child.name);
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
  const expectIdent = (): string => {
    const t = tokens[i];
    if (!t || t.type !== TokenType.Identifier) {
      throw new Error('Expected identifier');
    }
    i++;
    return t.value;
  };

  const sourceNode = expectIdent();

  let sourcePort: string | null = null;
  if (tokens[i]?.type === TokenType.Dot) {
    i++; // dot
    sourcePort = expectIdent();
  }

  let sourceSlice: IResolvedSlice | null = null;
  const maybeSrcSlice = parseSliceToken(tokens[i] ?? null);
  if (maybeSrcSlice) {
    sourceSlice = maybeSrcSlice;
    i++;
  }

  let targetPort: string | null = null;
  let targetSlice: IResolvedSlice | null = null;

  if (tokens[i]?.type === TokenType.Identifier) {
    targetPort = expectIdent();
    const maybeTgtSlice = parseSliceToken(tokens[i] ?? null);
    if (maybeTgtSlice) {
      targetSlice = maybeTgtSlice;
      i++;
    }
  }

  return { sourceNode, sourcePort, sourceSlice, targetPort, targetSlice };
}

function parseConnectOptions(dir: ICstDirective): Pick<IConnectOptions, 'repeat'> {
  const repeat = 1;
  if (!dir.body) return { repeat };

  let outRepeat = repeat;
  for (const opt of dir.body) {
    if (opt.name === 'repeat') {
      const v = coerceScalar(opt.args);
      const n = typeof v === 'number' ? v : parseInt(String(v), 10);
      if (Number.isFinite(n) && n > 0) outRepeat = Math.floor(n);
    }
  }

  return { repeat: outRepeat };
}

function buildNodeConfigFromBody(nodeDir: ICstDirective): {
  properties: Record<string, unknown>;
  fills: Record<string, number>;
  connects: Array<{ conn: ReturnType<typeof parseConnectArgs>; options: Pick<IConnectOptions, 'repeat'> }>;
} {
  const properties: Record<string, unknown> = {};
  const fills: Record<string, number> = {};
  const connects: Array<{ conn: ReturnType<typeof parseConnectArgs>; options: Pick<IConnectOptions, 'repeat'> }> = [];

  if (!nodeDir.body) return { properties, fills, connects };

  for (const stmt of nodeDir.body) {
    if (stmt.name === 'connect') {
      const conn = parseConnectArgs(stmt.args);
      const options = parseConnectOptions(stmt);
      connects.push({ conn, options });
      continue;
    }

    if (stmt.name === 'fill') {
      if (stmt.args.length >= 2 && stmt.args[0]!.type === TokenType.Identifier) {
        const port = stmt.args[0]!.value;
        const value = coerceScalar(stmt.args.slice(1));
        const num = typeof value === 'number' ? value : parseFloat(String(value));
        if (Number.isFinite(num)) fills[port] = num;
      }
      continue;
    }

    if (stmt.name === 'ports') {
      properties.ports = parsePortsBlock(stmt);
      continue;
    }

    // Generic property: name args...;
    const value = coerceScalar(stmt.args);
    properties[stmt.name] = value;
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

function loadRaslFromDirective(doc: ICstDocument): { ui: IRaslUiConfig; rasl: ICstDirective | null } {
  let rasl: ICstDirective | null = null;
  const ui: IRaslUiConfig = {};

  for (const dir of doc.children) {
    if (dir.name === 'rasl') rasl = dir;
    if (dir.name === 'ui' && dir.body) {
      for (const stmt of dir.body) {
        if (stmt.name === 'port') {
          const v = coerceScalar(stmt.args);
          const n = typeof v === 'number' ? v : parseInt(String(v), 10);
          if (Number.isFinite(n)) ui.port = n;
        }
      }
    }
  }

  return { ui, rasl };
}

export function loadRaslConfigFromSource(source: string): IRaslLoadResult {
  const result = parse(source);

  const errors: IRaslConfigError[] = [];
  if (result.errors.length > 0) {
    for (const e of result.errors) {
      errors.push({ message: e.message, line: e.line, column: e.column });
    }
    return { ui: {}, builder: new GraphBuilder(), errors };
  }

  if (!result.cst) {
    return { ui: {}, builder: new GraphBuilder(), errors: [{ message: 'Failed to parse config', line: 0, column: 0 }] };
  }

  const { ui, rasl } = loadRaslFromDirective(result.cst);
  if (!rasl || !rasl.body) {
    return { ui, builder: new GraphBuilder(), errors: [{ message: "No 'rasl' block found in configuration", line: 0, column: 0 }] };
  }

  const builder = new GraphBuilder();

  // Pass 1: instantiate nodes.
  for (const dir of rasl.body) {
    if (dir.name !== 'node') continue;

    // node <Type> <id> [extra...]
    const typeTok = dir.args[0];
    const idTok = dir.args[1];
    if (!typeTok || typeTok.type !== TokenType.Identifier) continue;
    if (!idTok || idTok.type !== TokenType.Identifier) continue;

    const typeName = typeTok.value;
    const nodeId = idTok.value;

    const NodeClass = getNodeClass(typeName);
    if (!NodeClass) {
      errors.push({ message: `Unknown node type: ${typeName}`, line: dir.span.line, column: dir.span.column });
      continue;
    }

    const { properties, fills, connects } = buildNodeConfigFromBody(dir);

    const extra = dir.args.slice(2);
    if (extra.length > 0) {
      // RASL convention: third arg is a model discriminator for some nodes.
      const model = parseModelArg(extra);
      // literal uses model, Color uses model.
      properties.model = model;
    }

    const configObj = applySnakeCaseCompatibility({ id: nodeId, ...properties, fill: fills });

    try {
      const node = new NodeClass(configObj);
      builder.addNode(node);
    } catch (e) {
      errors.push({ message: `Failed to create node ${nodeId}: ${(e as Error).message}`, line: dir.span.line, column: dir.span.column });
    }

    // Store connects on directive for pass 2 via a side table.
    (dir as unknown as { __raslConnects?: typeof connects }).__raslConnects = connects;
  }

  // Pass 2: connect edges.
  for (const dir of rasl.body) {
    if (dir.name !== 'node') continue;

    const idTok = dir.args[1];
    if (!idTok || idTok.type !== TokenType.Identifier) continue;
    const targetNode = idTok.value;

    const connects = (dir as unknown as { __raslConnects?: Array<{ conn: ReturnType<typeof parseConnectArgs>; options: Pick<IConnectOptions, 'repeat'> }> }).__raslConnects;
    if (!connects) continue;

    for (const { conn, options } of connects) {
      const srcPort = conn.sourcePort ?? 'out';
      const tgtPort = conn.targetPort ?? 'in';
      const connectOptions: IConnectOptions = {
        repeat: options.repeat,
        sourceSlice: conn.sourceSlice ?? undefined,
        targetSlice: conn.targetSlice ?? undefined,
      };

      try {
        builder.connect(conn.sourceNode, srcPort, targetNode, tgtPort, connectOptions);
      } catch (e) {
        errors.push({ message: `Failed to connect ${conn.sourceNode} -> ${targetNode}: ${(e as Error).message}`, line: dir.span.line, column: dir.span.column });
      }
    }
  }

  return { ui, builder, errors };
}
