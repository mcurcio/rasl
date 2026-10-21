import { describe, expect, test, vi } from "vitest";
import { createEngineLogger, createConsoleLogger } from "./index.js";
import type { ILogger } from "../nodes/index.js";

describe("New Logger API", () => {
  test("should support message-only logging", () => {
    const logger = createConsoleLogger();
    const consoleSpy = vi.spyOn(console, "info").mockImplementation(() => {});
    
    logger.info("Test message");
    
    expect(consoleSpy).toHaveBeenCalledWith("[INFO] Test message");
    consoleSpy.mockRestore();
  });

  test("should support message + fields logging", () => {
    const logger = createConsoleLogger();
    const consoleSpy = vi.spyOn(console, "info").mockImplementation(() => {});
    
    logger.info("Test message", { nodeId: "test", count: 42 });
    
    expect(consoleSpy).toHaveBeenCalledWith("[INFO] Test message", { nodeId: "test", count: 42 });
    consoleSpy.mockRestore();
  });

  test("should support error logging with error object", () => {
    const logger = createConsoleLogger();
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    
    const error = new Error("Test error");
    logger.error("Something failed", error);
    
    expect(consoleSpy).toHaveBeenCalledWith("[ERROR] Something failed", { err: error });
    consoleSpy.mockRestore();
  });

  test("should support error logging with error + fields", () => {
    const logger = createConsoleLogger();
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    
    const error = new Error("Test error");
    logger.error("Something failed", error, { nodeId: "test" });
    
    expect(consoleSpy).toHaveBeenCalledWith("[ERROR] Something failed", { err: error, nodeId: "test" });
    consoleSpy.mockRestore();
  });

  test("should support error logging without error object", () => {
    const logger = createConsoleLogger();
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    
    logger.error("Something failed");
    
    expect(consoleSpy).toHaveBeenCalledWith("[ERROR] Something failed");
    consoleSpy.mockRestore();
  });

  test("should create child loggers with bindings", () => {
    const logger = createConsoleLogger();
    const consoleSpy = vi.spyOn(console, "info").mockImplementation(() => {});
    
    const childLogger = logger.child({ component: "test" });
    childLogger.info("Child message");
    
    expect(consoleSpy).toHaveBeenCalledWith('[INFO] [{"component":"test"}] Child message');
    consoleSpy.mockRestore();
  });

  test("should work with engine logger", () => {
    const logger = createEngineLogger({ level: "debug", pretty: false });
    
    // Should not throw
    logger.trace("Trace message");
    logger.debug("Debug message", { key: "value" });
    logger.info("Info message");
    logger.warn("Warning message");
    logger.error("Error message", new Error("test"), { context: "test" });
    
    // Child logger should work
    const child = logger.child({ module: "test" });
    child.info("Child message");
  });

  test("should maintain consistent API across all log levels", () => {
    const logger = createConsoleLogger();
    const levels: Array<keyof Omit<ILogger, "error" | "child">> = ["trace", "debug", "info", "warn"];
    
    levels.forEach((level) => {
      expect(() => {
        logger[level as keyof Pick<ILogger, "trace" | "debug" | "info" | "warn">]("Test message");
        logger[level as keyof Pick<ILogger, "trace" | "debug" | "info" | "warn">]("Test message", { key: "value" });
      }).not.toThrow();
    });
    
    // Error level has additional overloads
    expect(() => {
      logger.error("Error message");
      logger.error("Error message", new Error("test"));
      logger.error("Error message", new Error("test"), { key: "value" });
    }).not.toThrow();
  });
});
