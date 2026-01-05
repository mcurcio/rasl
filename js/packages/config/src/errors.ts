export const ErrorCodes = {
  InvalidArgument: "INVALID_ARGUMENT",
  NotFound: "NOT_FOUND",
  NotReady: "NOT_READY",
  ParseError: "PARSE_ERROR",
  TimedOut: "TIMED_OUT",
  NetworkError: "NETWORK_ERROR",
  Internal: "INTERNAL",
} as const;

export type ErrorCode = (typeof ErrorCodes)[keyof typeof ErrorCodes];

export class RaslError extends Error {
  readonly code: ErrorCode;

  constructor(code: ErrorCode, message: string, options?: { cause?: unknown }) {
    super(message, options);
    this.code = code;
    this.name = new.target.name;
  }
}
