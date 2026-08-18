use serde::Deserialize;
use sha2::{Digest, Sha256};
use std::{
    collections::BTreeMap,
    fs::{File, OpenOptions},
    io::{Read, Write},
    net::{SocketAddr, TcpListener, TcpStream},
    os::unix::fs::OpenOptionsExt,
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    sync::Mutex,
    thread,
    time::{Duration, Instant},
};
use uuid::Uuid;

#[derive(Debug, PartialEq, Eq)]
pub(crate) struct RuntimeAssetPaths {
    pub(crate) daemon: PathBuf,
    pub(crate) helper_app: PathBuf,
    pub(crate) helper_executable: PathBuf,
    pub(crate) whisper_executable: PathBuf,
    pub(crate) whisper_model: PathBuf,
    pub(crate) manifest: PathBuf,
}

#[derive(Debug, PartialEq, Eq)]
pub(crate) struct RuntimeLayout {
    pub(crate) assets: RuntimeAssetPaths,
    pub(crate) data_dir: PathBuf,
    pub(crate) token_path: PathBuf,
    pub(crate) database_path: PathBuf,
    pub(crate) log_dir: PathBuf,
}

impl RuntimeLayout {
    pub(crate) fn from_packaged_executable(
        executable: &Path,
        data_dir: PathBuf,
    ) -> Result<Self, String> {
        let macos_dir = executable
            .parent()
            .ok_or_else(|| "desktop executable has no parent directory".to_string())?;
        if macos_dir.file_name().and_then(|value| value.to_str()) != Some("MacOS") {
            return Err("desktop executable is not inside a macOS app bundle".to_string());
        }
        let contents_dir = macos_dir
            .parent()
            .ok_or_else(|| "macOS directory has no app Contents parent".to_string())?;
        if contents_dir.file_name().and_then(|value| value.to_str()) != Some("Contents") {
            return Err("desktop executable is not inside an app Contents directory".to_string());
        }
        let resources = contents_dir.join("Resources");
        let helper_app = resources.join("OmniMac Accessibility Helper.app");
        let assets = RuntimeAssetPaths {
            daemon: resources.join("runtime/omnimac-daemon"),
            helper_executable: helper_app.join("Contents/MacOS/OmniMacAXHelper"),
            helper_app,
            whisper_executable: resources.join("runtime/whisper-cli"),
            whisper_model: resources.join("models/ggml-base.en.bin"),
            manifest: resources.join("runtime-manifest.json"),
        };
        Ok(Self {
            token_path: data_dir.join("session.token"),
            database_path: data_dir.join("omnimac.db"),
            log_dir: data_dir.join("logs"),
            data_dir,
            assets,
        })
    }
}

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct RuntimeAsset {
    relative_path: String,
    pub(crate) sha256: String,
    bytes: u64,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct RuntimeManifest {
    schema_version: u32,
    daemon: RuntimeAsset,
    helper: RuntimeAsset,
    whisper_executable: RuntimeAsset,
    pub(crate) whisper_model: RuntimeAsset,
}

impl RuntimeManifest {
    pub(crate) fn load(path: &Path) -> Result<Self, String> {
        let bytes = std::fs::read(path)
            .map_err(|error| format!("cannot read runtime manifest: {error}"))?;
        let manifest: Self = serde_json::from_slice(&bytes)
            .map_err(|error| format!("invalid runtime manifest: {error}"))?;
        if manifest.schema_version != 1 {
            return Err(format!(
                "unsupported runtime manifest schema {}",
                manifest.schema_version
            ));
        }
        Ok(manifest)
    }

    pub(crate) fn validate(&self, layout: &RuntimeLayout) -> Result<(), String> {
        self.validate_asset(
            "daemon",
            &self.daemon,
            "runtime/omnimac-daemon",
            &layout.assets.daemon,
        )?;
        self.validate_asset(
            "Accessibility helper",
            &self.helper,
            "OmniMac Accessibility Helper.app/Contents/MacOS/OmniMacAXHelper",
            &layout.assets.helper_executable,
        )?;
        self.validate_asset(
            "whisper executable",
            &self.whisper_executable,
            "runtime/whisper-cli",
            &layout.assets.whisper_executable,
        )?;
        self.validate_asset(
            "whisper model",
            &self.whisper_model,
            "models/ggml-base.en.bin",
            &layout.assets.whisper_model,
        )?;
        Ok(())
    }

    pub(crate) fn daemon_environment(
        &self,
        layout: &RuntimeLayout,
        token: &str,
    ) -> BTreeMap<String, String> {
        BTreeMap::from([
            ("OmniMac_DB_PATH".into(), path_text(&layout.database_path)),
            ("OmniMac_LOG_DIR".into(), path_text(&layout.log_dir)),
            ("OmniMac_SESSION_TOKEN".into(), token.to_string()),
            (
                "OmniMac_SESSION_TOKEN_PATH".into(),
                path_text(&layout.token_path),
            ),
            ("OmniMac_PLANNER".into(), "local".into()),
            ("OmniMac_INFERENCE_PROVIDER".into(), "llama.cpp".into()),
            ("OmniMac_INFERENCE_MODEL".into(), "qwen3:4b".into()),
            (
                "OmniMac_INFERENCE_ENDPOINT".into(),
                "http://127.0.0.1:11434".into(),
            ),
            ("OmniMac_NETWORK_ISOLATION".into(), "true".into()),
            (
                "OmniMac_WHISPER_EXECUTABLE".into(),
                path_text(&layout.assets.whisper_executable),
            ),
            (
                "OmniMac_WHISPER_MODEL_PATH".into(),
                path_text(&layout.assets.whisper_model),
            ),
            (
                "OmniMac_WHISPER_EXECUTABLE_SHA256".into(),
                self.whisper_executable.sha256.clone(),
            ),
            (
                "OmniMac_WHISPER_MODEL_SHA256".into(),
                self.whisper_model.sha256.clone(),
            ),
        ])
    }

    fn validate_asset(
        &self,
        label: &str,
        asset: &RuntimeAsset,
        expected_relative_path: &str,
        path: &Path,
    ) -> Result<(), String> {
        if asset.relative_path != expected_relative_path {
            return Err(format!("{label} manifest path is not authoritative"));
        }
        let metadata =
            std::fs::metadata(path).map_err(|error| format!("{label} is unavailable: {error}"))?;
        if metadata.len() != asset.bytes {
            return Err(format!("{label} size mismatch"));
        }
        let actual = sha256(path)?;
        if actual != asset.sha256 {
            return Err(format!("{label} SHA-256 mismatch"));
        }
        Ok(())
    }

    #[cfg(test)]
    fn for_test_layout(layout: &RuntimeLayout) -> Result<Self, String> {
        fn asset(path: &Path, relative_path: &str) -> Result<RuntimeAsset, String> {
            Ok(RuntimeAsset {
                relative_path: relative_path.to_string(),
                sha256: sha256(path)?,
                bytes: std::fs::metadata(path)
                    .map_err(|error| error.to_string())?
                    .len(),
            })
        }
        Ok(Self {
            schema_version: 1,
            daemon: asset(&layout.assets.daemon, "runtime/omnimac-daemon")?,
            helper: asset(
                &layout.assets.helper_executable,
                "OmniMac Accessibility Helper.app/Contents/MacOS/OmniMacAXHelper",
            )?,
            whisper_executable: asset(&layout.assets.whisper_executable, "runtime/whisper-cli")?,
            whisper_model: asset(&layout.assets.whisper_model, "models/ggml-base.en.bin")?,
        })
    }
}

fn sha256(path: &Path) -> Result<String, String> {
    let mut file = File::open(path).map_err(|error| error.to_string())?;
    let mut digest = Sha256::new();
    let mut buffer = [0_u8; 64 * 1024];
    loop {
        let count = file.read(&mut buffer).map_err(|error| error.to_string())?;
        if count == 0 {
            break;
        }
        digest.update(&buffer[..count]);
    }
    Ok(format!("{:x}", digest.finalize()))
}

fn path_text(path: &Path) -> String {
    path.to_string_lossy().into_owned()
}

pub(crate) fn write_private_token(path: &Path, token: &str) -> Result<(), String> {
    let parent = path
        .parent()
        .ok_or_else(|| "session token path has no parent directory".to_string())?;
    std::fs::create_dir_all(parent)
        .map_err(|error| format!("cannot create session token directory: {error}"))?;
    let temporary = parent.join(format!(".session-token-{}.tmp", Uuid::new_v4()));
    let result = (|| {
        let mut file = OpenOptions::new()
            .create_new(true)
            .write(true)
            .mode(0o600)
            .open(&temporary)
            .map_err(|error| format!("cannot create private session token: {error}"))?;
        file.write_all(token.as_bytes())
            .map_err(|error| format!("cannot write session token: {error}"))?;
        file.sync_all()
            .map_err(|error| format!("cannot sync session token: {error}"))?;
        std::fs::rename(&temporary, path)
            .map_err(|error| format!("cannot install session token: {error}"))?;
        Ok(())
    })();
    if result.is_err() {
        let _ = std::fs::remove_file(&temporary);
    }
    result
}

pub(crate) struct ManagedRuntime {
    daemon: Mutex<Option<Child>>,
    helper: Mutex<Option<Child>>,
    token: String,
}

impl ManagedRuntime {
    pub(crate) fn start(executable: &Path, data_dir: PathBuf) -> Result<Self, String> {
        let layout = RuntimeLayout::from_packaged_executable(executable, data_dir)?;
        let manifest = RuntimeManifest::load(&layout.assets.manifest)?;
        manifest.validate(&layout)?;
        ensure_port_available(SocketAddr::from(([127, 0, 0, 1], 7710)))?;
        std::fs::create_dir_all(&layout.log_dir)
            .map_err(|error| format!("cannot create runtime log directory: {error}"))?;

        let token = format!("{}{}", Uuid::new_v4().simple(), Uuid::new_v4().simple());
        write_private_token(&layout.token_path, &token)?;

        let helper_log = open_private_log(&layout.log_dir.join("ax-helper-sidecar.log"))?;
        let parent_pid = std::process::id().to_string();
        let mut helper_command = Command::new(&layout.assets.helper_executable);
        helper_command
            .env_clear()
            .env("OmniMac_DESKTOP_PARENT_PID", &parent_pid)
            .env("PATH", "/usr/bin:/bin:/usr/sbin:/sbin")
            .stdin(Stdio::null())
            .stdout(Stdio::from(
                helper_log
                    .try_clone()
                    .map_err(|error| format!("cannot clone helper log: {error}"))?,
            ))
            .stderr(Stdio::from(helper_log));
        for name in ["HOME", "TMPDIR", "LANG"] {
            if let Some(value) = std::env::var_os(name) {
                helper_command.env(name, value);
            }
        }
        let mut helper = helper_command
            .spawn()
            .map_err(|error| format!("cannot start Accessibility helper: {error}"))?;

        let daemon_log = open_private_log(&layout.log_dir.join("daemon-sidecar.log"))?;
        let environment = manifest.daemon_environment(&layout, &token);
        let mut command = Command::new(&layout.assets.daemon);
        command
            .env_clear()
            .envs(environment)
            .env("OmniMac_DESKTOP_PARENT_PID", &parent_pid)
            .env("PATH", "/usr/bin:/bin:/usr/sbin:/sbin")
            .stdin(Stdio::null())
            .stdout(Stdio::from(
                daemon_log
                    .try_clone()
                    .map_err(|error| format!("cannot clone daemon log: {error}"))?,
            ))
            .stderr(Stdio::from(daemon_log));
        for name in ["HOME", "TMPDIR", "LANG"] {
            if let Some(value) = std::env::var_os(name) {
                command.env(name, value);
            }
        }
        let mut daemon = match command.spawn() {
            Ok(child) => child,
            Err(error) => {
                terminate_child(&mut helper);
                return Err(format!("cannot start local daemon: {error}"));
            }
        };

        if let Err(error) = wait_for_authenticated_daemon(&mut daemon, &token) {
            terminate_child(&mut daemon);
            terminate_child(&mut helper);
            return Err(error);
        }

        Ok(Self {
            daemon: Mutex::new(Some(daemon)),
            helper: Mutex::new(Some(helper)),
            token,
        })
    }

    pub(crate) fn token(&self) -> &str {
        &self.token
    }

    pub(crate) fn shutdown(&self) {
        if let Ok(mut daemon) = self.daemon.lock() {
            if let Some(mut child) = daemon.take() {
                terminate_child(&mut child);
            }
        }
        if let Ok(mut helper) = self.helper.lock() {
            if let Some(mut child) = helper.take() {
                terminate_child(&mut child);
            }
        }
    }
}

fn ensure_port_available(address: SocketAddr) -> Result<(), String> {
    let listener = TcpListener::bind(address)
        .map_err(|error| format!("local daemon address {address} is unavailable: {error}"))?;
    drop(listener);
    Ok(())
}

impl Drop for ManagedRuntime {
    fn drop(&mut self) {
        self.shutdown();
    }
}

fn open_private_log(path: &Path) -> Result<File, String> {
    OpenOptions::new()
        .create(true)
        .append(true)
        .mode(0o600)
        .open(path)
        .map_err(|error| format!("cannot open private sidecar log: {error}"))
}

fn wait_for_authenticated_daemon(child: &mut Child, token: &str) -> Result<(), String> {
    let deadline = Instant::now() + Duration::from_secs(20);
    while Instant::now() < deadline {
        if let Some(status) = child
            .try_wait()
            .map_err(|error| format!("cannot inspect daemon process: {error}"))?
        {
            return Err(format!("local daemon exited before readiness: {status}"));
        }
        if authenticated_runtime_probe(token) {
            return Ok(());
        }
        thread::sleep(Duration::from_millis(100));
    }
    Err("local daemon did not become ready within 20 seconds".to_string())
}

fn authenticated_runtime_probe(token: &str) -> bool {
    let address = SocketAddr::from(([127, 0, 0, 1], 7710));
    let Ok(mut stream) = TcpStream::connect_timeout(&address, Duration::from_millis(200)) else {
        return false;
    };
    let _ = stream.set_read_timeout(Some(Duration::from_millis(500)));
    let request = format!(
        "GET /api/runtime HTTP/1.1\r\nHost: 127.0.0.1:7710\r\nAuthorization: Bearer {token}\r\nConnection: close\r\n\r\n"
    );
    if stream.write_all(request.as_bytes()).is_err() {
        return false;
    }
    let mut response = [0_u8; 64];
    let Ok(count) = stream.read(&mut response) else {
        return false;
    };
    response[..count].starts_with(b"HTTP/1.1 200") || response[..count].starts_with(b"HTTP/1.0 200")
}

pub(crate) fn terminate_child(child: &mut Child) {
    if matches!(child.try_wait(), Ok(Some(_))) {
        let _ = child.wait();
        return;
    }
    let pid = child.id() as libc::pid_t;
    // SAFETY: pid comes directly from this owned Child; SIGTERM requests its
    // normal cleanup path and does not access memory.
    unsafe {
        libc::kill(pid, libc::SIGTERM);
    }
    let deadline = Instant::now() + Duration::from_secs(2);
    while Instant::now() < deadline {
        if matches!(child.try_wait(), Ok(Some(_))) {
            let _ = child.wait();
            return;
        }
        thread::sleep(Duration::from_millis(20));
    }
    let _ = child.kill();
    let _ = child.wait();
}

#[cfg(test)]
mod tests {
    use super::{
        ensure_port_available, terminate_child, write_private_token, RuntimeAssetPaths,
        RuntimeLayout, RuntimeManifest,
    };
    use std::{
        fs,
        net::{SocketAddr, TcpListener},
        os::unix::fs::PermissionsExt,
        path::PathBuf,
        process::Command,
    };

    #[test]
    fn packaged_layout_resolves_sidecar_and_sealed_resources() {
        let executable = PathBuf::from("/Applications/OmniMac.app/Contents/MacOS/omnimac-desktop");
        let data_dir = PathBuf::from("/Users/test/Library/Application Support/OmniMac");

        let layout = RuntimeLayout::from_packaged_executable(&executable, data_dir.clone())
            .expect("valid app bundle layout");

        assert_eq!(
            layout.assets,
            RuntimeAssetPaths {
                daemon: PathBuf::from(
                    "/Applications/OmniMac.app/Contents/Resources/runtime/omnimac-daemon"
                ),
                helper_app: PathBuf::from(
                    "/Applications/OmniMac.app/Contents/Resources/OmniMac Accessibility Helper.app"
                ),
                helper_executable: PathBuf::from(
                    "/Applications/OmniMac.app/Contents/Resources/OmniMac Accessibility Helper.app/Contents/MacOS/OmniMacAXHelper"
                ),
                whisper_executable: PathBuf::from(
                    "/Applications/OmniMac.app/Contents/Resources/runtime/whisper-cli"
                ),
                whisper_model: PathBuf::from(
                    "/Applications/OmniMac.app/Contents/Resources/models/ggml-base.en.bin"
                ),
                manifest: PathBuf::from(
                    "/Applications/OmniMac.app/Contents/Resources/runtime-manifest.json"
                ),
            }
        );
        assert_eq!(layout.data_dir, data_dir);
        assert_eq!(layout.token_path, layout.data_dir.join("session.token"));
        assert_eq!(layout.database_path, layout.data_dir.join("omnimac.db"));
        assert_eq!(layout.log_dir, layout.data_dir.join("logs"));
    }

    #[test]
    fn non_bundle_executable_fails_closed() {
        let result = RuntimeLayout::from_packaged_executable(
            &PathBuf::from("/tmp/omnimac-desktop"),
            PathBuf::from("/tmp/data"),
        );
        assert!(result.is_err());
    }

    #[test]
    fn manifest_validation_detects_asset_mutation_and_builds_local_only_environment() {
        let root = std::env::temp_dir().join(format!(
            "omnimac-runtime-manifest-test-{}",
            std::process::id()
        ));
        let executable = root.join("OmniMac.app/Contents/MacOS/omnimac-desktop");
        let data_dir = root.join("data");
        fs::create_dir_all(executable.parent().expect("executable parent"))
            .expect("create macOS directory");
        let layout = RuntimeLayout::from_packaged_executable(&executable, data_dir)
            .expect("valid bundle layout");
        fs::create_dir_all(
            layout
                .assets
                .helper_executable
                .parent()
                .expect("helper parent"),
        )
        .expect("create helper directory");
        fs::create_dir_all(
            layout
                .assets
                .whisper_executable
                .parent()
                .expect("whisper parent"),
        )
        .expect("create runtime directory");
        fs::create_dir_all(layout.assets.whisper_model.parent().expect("model parent"))
            .expect("create model directory");
        fs::write(&layout.assets.daemon, b"daemon").expect("write daemon");
        fs::write(&layout.assets.helper_executable, b"helper").expect("write helper");
        fs::write(&layout.assets.whisper_executable, b"whisper").expect("write whisper");
        fs::write(&layout.assets.whisper_model, b"model").expect("write model");

        let manifest = RuntimeManifest::for_test_layout(&layout).expect("create manifest");
        manifest.validate(&layout).expect("assets match manifest");
        let environment = manifest.daemon_environment(&layout, "private-token");
        assert_eq!(environment["OmniMac_NETWORK_ISOLATION"], "true");
        assert_eq!(environment["OmniMac_PLANNER"], "local");
        assert_eq!(environment["OmniMac_SESSION_TOKEN"], "private-token");
        assert_eq!(
            environment["OmniMac_WHISPER_MODEL_SHA256"],
            manifest.whisper_model.sha256
        );

        fs::write(&layout.assets.whisper_model, b"other").expect("mutate model");
        let error = manifest
            .validate(&layout)
            .expect_err("mutated asset must fail");
        assert!(error.contains("whisper model SHA-256 mismatch"));
        fs::remove_dir_all(root).expect("remove test directory");
    }

    #[test]
    fn session_token_file_is_private_and_replaced_atomically() {
        let root =
            std::env::temp_dir().join(format!("omnimac-runtime-token-test-{}", std::process::id()));
        let token_path = root.join("session.token");
        write_private_token(&token_path, "first-token").expect("write first token");
        write_private_token(&token_path, "second-token").expect("replace token");

        assert_eq!(
            fs::read_to_string(&token_path).expect("read token"),
            "second-token"
        );
        let mode = fs::metadata(&token_path)
            .expect("token metadata")
            .permissions()
            .mode()
            & 0o777;
        assert_eq!(mode, 0o600);
        fs::remove_dir_all(root).expect("remove test directory");
    }

    #[test]
    fn managed_child_is_terminated_and_reaped() {
        let mut child = Command::new("/bin/sleep")
            .arg("30")
            .spawn()
            .expect("spawn sleep fixture");
        terminate_child(&mut child);
        assert!(child.try_wait().expect("query child").is_some());
    }

    #[test]
    fn occupied_daemon_address_fails_before_runtime_start() {
        let listener = TcpListener::bind(("127.0.0.1", 0)).expect("bind fixture listener");
        let address: SocketAddr = listener.local_addr().expect("fixture address");

        let error = ensure_port_available(address).expect_err("occupied port must fail");

        assert!(error.contains("local daemon address"));
    }

    #[test]
    fn packaged_app_declares_bounded_microphone_use() {
        let info_plist = include_str!("../Info.plist");

        assert!(info_plist.contains("NSMicrophoneUsageDescription"));
        assert!(info_plist.contains("push-to-talk"));
        assert!(info_plist.contains("locally"));
    }
}
