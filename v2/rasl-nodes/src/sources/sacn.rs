//! sACN/E1.31 source node for receiving DMX universe data.
//!
//! This is a placeholder implementation. Full sACN support requires
//! async UDP socket handling with multicast.

use std::net::UdpSocket;
use std::sync::mpsc::{self, Receiver, Sender};
use std::thread::{self, JoinHandle};

use rasl_core::frame::Frame;
use rasl_core::node::{Node, NodeContext, NodeResult, NodeError};
use rasl_core::payload::MatrixPayload;
use rasl_core::port::{InputPorts, OutputPort, OutputPorts, PortSpec};
use rasl_core::tick::TickContext;
use rasl_core::impl_node_basics;
use tracing::{info, warn, debug};

const SACN_PORT: u16 = 5568;
const DMX_CHANNELS: usize = 512;

/// Configuration for sACN source node.
#[derive(Debug, Clone)]
pub struct SacnSourceConfig {
    pub id: String,
    pub universes: Vec<u16>,
    pub bind_address: String,
    pub bind_port: u16,
}

impl Default for SacnSourceConfig {
    fn default() -> Self {
        Self {
            id: "sacn".to_string(),
            universes: vec![1],
            bind_address: "0.0.0.0".to_string(),
            bind_port: SACN_PORT,
        }
    }
}

/// sACN source node that receives E1.31 DMX data.
pub struct SacnSourceNode {
    id: String,
    inputs: InputPorts,
    outputs: OutputPorts,
    
    universes: Vec<u16>,
    bind_address: String,
    bind_port: u16,
    
    // Background receiver
    receiver: Option<Receiver<Vec<u8>>>,
    worker_handle: Option<JoinHandle<()>>,
    shutdown_tx: Option<Sender<()>>,
    
    // Latest received data
    latest_data: Option<Vec<f32>>,
}

impl SacnSourceNode {
    pub fn new(config: SacnSourceConfig) -> Self {
        let mut outputs = OutputPorts::new();
        outputs.add(OutputPort::new(PortSpec::new("dmx", "matrix")));
        
        Self {
            id: config.id,
            inputs: InputPorts::new(),
            outputs,
            universes: config.universes,
            bind_address: config.bind_address,
            bind_port: config.bind_port,
            receiver: None,
            worker_handle: None,
            shutdown_tx: None,
            latest_data: None,
        }
    }
}

impl Node for SacnSourceNode {
    impl_node_basics!(SacnSourceNode, id, inputs, outputs);
    
    fn start(&mut self, ctx: &NodeContext) -> NodeResult<()> {
        let bind_addr = format!("{}:{}", self.bind_address, self.bind_port);
        
        // Create channels
        let (data_tx, data_rx) = mpsc::channel();
        let (shutdown_tx, shutdown_rx) = mpsc::channel();
        
        self.receiver = Some(data_rx);
        self.shutdown_tx = Some(shutdown_tx);
        
        // Spawn background receiver thread
        let universes = self.universes.clone();
        let handle = thread::Builder::new()
            .name(format!("sacn-recv-{}", self.id))
            .spawn(move || {
                sacn_receiver_thread(bind_addr, universes, data_tx, shutdown_rx);
            })
            .map_err(|e| NodeError::StartFailed(ctx.id.clone(), e.to_string()))?;
        
        self.worker_handle = Some(handle);
        
        info!(
            universes = ?self.universes,
            bind_port = %self.bind_port,
            "sacn_source_started"
        );
        
        Ok(())
    }
    
    fn pull(&mut self, _tick: &TickContext) -> NodeResult<()> {
        // Check for new data from receiver thread
        if let Some(ref rx) = self.receiver {
            // Drain all pending messages, keep latest
            while let Ok(data) = rx.try_recv() {
                // Convert bytes to normalized floats
                let floats: Vec<f32> = data.iter()
                    .map(|&b| b as f32 / 255.0)
                    .collect();
                self.latest_data = Some(floats);
            }
        }
        
        // Output latest data if available
        if let Some(ref data) = self.latest_data {
            let payload = MatrixPayload::from_slice(data);
            let frame = Frame::new(&self.id, payload);
            
            if let Some(out) = self.outputs.get("dmx") {
                out.write(frame);
            }
        }
        
        Ok(())
    }
    
    fn stop(&mut self, _ctx: &NodeContext) -> NodeResult<()> {
        // Signal shutdown
        if let Some(tx) = self.shutdown_tx.take() {
            let _ = tx.send(());
        }
        
        // Wait for worker
        if let Some(handle) = self.worker_handle.take() {
            let _ = handle.join();
        }
        
        info!("sacn_source_stopped");
        Ok(())
    }
}

/// Background thread that receives sACN packets.
fn sacn_receiver_thread(
    bind_addr: String,
    universes: Vec<u16>,
    data_tx: Sender<Vec<u8>>,
    shutdown_rx: Receiver<()>,
) {
    // Try to bind UDP socket
    let socket = match UdpSocket::bind(&bind_addr) {
        Ok(s) => s,
        Err(e) => {
            warn!(error = %e, addr = %bind_addr, "Failed to bind sACN socket");
            return;
        }
    };
    
    // Set non-blocking with timeout for shutdown checks
    if let Err(e) = socket.set_read_timeout(Some(std::time::Duration::from_millis(100))) {
        warn!(error = %e, "Failed to set socket timeout");
    }
    
    let mut buf = [0u8; 638]; // Max sACN packet size
    
    loop {
        // Check for shutdown
        if shutdown_rx.try_recv().is_ok() {
            break;
        }
        
        // Try to receive packet
        match socket.recv_from(&mut buf) {
            Ok((len, _addr)) => {
                if len >= 126 {
                    // Parse sACN packet (simplified - just extract DMX data)
                    // Full E1.31 parsing would validate headers, universe, etc.
                    if let Some(dmx_data) = parse_sacn_packet(&buf[..len], &universes) {
                        let _ = data_tx.send(dmx_data);
                    }
                }
            }
            Err(ref e) if e.kind() == std::io::ErrorKind::WouldBlock => {
                // Timeout, continue loop
            }
            Err(ref e) if e.kind() == std::io::ErrorKind::TimedOut => {
                // Timeout, continue loop
            }
            Err(e) => {
                debug!(error = %e, "sACN recv error");
            }
        }
    }
}

/// Parse sACN/E1.31 packet and extract DMX data.
/// Returns None if packet is invalid or for wrong universe.
fn parse_sacn_packet(data: &[u8], universes: &[u16]) -> Option<Vec<u8>> {
    // Minimal E1.31 validation
    // Root layer preamble
    if data.len() < 126 {
        return None;
    }
    
    // Check ACN packet identifier at offset 4
    const ACN_ID: &[u8] = b"ASC-E1.17\0\0\0";
    if data.len() < 16 || &data[4..16] != ACN_ID {
        return None;
    }
    
    // Universe is at offset 113-114 (big endian)
    let universe = u16::from_be_bytes([data[113], data[114]]);
    
    if !universes.contains(&universe) {
        return None;
    }
    
    // DMX data starts at offset 126
    let dmx_start = 126;
    let dmx_len = (data.len() - dmx_start).min(DMX_CHANNELS);
    
    Some(data[dmx_start..dmx_start + dmx_len].to_vec())
}

#[cfg(test)]
mod tests {
    use super::*;
    
    #[test]
    fn test_sacn_config_default() {
        let config = SacnSourceConfig::default();
        assert_eq!(config.universes, vec![1]);
        assert_eq!(config.bind_port, 5568);
    }
}
