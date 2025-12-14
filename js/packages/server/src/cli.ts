#!/usr/bin/env node
/**
 * RASL CLI - Run config files from the command line.
 */

import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { UnifiedScheduler, ensureNodesLoaded, loadRaslConfigFromSource } from '@rasl/engine';

// Import nodes to register them
import '@rasl/nodes';

interface INodeDef {
  id: string;
  type: string;
  properties: Record<string, unknown>;
  connections: Array<{
    sourceNode: string;
    sourcePort?: string;
    targetPort?: string;
  }>;
  fills: Record<string, number>;
}

// Legacy types kept local for now.

/**
 * Main CLI entry point.
 */
async function main(): Promise<void> {
  const args = process.argv.slice(2);

  if (args.length === 0) {
    console.log('Usage: rasl-server <config-file>');
    console.log('');
    console.log('Example:');
    console.log('  rasl-server virtual.conf');
    process.exit(1);
  }

  const configPath = resolve(args[0]);
  console.log(`Loading config: ${configPath}`);

  let source: string;
  try {
    source = readFileSync(configPath, 'utf-8');
  } catch (err) {
    console.error(`Failed to read config file: ${configPath}`);
    process.exit(1);
  }

  await ensureNodesLoaded();
  const load = loadRaslConfigFromSource(source);

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

  const scheduler = new UnifiedScheduler(plan);

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
