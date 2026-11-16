// The rasl GraphQL API (docs/web-api.md): the config as written, node types, edits, metrics.
import { createClient } from "graphql-ws";

export type Port = {
  readonly name: string;
  readonly types: readonly string[];
  readonly minCount: number | null;
  readonly maxCount: number | null;
  readonly components: number | null;
  readonly default: boolean;
};

export type SourcePlace = { readonly path: string; readonly line: number };

export type ConfigNode = {
  readonly id: string;
  readonly type: string;
  readonly place: SourcePlace;
  readonly locked: string | null;
  readonly settings: readonly { readonly key: string; readonly values: string }[];
  readonly inputs: readonly Port[];
  readonly outputs: readonly Port[];
  readonly error: string | null;
};

export type ConfigEdge = {
  readonly target: string;
  readonly source: string;
  readonly port: string | null;
  readonly sourceNode: string | null;
  readonly sourcePort: string | null;
  readonly targetPort: string | null;
  readonly repeat: number | null;
  readonly repeatUntil: number | null;
  readonly place: SourcePlace;
  readonly locked: string | null;
};

export type Endpoint = {
  readonly node: string;
  readonly port: string | null;
  readonly sliceStart: number | null;
  readonly sliceEnd: number | null;
};

export type ConfigProblem = {
  readonly message: string;
  readonly formatted: string;
  readonly path: string | null;
  readonly line: number;
  readonly column: number | null;
  readonly connection: {
    readonly problem: string;
    readonly source: Endpoint;
    readonly target: Endpoint;
    readonly other: Endpoint | null;
    readonly supplied: number | null;
    readonly takes: number | null;
  } | null;
};

export type ConfigGraph = {
  readonly path: string;
  readonly version: string;
  readonly editable: boolean;
  readonly nodes: readonly ConfigNode[];
  readonly edges: readonly ConfigEdge[];
  readonly error: ConfigProblem | null;
};

export type NodeType = {
  readonly name: string;
  readonly aliases: readonly string[];
  readonly summary: string;
  readonly schema: JsonSchema | null;
};

export type JsonSchema = {
  readonly type?: string;
  readonly title?: string;
  readonly description?: string;
  readonly default?: unknown;
  readonly enum?: readonly unknown[];
  readonly properties?: Readonly<Record<string, JsonSchema>>;
  readonly required?: readonly string[];
};

export type Setting = { readonly key: string; readonly values: string };

/** One edit, as the API takes it: exactly one key. */
export type Edit =
  | {
      readonly addNode: {
        readonly type: string;
        readonly id: string;
        readonly values: string;
        readonly settings: readonly Setting[];
      };
    }
  | { readonly removeNode: { readonly id: string } }
  | { readonly renameNode: { readonly id: string; readonly newId: string } }
  | {
      readonly connect: {
        readonly source: string;
        readonly target: string;
        readonly port: string | null;
        readonly repeat: number | null;
        readonly repeatUntil: number | null;
      };
    }
  | { readonly disconnect: { readonly source: string; readonly target: string; readonly port: string | null } };

export type EditOutcome = {
  readonly ok: boolean;
  readonly version: string;
  readonly changes: readonly { readonly path: string; readonly diff: string }[];
  readonly saved: readonly string[];
  readonly error: ConfigProblem | null;
  readonly refused: { readonly index: number; readonly message: string } | null;
  readonly conflict: string | null;
};

export type NodeMetrics = {
  readonly nodeId: string;
  readonly successRate: number;
  readonly avgExecutionTimeMs: number;
  readonly lastError: string | null;
  readonly handleCount: number;
};

export class ApiError extends Error {}

const ENDPOINT = "graphql";

async function request<T>(query: string, variables: Record<string, unknown> = {}): Promise<T> {
  const response = await fetch(ENDPOINT, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ query, variables }),
  });
  if (!response.ok) throw new ApiError(`GraphQL request failed: ${response.status}`);
  const payload = (await response.json()) as { data?: T; errors?: readonly { message: string }[] };
  if (payload.errors?.length) throw new ApiError(payload.errors.map((e) => e.message).join("\n"));
  if (payload.data === undefined) throw new ApiError("GraphQL answered without data");
  return payload.data;
}

const PORT = "name types minCount maxCount components default";
const PROBLEM = `message formatted path line column connection {
  problem supplied takes
  source { node port sliceStart sliceEnd } target { node port sliceStart sliceEnd } other { node port sliceStart sliceEnd } }`;
const NODE = `id type place { path line } locked settings { key values } inputs { ${PORT} } outputs { ${PORT} } error`;

export async function fetchConfigGraph(): Promise<ConfigGraph | null> {
  const data = await request<{ configGraph: ConfigGraph | null }>(`{ configGraph {
    path version editable error { ${PROBLEM} }
    nodes { ${NODE} }
    edges { target source port sourceNode sourcePort targetPort repeat repeatUntil place { path line } locked }
  } }`);
  return data.configGraph;
}

export async function fetchNodeTypes(): Promise<readonly NodeType[]> {
  const data = await request<{ nodeTypes: NodeType[] }>("{ nodeTypes { name aliases summary schema } }");
  return data.nodeTypes;
}

export async function previewNode(type: string, values: string, settings: readonly Setting[]): Promise<ConfigNode> {
  const data = await request<{ previewNode: ConfigNode }>(
    `query($type: String!, $values: String!, $settings: [SettingInput!]) {
      previewNode(type: $type, values: $values, settings: $settings) { ${NODE} } }`,
    { type, values, settings },
  );
  return data.previewNode;
}

async function runEdits(
  mutation: "previewEdits" | "applyEdits",
  baseVersion: string,
  edits: readonly Edit[],
): Promise<EditOutcome> {
  const data = await request<Record<string, EditOutcome>>(
    `mutation($v: String!, $edits: [EditInput!]!) { ${mutation}(baseVersion: $v, edits: $edits) {
      ok version saved conflict refused { index message } changes { path diff } error { ${PROBLEM} } } }`,
    { v: baseVersion, edits },
  );
  const outcome = data[mutation];
  if (outcome === undefined) throw new ApiError(`No ${mutation} in the answer`);
  return outcome;
}

export function previewEdits(baseVersion: string, edits: readonly Edit[]): Promise<EditOutcome> {
  return runEdits("previewEdits", baseVersion, edits);
}

export function applyEdits(baseVersion: string, edits: readonly Edit[]): Promise<EditOutcome> {
  return runEdits("applyEdits", baseVersion, edits);
}

export type Subscriptions = {
  readonly onConfigChange: (version: string, lastReloadOk: boolean | null, lastReloadError: string | null) => void;
  readonly onMetrics: (metrics: readonly NodeMetrics[]) => void;
  readonly onConnection: (connected: boolean) => void;
};

/** Subscribe to config changes and metrics; returns a function that stops both. */
export function subscribe(handlers: Subscriptions): () => void {
  const url = new URL(ENDPOINT, window.location.href);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  const client = createClient({
    url: url.toString(),
    retryAttempts: Infinity,
    shouldRetry: () => true,
    on: { connected: () => handlers.onConnection(true), closed: () => handlers.onConnection(false) },
  });
  const stopConfig = client.subscribe<{
    configChanged: { version: string; lastReloadOk: boolean | null; lastReloadError: string | null };
  }>(
    { query: "subscription { configChanged { version lastReloadOk lastReloadError } }" },
    {
      next: ({ data }) => {
        if (data)
          handlers.onConfigChange(
            data.configChanged.version,
            data.configChanged.lastReloadOk,
            data.configChanged.lastReloadError,
          );
      },
      error: () => undefined,
      complete: () => undefined,
    },
  );
  const stopMetrics = client.subscribe<{ metricsStream: { nodes: NodeMetrics[] } }>(
    {
      query:
        "subscription { metricsStream(intervalMs: 1000) { nodes { nodeId successRate avgExecutionTimeMs lastError handleCount } } }",
    },
    {
      next: ({ data }) => {
        if (data) handlers.onMetrics(data.metricsStream.nodes);
      },
      error: () => undefined,
      complete: () => undefined,
    },
  );
  return () => {
    stopConfig();
    stopMetrics();
    void client.dispose();
  };
}
