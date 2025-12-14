//! DDP (Distributed Display Protocol) sink node for LED pixel data.
//!
//! Transmits RGB pixel data as DDP packets to network devices (LED controllers, WLED, etc.).
//! DDP is optimized for high pixel counts with up to 480 RGB pixels per packet.
//!
//! Protocol reference: http://www.3waylabs.com/ddp/

use std::io;
use std::net::UdpSocket;
use std::sync::mpsc::{self, Sender, Receiver};
use std::thread::{self, JoinHandle};

use rasl_core::frame::Frame;
use rasl_core::node::{Node, NodeContext, NodeResult, NodeError};
use rasl_core::payload::{MatrixPayload, Payload};
use rasl_core::port::{InputPort, InputPorts, OutputPorts, PortSpec};
use rasl_core::tick::TickContext;
use rasl_core::impl_node_basics;
use tracing::{info, warn, error};

// DDP protocol constants
const DDP_PORT: u16 = 4048;
const DDP_HEADER_LEN: usize = 10;
const DDP_MAX_DATALEN: usize = 1440; // Up to 480 RGB pixels per packet

// DDP flags
const DDP_VER1: u8 = 0x40;
const DDP_PUSH: u8 = 0x01;
const DDP_DATATYPE_RGB: u8 = 0x00;
const DDP_DEFAULT_DEST_ID: u8 = 0x01;

/// Configuration for DDP sink node.
#[derive(Debug, Clone)]
pub struct DdpSinkConfig {
    pub id: String,
    pub target: String,
    pub fps: f64,
    pub input_port: String,
    pub max_count: Option<usize>,
}

impl Default for DdpSinkConfig {
    fn default() -> Self {
        Self {
            id: "ddp".to_string(),
            target: "127.0.0.1".to_string(),
            fps: 20.0,
            input_port: "pixels".to_string(),
            max_count: None,
        }
    }
}

/// Message sent to background DDP sender thread.
enum DdpMessage {
    Send(Vec<u8>),
    Shutdown,
}

/// DDP sink node that transmits RGB pixel data via UDP.
pub struct DdpSinkNode {
    id: String,
    inputs: InputPorts,
    outputs: OutputPorts,
    
    target: String,
    fps: f64,
    input_port: String,
    max_count: Option<usize>,
    
    // Background sender thread
    sender: Option<Sender<DdpMessage>>,
    worker_handle: Option<JoinHandle<()>>,
    
    // Stats
    frames_sent: u64,
    frames_dropped: u64,
}

impl DdpSinkNode {
    pub fn new(config: DdpSinkConfig) -> Self {
        let mut inputs = InputPorts::new();
        inputs.add(InputPort::new(PortSpec::new(&config.input_port, "color")));
        
        Self {
            id: config.id,
            inputs,
            outputs: OutputPorts::new(),
            target: config.target,
            fps: config.fps,
            input_port: config.input_port,
            max_count: config.max_count,
            sender: None,
            worker_handle: None,
            frames_sent: 0,
            frames_dropped: 0,
        }
    }
    
    /// Parse fps string (e.g., "20hz", "20", "50ms") to Hz.
    pub fn parse_fps(fps_str: &str) -> Option<f64> {
        let s = fps_str.trim().to_lowercase();
        
        if s.ends_with("hz") {
            s[..s.len()-2].trim().parse().ok()
        } else if s.ends_with("ms") {
            let ms: f64 = s[..s.len()-2].trim().parse().ok()?;
            Some(1000.0 / ms)
        } else {
            s.parse().ok()
        }
    }
}

impl Node for DdpSinkNode {
    impl_node_basics!(DdpSinkNode, id, inputs, outputs);
    
    fn start(&mut self, ctx: &NodeContext) -> NodeResult<()> {
        let target = self.target.clone();
        let target_addr = format!("{}:{}", target, DDP_PORT);
        
        // Create channel for sending frames to background thread
        let (tx, rx): (Sender<DdpMessage>, Receiver<DdpMessage>) = mpsc::channel();
        self.sender = Some(tx);
        
        // Spawn background sender thread
        let handle = thread::Builder::new()
            .name(format!("ddp-send-{}", target))
            .spawn(move || {
                ddp_sender_thread(target_addr, rx);
            })
            .map_err(|e| NodeError::StartFailed(ctx.id.clone(), e.to_string()))?;
        
        self.worker_handle = Some(handle);
        
        info!(
            target = %self.target,
            fps = %self.fps,
            input_port = %self.input_port,
            "ddp_sink_started"
        );
        
        Ok(())
    }
    
    fn pull(&mut self, _tick: &TickContext) -> NodeResult<()> {
        let sender = match &self.sender {
            Some(s) => s,
            None => return Ok(()),
        };
        
        // Read from input port
        let frame = match self.inputs.get(&self.input_port).and_then(|p| p.read()) {
            Some(f) => f,
            None => return Ok(()),
        };
        
        let payload = &frame.payload;
        let data = payload.as_array();
        
        // Flatten to 1D and convert to bytes
        let flat: Vec<f32> = data.iter().cloned().collect();
        let mut byte_data: Vec<u8> = flat.iter()
            .map(|&v| (v.clamp(0.0, 1.0) * 255.0) as u8)
            .collect();
        
        // Apply max_count limit
        if let Some(max_count) = self.max_count {
            let channels = data.ncols();
            let max_len = max_count * channels;
            if byte_data.len() > max_len {
                byte_data.truncate(max_len);
            }
        }
        
        // Send to background thread
        // Note: std::sync::mpsc doesn't have try_send, so we use send which may block briefly
        // For true non-blocking, we'd need crossbeam or tokio channels
        match sender.send(DdpMessage::Send(byte_data)) {
            Ok(_) => self.frames_sent += 1,
            Err(_) => {
                self.frames_dropped += 1;
                warn!("DDP sender thread disconnected");
            }
        }
        
        Ok(())
    }
    
    fn stop(&mut self, _ctx: &NodeContext) -> NodeResult<()> {
        // Signal shutdown
        if let Some(sender) = self.sender.take() {
            let _ = sender.send(DdpMessage::Shutdown);
        }
        
        // Wait for worker to finish
        if let Some(handle) = self.worker_handle.take() {
            let _ = handle.join();
        }
        
        info!(
            target = %self.target,
            frames_sent = %self.frames_sent,
            frames_dropped = %self.frames_dropped,
            "ddp_sink_stopped"
        );
        
        Ok(())
    }
    
    fn pull_rate(&self) -> Option<f64> {
        Some(self.fps)
    }
}

/// Background thread that sends DDP packets.
fn ddp_sender_thread(target_addr: String, rx: Receiver<DdpMessage>) {
    let socket = match UdpSocket::bind("0.0.0.0:0") {
        Ok(s) => s,
        Err(e) => {
            error!(error = %e, "Failed to bind UDP socket for DDP");
            return;
        }
    };
    
    let mut sequence: u8 = 0;
    
    loop {
        match rx.recv() {
            Ok(DdpMessage::Send(data)) => {
                if let Err(e) = send_ddp_packets(&socket, &target_addr, &data, &mut sequence) {
                    warn!(error = %e, target = %target_addr, "DDP send error");
                }
            }
            Ok(DdpMessage::Shutdown) | Err(_) => {
                break;
            }
        }
    }
}

/// Send data as DDP packets (splitting if necessary).
fn send_ddp_packets(
    socket: &UdpSocket,
    target: &str,
    data: &[u8],
    sequence: &mut u8,
) -> io::Result<()> {
    if data.is_empty() {
        return Ok(());
    }
    
    let num_packets = (data.len() + DDP_MAX_DATALEN - 1) / DDP_MAX_DATALEN;
    
    for i in 0..num_packets {
        let byte_offset = i * DDP_MAX_DATALEN;
        let chunk_end = (byte_offset + DDP_MAX_DATALEN).min(data.len());
        let chunk = &data[byte_offset..chunk_end];
        let is_last = i == num_packets - 1;
        
        *sequence = (*sequence % 15) + 1;
        
        send_ddp_packet(socket, target, *sequence, byte_offset as u32, chunk, is_last)?;
    }
    
    Ok(())
}

/// Send a single DDP packet.
fn send_ddp_packet(
    socket: &UdpSocket,
    target: &str,
    sequence: u8,
    byte_offset: u32,
    data: &[u8],
    is_last: bool,
) -> io::Result<()> {
    let flags = DDP_VER1 | if is_last { DDP_PUSH } else { 0 };
    let data_len = data.len() as u16;
    
    // Build header (10 bytes)
    let mut packet = Vec::with_capacity(DDP_HEADER_LEN + data.len());
    packet.push(flags);
    packet.push(sequence & 0x0F);
    packet.push(DDP_DATATYPE_RGB);
    packet.push(DDP_DEFAULT_DEST_ID);
    packet.extend_from_slice(&byte_offset.to_be_bytes());
    packet.extend_from_slice(&data_len.to_be_bytes());
    packet.extend_from_slice(data);
    
    socket.send_to(&packet, target)?;
    
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    
    #[test]
    fn test_parse_fps() {
        assert_eq!(DdpSinkNode::parse_fps("20hz"), Some(20.0));
        assert_eq!(DdpSinkNode::parse_fps("20"), Some(20.0));
        assert_eq!(DdpSinkNode::parse_fps("50ms"), Some(20.0));
        assert_eq!(DdpSinkNode::parse_fps("100ms"), Some(10.0));
        assert_eq!(DdpSinkNode::parse_fps("invalid"), None);
    }
    
    #[test]
    fn test_ddp_config_default() {
        let config = DdpSinkConfig::default();
        assert_eq!(config.fps, 20.0);
        assert_eq!(config.input_port, "pixels");
    }
}
