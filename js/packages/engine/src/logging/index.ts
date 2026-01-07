import type { ILogger, LogFields } from "../nodes/index.js";
import pino, { type DestinationStream, type LevelWithSilent, type Logger as PinoLogger } from "pino";

export type LogLevel = Exclude<LevelWithSilent, "fatal">;

export interface IEngineLoggerConfig {
  level?: LogLevel;
  pretty?: boolean;
  filePath?: string | null;
}

function wrapPino(logger: PinoLogger): ILogger {
  return {
    trace: (message: string, fields?: Record<string, unknown>) => {
      if (fields) {
        logger.trace(fields, message);
      } else {
        logger.trace(message);
      }
    },
    debug: (message: string, fields?: Record<string, unknown>) => {
      if (fields) {
        logger.debug(fields, message);
      } else {
        logger.debug(message);
      }
    },
    info: (message: string, fields?: Record<string, unknown>) => {
      if (fields) {
        logger.info(fields, message);
      } else {
        logger.info(message);
      }
    },
    warn: (message: string, fields?: Record<string, unknown>) => {
      if (fields) {
        logger.warn(fields, message);
      } else {
        logger.warn(message);
      }
    },
    error: (message: string, error?: Error, fields?: Record<string, unknown>) => {
      const logFields: Record<string, unknown> = fields ? { ...fields } : {};
      if (error) {
        logFields.err = error;
      }
      if (Object.keys(logFields).length > 0) {
        logger.error(logFields, message);
      } else {
        logger.error(message);
      }
    },
    child: (bindings: Record<string, unknown>) => wrapPino(logger.child(bindings)),
  };
}

export function createEngineLogger(config?: IEngineLoggerConfig): ILogger {
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
  return logger.child(bindings);
}

export function createConsoleLogger(): ILogger {
  return {
    trace: (message: string, fields?: Record<string, unknown>) => {
      const prefix = "[TRACE]";
      if (fields) {
        console.log(`${prefix} ${message}`, fields);
      } else {
        console.log(`${prefix} ${message}`);
      }
    },
    debug: (message: string, fields?: Record<string, unknown>) => {
      const prefix = "[DEBUG]";
      if (fields) {
        console.debug(`${prefix} ${message}`, fields);
      } else {
        console.debug(`${prefix} ${message}`);
      }
    },
    info: (message: string, fields?: Record<string, unknown>) => {
      const prefix = "[INFO]";
      if (fields) {
        console.info(`${prefix} ${message}`, fields);
      } else {
        console.info(`${prefix} ${message}`);
      }
    },
    warn: (message: string, fields?: Record<string, unknown>) => {
      const prefix = "[WARN]";
      if (fields) {
        console.warn(`${prefix} ${message}`, fields);
      } else {
        console.warn(`${prefix} ${message}`);
      }
    },
    error: (message: string, error?: Error, fields?: Record<string, unknown>) => {
      const prefix = "[ERROR]";
      if (error || fields) {
        const allFields = { ...fields, ...(error && { err: error }) };
        console.error(`${prefix} ${message}`, allFields);
      } else {
        console.error(`${prefix} ${message}`);
      }
    },
    child: (bindings: Record<string, unknown>) => {
      // For console logger, just return the same logger with bindings noted in messages
      return {
        ...createConsoleLogger(),
        trace: (message: string, fields?: Record<string, unknown>) => {
          const prefix = `[TRACE] [${JSON.stringify(bindings)}]`;
          if (fields) {
            console.log(`${prefix} ${message}`, { ...bindings, ...fields });
          } else {
            console.log(`${prefix} ${message}`);
          }
        },
        debug: (message: string, fields?: Record<string, unknown>) => {
          const prefix = `[DEBUG] [${JSON.stringify(bindings)}]`;
          if (fields) {
            console.debug(`${prefix} ${message}`, { ...bindings, ...fields });
          } else {
            console.debug(`${prefix} ${message}`);
          }
        },
        info: (message: string, fields?: Record<string, unknown>) => {
          const prefix = `[INFO] [${JSON.stringify(bindings)}]`;
          if (fields) {
            console.info(`${prefix} ${message}`, { ...bindings, ...fields });
          } else {
            console.info(`${prefix} ${message}`);
          }
        },
        warn: (message: string, fields?: Record<string, unknown>) => {
          const prefix = `[WARN] [${JSON.stringify(bindings)}]`;
          if (fields) {
            console.warn(`${prefix} ${message}`, { ...bindings, ...fields });
          } else {
            console.warn(`${prefix} ${message}`);
          }
        },
        error: (message: string, error?: Error, fields?: Record<string, unknown>) => {
          const prefix = `[ERROR] [${JSON.stringify(bindings)}]`;
          const allFields = { ...bindings, ...fields, ...(error && { err: error }) };
          console.error(`${prefix} ${message}`, allFields);
        },
        child: (moreBindings: Record<string, unknown>) => {
          return createConsoleLogger().child({ ...bindings, ...moreBindings });
        },
      };
    },
  };
}
