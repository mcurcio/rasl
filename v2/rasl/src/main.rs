//! RASL - Real-time Animation Show Library
//!
//! CLI application for running RASL graphs.

use anyhow::{Context, Result};
use clap::{Parser, Subcommand};
use rasl_config::load_config;
use rasl_runtime::Scheduler;
use std::path::PathBuf;
use tracing::{info, Level};
use tracing_subscriber::FmtSubscriber;

#[derive(Parser)]
#[command(name = "rasl")]
#[command(author, version, about = "Real-time Animation Show Library", long_about = None)]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    /// Run a RASL configuration file
    Run {
        /// Path to the configuration file
        config: PathBuf,

        /// Number of ticks to run (0 = infinite)
        #[arg(short, long, default_value = "0")]
        ticks: u64,

        /// Enable verbose logging
        #[arg(short, long)]
        verbose: bool,
    },

    /// Validate a configuration file without running
    Check {
        /// Path to the configuration file
        config: PathBuf,
    },

    /// Describe the graph structure
    Describe {
        /// Path to the configuration file
        config: PathBuf,
    },
}

fn setup_logging(verbose: bool) {
    let level = if verbose { Level::DEBUG } else { Level::INFO };
    let subscriber = FmtSubscriber::builder()
        .with_max_level(level)
        .with_target(false)
        .compact()
        .init();
}

#[tokio::main]
async fn main() -> Result<()> {
    let cli = Cli::parse();

    match cli.command {
        Commands::Run { config, ticks, verbose } => {
            setup_logging(verbose);
            run_config(&config, ticks).await
        }
        Commands::Check { config } => {
            setup_logging(false);
            check_config(&config)
        }
        Commands::Describe { config } => {
            setup_logging(false);
            describe_config(&config)
        }
    }
}

async fn run_config(path: &PathBuf, ticks: u64) -> Result<()> {
    info!(path = %path.display(), "loading_config");

    let plan = load_config(path).context("Failed to load configuration")?;

    info!(
        nodes = plan.nodes.len(),
        rate_drivers = plan.rate_drivers.len(),
        "graph_loaded"
    );

    let mut scheduler = Scheduler::new(plan).context("Failed to create scheduler")?;

    if ticks > 0 {
        info!(ticks = ticks, "running_fixed_ticks");
        scheduler.run_ticks(ticks).context("Scheduler error")?;
    } else {
        info!("running_continuous");
        scheduler.run().await.context("Scheduler error")?;
    }

    info!("shutdown_complete");
    Ok(())
}

fn check_config(path: &PathBuf) -> Result<()> {
    info!(path = %path.display(), "checking_config");

    let plan = load_config(path).context("Failed to load configuration")?;

    println!("✓ Configuration valid");
    println!("  Nodes: {}", plan.nodes.len());
    println!("  Rate drivers: {}", plan.rate_drivers.len());

    for (id, hz) in &plan.rate_drivers {
        println!("    - {} @ {} Hz", id, hz);
    }

    Ok(())
}

fn describe_config(path: &PathBuf) -> Result<()> {
    let plan = load_config(path).context("Failed to load configuration")?;

    println!("RASL Graph: {}", path.display());
    println!();

    println!("Nodes ({}):", plan.nodes.len());
    for id in &plan.topo_order {
        let node = plan.nodes.get(id).unwrap();
        let inputs: Vec<_> = node.inputs().names().collect();
        let outputs: Vec<_> = node.outputs().names().collect();

        let rate = plan.rate_drivers.get(id).map(|hz| format!(" @ {} Hz", hz)).unwrap_or_default();

        println!("  {}{}:", id, rate);
        if !inputs.is_empty() {
            println!("    inputs: {:?}", inputs);
        }
        if !outputs.is_empty() {
            println!("    outputs: {:?}", outputs);
        }
    }

    println!();
    println!("Edges:");
    for (source, edges) in &plan.adjacency {
        for edge in edges {
            println!("  {}.{} -> {}.{}", source, edge.source_port, edge.target, edge.target_port);
        }
    }

    Ok(())
}
