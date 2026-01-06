#!/usr/bin/env node
/**
 * RASL CLI - Run config files from the command line.
 */

// Register nodes from engine + extensions
import "@rasl/color";
import "@rasl/lighting";

import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { createEngineLogger, loadRaslConfigFromSource, type LogLevel, Engine } from "@rasl/engine";
import { RaslServer } from "./server.js";

// Legacy types kept local for now.

/**
 * Main CLI entry point.
 */
async function main(): Promise<void> {
  const args = process.argv.slice(2);

  const debug = args.includes("--debug");
  const verbose = args.includes("--verbose");
  const filteredArgs = args.filter((a) => a !== "--debug" && a !== "--verbose");

  if (filteredArgs.length === 0) {
    console.log("Usage: rasl-server [--debug|--verbose] <config-file>");
    console.log("");
    console.log("Example:");
    console.log("  rasl-server virtual.conf");
    process.exit(1);
  }

  const configPath = resolve(filteredArgs[0]);
  console.log(`Loading config: ${configPath}`);

  let source: string;
  try {
    source = readFileSync(configPath, "utf-8");
  } catch (err) {
    console.error(`Failed to read config file: ${configPath}`);
    process.exit(1);
  }

  const load = await loadRaslConfigFromSource(source, { path: configPath });

  if (load.errors.length > 0) {
    console.error("Config errors:");
    for (const err of load.errors) {
      console.error(`  Line ${err.line}: ${err.message}`);
    }
    process.exit(1);
  }

  console.log("Config parsed successfully");
  const builder = load.builder;
  const plan = builder.build();

  console.log(`Built graph with ${plan.nodes.size} nodes`);
  console.log("Starting engine...");

  const level: LogLevel = verbose ? "trace" : debug ? "debug" : "info";
  const logger = createEngineLogger({ level, pretty: true, filePath: null });

  // Create engine and add graph
  const engine = new Engine({ logger });
  engine.addGraph({ 
    id: "main", 
    plan, 
    autoStart: true 
  });

  // Create and configure server
  const server = new RaslServer({ port: 8080, logger });

  // Handle graceful shutdown
  process.on("SIGINT", () => {
    console.log("\nShutting down...");
    engine.stop();
    server.stop();
  });

  process.on("SIGTERM", () => {
    console.log("\nShutting down...");
    engine.stop();
    server.stop();
  });

  try {
    // Start both engine and server
    await engine.start();
    await server.start(engine);
    console.log("Engine and server started successfully");
  } catch (err) {
    console.error("Error:", err);
    process.exit(1);
  }
}

main().catch((err) => {
  console.error("Fatal error:", err);
  process.exit(1);
});
