// THOTH desktop shell. Deliberately minimal: the desktop app is a thin
// client over the daemon's HTTP/WS API, so no custom Tauri commands exist
// in Phases 0-2. IPC surface stays closed until a capability review adds one.

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .run(tauri::generate_context!())
        .expect("error while running THOTH desktop");
}
