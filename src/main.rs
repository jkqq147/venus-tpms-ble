#[cfg(target_os = "linux")]
fn main() -> Result<(), Box<dyn std::error::Error>> {
    venus_tpms_ble::run_service()
}

#[cfg(not(target_os = "linux"))]
fn main() {
    eprintln!("venus-tpms-ble only runs on Linux");
    std::process::exit(2);
}
