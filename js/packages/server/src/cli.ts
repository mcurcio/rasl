#!/usr/bin/env node
/**
 * RASL CLI - Run config files from the command line.
 */

import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import {
  createEngineLogger,
  type LogLevel,
  UnifiedScheduler,
  loadRaslConfigFromSource,
} from '@rasl/engine';

// Register nodes from engine + extensions
import '@rasl/color';
import '@rasl/lighting';

// Legacy types kept local for now.

/**
 * Main CLI entry point.
 */
async function main(): Promise<void> {
  const args = process.argv.slice(2);

  const debug = args.includes('--debug');
  const verbose = args.includes('--verbose');
  const filteredArgs = args.filter((a) => a !== '--debug' && a !== '--verbose');

  if (filteredArgs.length === 0) {
    console.log('Usage: rasl-server [--debug|--verbose] <config-file>');
    console.log('');
    console.log('Example:');
    console.log('  rasl-server virtual.conf');
    process.exit(1);
  }

  const configPath = resolve(filteredArgs[0]);
  console.log(`Loading config: ${configPath}`);

  let source: string;
  try {
    source = readFileSync(configPath, 'utf-8');
  } catch (err) {
    console.error(`Failed to read config file: ${configPath}`);
    process.exit(1);
  }

  const load = await loadRaslConfigFromSource(source, { path: configPath });

  if (load.errors.length > 0) {
    console.error('Config errors:');
    for (const err of load.errors) {
      console.error(`  Line ${err.line}: ${err.message}`);
    }
    process.exit(1);
  }

  console.log('Config parsed successfully');
  const builder = load.builder;
  const plan = builder.build();

  console.log(`Built graph with ${plan.nodes.size} nodes`);
  console.log('Starting scheduler...');

  const level: LogLevel = verbose ? 'trace' : debug ? 'debug' : 'info';
  const logger = createEngineLogger({ level, pretty: true, filePath: null });

  const scheduler = new UnifiedScheduler(plan, { logger });

  // Handle graceful shutdown
  process.on('SIGINT', () => {
    console.log('\nShutting down...');
    scheduler.stop();
  });

  process.on('SIGTERM', () => {
    console.log('\nShutting down...');
    scheduler.stop();
  });

  try {
    await scheduler.run();
  } catch (err) {
    console.error('Scheduler error:', err);
    process.exit(1);
  }
}

main().catch((err) => {
  console.error('Fatal error:', err);
  process.exit(1);
});
