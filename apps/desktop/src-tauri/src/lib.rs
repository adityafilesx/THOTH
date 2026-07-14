// THOTH desktop shell: authenticated daemon token, native menu-bar presence,
// a non-focus-stealing voice overlay, and global push-to-talk. Computer
// interaction remains exclusively behind the daemon safety state machine.

mod managed_runtime;
mod presence;

use std::sync::Mutex;

use presence::PresencePayload;
use serde::Serialize;
use tauri::{
    menu::{Menu, MenuItem, PredefinedMenuItem},
    tray::TrayIconBuilder,
    Emitter, Manager, State, Wry,
};

struct PresenceStore(Mutex<PresencePayload>);
struct RuntimeAuth(Mutex<Option<String>>);

struct TrayItems {
    status: MenuItem<Wry>,
    task: MenuItem<Wry>,
    approval: MenuItem<Wry>,
    microphone: MenuItem<Wry>,
    planner: MenuItem<Wry>,
    stt: MenuItem<Wry>,
    tts: MenuItem<Wry>,
    accessibility: MenuItem<Wry>,
    privacy: MenuItem<Wry>,
}

impl TrayItems {
    fn update(&self, presence: &PresencePayload) -> tauri::Result<()> {
        let labels = presence.labels();
        self.status.set_text(labels.status)?;
        self.task.set_text(labels.task)?;
        self.approval.set_text(labels.approval)?;
        self.microphone.set_text(labels.microphone)?;
        self.planner.set_text(labels.planner)?;
        self.stt.set_text(labels.stt)?;
        self.tts.set_text(labels.tts)?;
        self.accessibility.set_text(labels.accessibility)?;
        self.privacy.set_text(labels.privacy)?;
        Ok(())
    }

    fn update_voice(&self, state: &str) -> tauri::Result<()> {
        let label = match state {
            "listening" => "Status: Listening",
            "transcribing" => "Status: Transcribing",
            "submitting" => "Status: Routing",
            "failed" => "Status: Failed",
            _ => "Status: Idle",
        };
        self.status.set_text(label)?;
        self.microphone.set_text(if state == "listening" {
            "Microphone: active"
        } else {
            "Microphone: enabled"
        })?;
        Ok(())
    }
}

#[derive(Clone, Serialize)]
struct PushToTalkEvent {
    state: &'static str,
}

#[tauri::command]
fn session_token(auth: State<'_, RuntimeAuth>) -> Option<String> {
    auth.0.lock().ok().and_then(|value| value.clone())
}

fn configured_session_token() -> Option<String> {
    if let Ok(token) = std::env::var("THOTH_SESSION_TOKEN") {
        if !token.is_empty() {
            return Some(token);
        }
    }
    let path = std::env::var("THOTH_SESSION_TOKEN_PATH")
        .unwrap_or_else(|_| "data/session.token".to_string());
    std::fs::read_to_string(path)
        .ok()
        .map(|value| value.trim().to_string())
}

#[tauri::command]
fn update_presence(
    presence: PresencePayload,
    store: State<'_, PresenceStore>,
    items: State<'_, TrayItems>,
) -> Result<(), String> {
    items.update(&presence).map_err(|error| error.to_string())?;
    *store.0.lock().map_err(|_| "presence lock poisoned")? = presence;
    Ok(())
}

#[tauri::command]
fn update_voice_state(state: String, items: State<'_, TrayItems>) -> Result<(), String> {
    items
        .update_voice(&state)
        .map_err(|error| error.to_string())
}

fn emit_push_to_talk(app: &tauri::AppHandle, state: &'static str) -> tauri::Result<()> {
    if let Some(overlay) = app.get_webview_window("voice-overlay") {
        overlay.show()?;
        overlay.emit("thoth://ptt", PushToTalkEvent { state })?;
    }
    Ok(())
}

#[tauri::command]
fn begin_push_to_talk(app: tauri::AppHandle) -> Result<(), String> {
    emit_push_to_talk(&app, "Pressed").map_err(|error| error.to_string())
}

#[tauri::command]
fn end_push_to_talk(app: tauri::AppHandle) -> Result<(), String> {
    emit_push_to_talk(&app, "Released").map_err(|error| error.to_string())
}

#[tauri::command]
fn set_voice_overlay_visible(app: tauri::AppHandle, visible: bool) -> Result<(), String> {
    if let Some(overlay) = app.get_webview_window("voice-overlay") {
        if visible {
            overlay.show().map_err(|error| error.to_string())?;
        } else {
            overlay.hide().map_err(|error| error.to_string())?;
        }
    }
    Ok(())
}

fn setup_tray(app: &tauri::App) -> tauri::Result<()> {
    let initial = PresencePayload::default();
    let labels = initial.labels();
    let listen = MenuItem::with_id(app, "listen", "Start listening", true, None::<&str>)?;
    let open = MenuItem::with_id(app, "open", "Open command center", true, None::<&str>)?;
    let status = MenuItem::with_id(app, "status", labels.status, false, None::<&str>)?;
    let task = MenuItem::with_id(app, "task", labels.task, false, None::<&str>)?;
    let approval = MenuItem::with_id(app, "approval", labels.approval, false, None::<&str>)?;
    let stop = MenuItem::with_id(app, "stop", "Stop", true, None::<&str>)?;
    let microphone = MenuItem::with_id(app, "microphone", labels.microphone, false, None::<&str>)?;
    let planner = MenuItem::with_id(app, "planner", labels.planner, false, None::<&str>)?;
    let stt = MenuItem::with_id(app, "stt", labels.stt, false, None::<&str>)?;
    let tts = MenuItem::with_id(app, "tts", labels.tts, false, None::<&str>)?;
    let accessibility = MenuItem::with_id(
        app,
        "accessibility",
        labels.accessibility,
        false,
        None::<&str>,
    )?;
    let privacy = MenuItem::with_id(app, "privacy", labels.privacy, false, None::<&str>)?;
    let quit = MenuItem::with_id(app, "quit", "Quit THOTH", true, None::<&str>)?;
    let separator_a = PredefinedMenuItem::separator(app)?;
    let separator_b = PredefinedMenuItem::separator(app)?;
    let separator_c = PredefinedMenuItem::separator(app)?;
    let menu = Menu::with_items(
        app,
        &[
            &listen,
            &open,
            &separator_a,
            &status,
            &task,
            &approval,
            &stop,
            &separator_b,
            &microphone,
            &planner,
            &stt,
            &tts,
            &accessibility,
            &privacy,
            &separator_c,
            &quit,
        ],
    )?;

    app.manage(PresenceStore(Mutex::new(initial)));
    app.manage(TrayItems {
        status,
        task,
        approval,
        microphone,
        planner,
        stt,
        tts,
        accessibility,
        privacy,
    });

    let mut tray = TrayIconBuilder::with_id("thoth")
        .menu(&menu)
        .show_menu_on_left_click(true)
        .tooltip("THOTH — local computer operator")
        .on_menu_event(|app, event| match event.id().as_ref() {
            "listen" => {
                let _ = emit_push_to_talk(app, "Pressed");
            }
            "open" => {
                if let Some(main) = app.get_webview_window("main") {
                    let _ = main.show();
                    let _ = main.set_focus();
                }
            }
            "stop" => {
                let _ = app.emit_to("main", "thoth://stop", ());
            }
            "quit" => app.exit(0),
            _ => {}
        });
    if let Some(icon) = app.default_window_icon() {
        tray = tray.icon(icon.clone()).icon_as_template(true);
    }
    tray.build(app)?;
    Ok(())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    #[cfg(desktop)]
    let shortcut_plugin = tauri_plugin_global_shortcut::Builder::new()
        .with_handler(|app, shortcut, event| {
            use tauri_plugin_global_shortcut::{Code, Modifiers, Shortcut, ShortcutState};
            let push_to_talk = Shortcut::new(Some(Modifiers::ALT), Code::Space);
            if shortcut == &push_to_talk {
                let state = match event.state() {
                    ShortcutState::Pressed => "Pressed",
                    ShortcutState::Released => "Released",
                };
                let _ = emit_push_to_talk(app, state);
            }
        })
        .build();

    let builder =
        tauri::Builder::default().manage(RuntimeAuth(Mutex::new(configured_session_token())));
    #[cfg(desktop)]
    let builder = builder.plugin(shortcut_plugin);

    let app = builder
        .setup(|app| {
            let manage_runtime = !cfg!(debug_assertions)
                || std::env::var("THOTH_MANAGED_RUNTIME").as_deref() == Ok("1");
            if manage_runtime {
                let executable = std::env::current_exe()?;
                let data_dir = app.path().app_data_dir()?;
                let runtime = managed_runtime::ManagedRuntime::start(&executable, data_dir)
                    .map_err(std::io::Error::other)?;
                *app.state::<RuntimeAuth>()
                    .0
                    .lock()
                    .map_err(|_| std::io::Error::other("runtime auth lock poisoned"))? =
                    Some(runtime.token().to_string());
                app.manage(runtime);
            }
            setup_tray(app)?;
            #[cfg(desktop)]
            {
                use tauri_plugin_global_shortcut::{Code, GlobalShortcutExt, Modifiers, Shortcut};
                app.global_shortcut()
                    .register(Shortcut::new(Some(Modifiers::ALT), Code::Space))?;
            }
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            session_token,
            update_presence,
            update_voice_state,
            begin_push_to_talk,
            end_push_to_talk,
            set_voice_overlay_visible
        ])
        .build(tauri::generate_context!())
        .expect("error while building THOTH desktop");
    app.run(|handle, event| {
        if matches!(
            event,
            tauri::RunEvent::ExitRequested { .. } | tauri::RunEvent::Exit
        ) {
            if let Some(runtime) = handle.try_state::<managed_runtime::ManagedRuntime>() {
                runtime.shutdown();
            }
        }
    });
}
