import { format } from "node:util";

import type { ILogger, LogFields } from "../runtime/nodes/index.js";
import pino, { type DestinationStream, type LevelWithSilent, type Logger as PinoLogger } from "pino";

export type LogLevel = Exclude<LevelWithSilent, "fatal">;

export interface IEngineLoggerConfig {
  level?: LogLevel;
  pretty?: boolean;
  filePath?: string | null;
}

type IChildLogger = ILogger & { child?: (bindings: LogFields) => IChildLogger };

function isPlainObject(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v) && !(v instanceof Error);
}

function formatMessage(msg: unknown, args: unknown[]): string {
  if (typeof msg === "string") return format(msg, ...args);
  return format("%o", msg, ...args);
}

function wrapPino(logger: PinoLogger): IChildLogger {
  const call = (level: "trace" | "debug" | "info" | "warn" | "error", a0: unknown, rest: unknown[]): void => {
    if (a0 instanceof Error) {
      const msg = rest.length > 0 ? formatMessage(rest[0], rest.slice(1)) : undefined;
      (logger as any)[level]({ err: a0 }, msg);
      return;
    }

    if (isPlainObject(a0)) {
      const fields = a0 as LogFields;
      const msg = rest.length > 0 ? formatMessage(rest[0], rest.slice(1)) : undefined;
      (logger as any)[level](fields, msg);
      return;
    }

    (logger as any)[level](formatMessage(a0, rest));
  };

  return {
    trace: (a0: unknown, ...rest: unknown[]) => call("trace", a0, rest),
    debug: (a0: unknown, ...rest: unknown[]) => call("debug", a0, rest),
    info: (a0: unknown, ...rest: unknown[]) => call("info", a0, rest),
    warn: (a0: unknown, ...rest: unknown[]) => call("warn", a0, rest),
    error: (a0: unknown, ...rest: unknown[]) => call("error", a0, rest),
    child: (bindings: LogFields) => wrapPino(logger.child(bindings)),
  };
}

export function createEngineLogger(config?: IEngineLoggerConfig): IChildLogger {
  const level = (config?.level ?? "info") as LevelWithSilent;
  const pretty = config?.pretty ?? true;
  const filePath = config?.filePath ?? null;

  const streams: Array<{ level: LevelWithSilent; stream: DestinationStream }> = [];

  if (pretty) {
    const transport = pino.transport({
      target: "pino-pretty",
      options: {
        colorize: true,
        levelFirst: true,
        singleLine: true,
        translateTime: "SYS:standard",
        ignore: "pid,hostname",
      },
    });
    streams.push({ level, stream: transport as DestinationStream });
  }

  if (filePath) {
    const dest = pino.destination({ dest: filePath, mkdir: true, sync: false });
    streams.push({ level, stream: dest as DestinationStream });
  }

  const base =
    streams.length === 0
      ? pino({ level })
      : streams.length === 1
        ? pino({ level }, streams[0]!.stream)
        : pino({ level }, pino.multistream(streams));

  return wrapPino(base);
}

export function childLogger(logger: ILogger, bindings: LogFields): ILogger {
  const maybe = logger as IChildLogger;
  if (typeof maybe.child === "function") return maybe.child(bindings);
  return logger;
}

export function createConsoleLogger(): ILogger {
  const write = (level: "trace" | "debug" | "info" | "warn" | "error", a0: unknown, rest: unknown[]): void => {
    const prefix = `[${level.toUpperCase()}]`;

    if (a0 instanceof Error) {
      const msg = rest.length > 0 ? formatMessage(rest[0], rest.slice(1)) : a0.message;
      (console as any)[level === "trace" ? "debug" : level](`${prefix} ${msg}`, a0);
      return;
    }

    if (isPlainObject(a0)) {
      const fields = a0 as Record<string, unknown>;
      const msg = rest.length > 0 ? formatMessage(rest[0], rest.slice(1)) : "";
      const fieldsText = Object.keys(fields).length > 0 ? ` ${JSON.stringify(fields)}` : "";
      (console as any)[level === "trace" ? "debug" : level](`${prefix}${fieldsText} ${msg}`.trim());
      return;
    }

    const msg = formatMessage(a0, rest);
    (console as any)[level === "trace" ? "debug" : level](`${prefix} ${msg}`);
  };

  return {
    trace: (a0: unknown, ...rest: unknown[]) => write("trace", a0, rest),
    debug: (a0: unknown, ...rest: unknown[]) => write("debug", a0, rest),
    info: (a0: unknown, ...rest: unknown[]) => write("info", a0, rest),
    warn: (a0: unknown, ...rest: unknown[]) => write("warn", a0, rest),
    error: (a0: unknown, ...rest: unknown[]) => write("error", a0, rest),
  };
}
