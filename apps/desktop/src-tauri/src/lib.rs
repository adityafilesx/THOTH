// THOTH desktop shell. The `session_token` command is the first — and only —
// custom command: it hands the daemon-issued session token to the webview so
// the thin client can authenticate over HTTP/WS. Reviewed capability that
// implements the desktop side of the Phase 3 slice-2 auth token.

#[tauri::command]
fn session_token() -> Option<String> {
    if let Ok(t) = std::env::var("THOTH_SESSION_TOKEN") {
        if !t.is_empty() {
            return Some(t);
        }
    }
    let path = std::env::var("THOTH_SESSION_TOKEN_PATH")
        .unwrap_or_else(|_| "data/session.token".to_string());
    std::fs::read_to_string(path).ok().map(|s| s.trim().to_string())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![session_token])
        .run(tauri::generate_context!())
        .expect("error while running THOTH desktop");
}
