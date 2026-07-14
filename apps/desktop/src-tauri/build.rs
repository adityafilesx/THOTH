#[cfg(unix)]
fn prepare_debug_placeholders() {
    use std::os::unix::fs::PermissionsExt;
    use std::path::Path;

    if std::env::var("PROFILE").as_deref() == Ok("release") {
        return;
    }
    let binary = Path::new("resources/runtime/thoth-daemon");
    std::fs::create_dir_all(binary.parent().expect("binary parent"))
        .expect("create debug sidecar directory");
    std::fs::write(&binary, b"#!/bin/sh\nexit 1\n").expect("write inert debug sidecar");
    let mut permissions = std::fs::metadata(&binary)
        .expect("debug sidecar metadata")
        .permissions();
    permissions.set_mode(0o755);
    std::fs::set_permissions(&binary, permissions).expect("set debug sidecar mode");

    for directory in [
        "resources/THOTH Accessibility Helper.app",
        "resources/models",
    ] {
        std::fs::create_dir_all(directory).expect("create debug resource placeholder");
    }
    std::fs::write("resources/runtime-manifest.json", b"{}\n")
        .expect("write debug manifest placeholder");
}

fn main() {
    #[cfg(unix)]
    prepare_debug_placeholders();
    tauri_build::build()
}
