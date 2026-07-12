//! Minimal raw-HCI TPMS receiver used to benchmark the native Venus runtime.
//!
//! BlueZ remains responsible for enabling LE discovery. This process only reads
//! the resulting HCI advertising reports, discards non-TPMS payloads, and emits
//! parsed readings as JSON lines.

#[cfg(any(target_os = "linux", feature = "hci-test"))]
mod linux;

#[cfg(target_os = "linux")]
fn main() {
    if let Err(error) = linux::run() {
        eprintln!("{error}");
        std::process::exit(1);
    }
}

#[cfg(not(target_os = "linux"))]
fn main() {
    eprintln!("venus-tpms-hci-monitor only runs on Linux with BlueZ HCI sockets");
    std::process::exit(2);
}
