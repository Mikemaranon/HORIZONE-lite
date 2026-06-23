#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::{
    env, fs,
    net::{TcpListener, TcpStream},
    path::PathBuf,
    process::{Child, Command, Stdio},
    sync::{Arc, Mutex},
    thread,
    time::{Duration, Instant},
};

use tauri::{Manager, RunEvent, WebviewUrl, WebviewWindowBuilder};
use tauri_plugin_opener::OpenerExt;

const SINGLE_WEBVIEW_NAVIGATION_SCRIPT: &str = r#"
(() => {
    const navigateInCurrentWebview = (url) => {
        if (url !== undefined && url !== null && String(url)) {
            window.location.assign(String(url));
        }
        return null;
    };

    window.open = navigateInCurrentWebview;

    document.addEventListener("click", (event) => {
        const anchor = event.composedPath().find(
            (element) => element instanceof HTMLAnchorElement && element.href
        );
        if (!anchor) {
            return;
        }

        const destination = new URL(anchor.href, window.location.href);
        const opensNewContext = Boolean(
            anchor.target && anchor.target.toLowerCase() !== "_self"
        );
        if (destination.origin !== window.location.origin || opensNewContext) {
            event.preventDefault();
            navigateInCurrentWebview(destination.href);
        }
    }, true);
})();
"#;

#[derive(Debug, PartialEq, Eq)]
enum NavigationDecision {
    AllowInternal,
    OpenExternal,
    Deny,
}

struct BackendProcess(Arc<Mutex<Option<Child>>>);

impl Drop for BackendProcess {
    fn drop(&mut self) {
        if let Ok(mut child_slot) = self.0.lock() {
            if let Some(mut child) = child_slot.take() {
                let _ = child.kill();
                let _ = child.wait();
            }
        }
    }
}

fn main() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .setup(|app| {
            let port = find_available_port()?;
            let data_dir = app.path().app_data_dir()?;
            let backend = start_backend(app.handle(), port, data_dir)?;
            let backend_process = Arc::new(Mutex::new(Some(backend)));
            app.manage(BackendProcess(Arc::clone(&backend_process)));

            wait_for_backend(port)?;
            let url = format!("http://127.0.0.1:{port}/").parse().unwrap();
            let navigation_app = app.handle().clone();
            let new_window_app = app.handle().clone();
            WebviewWindowBuilder::new(app, "main", WebviewUrl::External(url))
                .title("HORIZONE")
                .inner_size(1200.0, 820.0)
                .min_inner_size(900.0, 640.0)
                .initialization_script(SINGLE_WEBVIEW_NAVIGATION_SCRIPT)
                .on_navigation(move |url| handle_navigation(&navigation_app, url, port))
                .on_new_window(move |url, _features| {
                    handle_new_window(&new_window_app, url, port)
                })
                .build()?;

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("failed to build HORIZONE desktop app");

    app.run(|app_handle, event| match event {
        RunEvent::Exit | RunEvent::ExitRequested { .. } => stop_backend(app_handle),
        _ => {}
    });
}

fn navigation_decision(url: &tauri::Url, app_port: u16) -> NavigationDecision {
    if url.scheme() == "http"
        && url.host_str() == Some("127.0.0.1")
        && url.port() == Some(app_port)
    {
        NavigationDecision::AllowInternal
    } else if matches!(url.scheme(), "http" | "https") {
        NavigationDecision::OpenExternal
    } else {
        NavigationDecision::Deny
    }
}

fn handle_navigation(app: &tauri::AppHandle, url: &tauri::Url, app_port: u16) -> bool {
    match navigation_decision(url, app_port) {
        NavigationDecision::AllowInternal => true,
        NavigationDecision::OpenExternal => {
            open_external_url(app, url);
            false
        }
        NavigationDecision::Deny => false,
    }
}

fn handle_new_window(
    app: &tauri::AppHandle,
    url: tauri::Url,
    app_port: u16,
) -> tauri::webview::NewWindowResponse<tauri::Wry> {
    if navigation_decision(&url, app_port) == NavigationDecision::OpenExternal {
        open_external_url(app, &url);
    }
    tauri::webview::NewWindowResponse::Deny
}

fn open_external_url(app: &tauri::AppHandle, url: &tauri::Url) {
    if let Err(error) = app.opener().open_url(url.as_str(), None::<&str>) {
        eprintln!("failed to open external URL in the system browser: {error}");
    }
}

fn stop_backend(app: &tauri::AppHandle) {
    let backend_process = Arc::clone(&app.state::<BackendProcess>().0);
    {
        if let Ok(mut child_slot) = backend_process.lock() {
            if let Some(mut child) = child_slot.take() {
                let _ = child.kill();
                let _ = child.wait();
            }
        };
    }
}

fn find_available_port() -> Result<u16, Box<dyn std::error::Error>> {
    let listener = TcpListener::bind("127.0.0.1:0")?;
    let port = listener.local_addr()?.port();
    drop(listener);
    Ok(port)
}

fn start_backend(
    app: &tauri::AppHandle,
    port: u16,
    data_dir: PathBuf,
) -> Result<Child, Box<dyn std::error::Error>> {
    let backend_path = backend_path(app)?;
    let bundled_runtime = llama_server_path(app)?;
    fs::create_dir_all(&data_dir)?;
    let log_dir = data_dir.join("logs");
    fs::create_dir_all(&log_dir)?;
    let backend_log = fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(log_dir.join("backend.log"))?;
    let mut command = Command::new(backend_path);
    command
        .env("HORIZONE_DESKTOP", "1")
        .env("HOST", "127.0.0.1")
        .env("PORT", port.to_string())
        .env("HORIZONE_DATA_DIR", &data_dir)
        .stdin(Stdio::null())
        .stdout(Stdio::from(backend_log.try_clone()?))
        .stderr(Stdio::from(backend_log));

    if env::var("HORIZONE_LLAMA_CPP_BINARY").is_err() {
        if let Some((runtime_path, runtime_kind)) = bundled_runtime {
            command
                .env("HORIZONE_LLAMA_CPP_BINARY", runtime_path)
                .env("HORIZONE_LLAMA_CPP_SERVER_KIND", runtime_kind);
        }
    }

    Ok(command.spawn()?)
}

fn backend_path(app: &tauri::AppHandle) -> Result<PathBuf, Box<dyn std::error::Error>> {
    if let Ok(configured) = env::var("HORIZONE_BACKEND_BIN") {
        return Ok(PathBuf::from(configured));
    }

    let executable = if cfg!(windows) {
        "horizone-backend.exe"
    } else {
        "horizone-backend"
    };
    let resource_dir = app.path().resource_dir()?;
    let candidates = [
        resource_dir.join("backend").join(executable),
        resource_dir.join(executable),
        resource_dir.join("_up_").join("dist").join("backend").join(executable),
    ];
    for candidate in candidates {
        if candidate.exists() {
            return Ok(candidate);
        }
    }
    Ok(resource_dir.join(executable))
}

fn llama_server_path(
    app: &tauri::AppHandle,
) -> Result<Option<(PathBuf, &'static str)>, Box<dyn std::error::Error>> {
    let resource_dir = app.path().resource_dir()?;
    let native_executable = if cfg!(windows) {
        "llama-server.exe"
    } else {
        "llama-server"
    };
    let python_executable = if cfg!(windows) {
        "horizone-llama-server.exe"
    } else {
        "horizone-llama-server"
    };

    let candidates = [
        (
            resource_dir
                .join("_up_")
                .join("dist")
                .join("runtime")
                .join(native_executable),
            "native",
        ),
        (
            resource_dir
                .join("_up_")
                .join("dist")
                .join("runtime")
                .join(python_executable),
            "python",
        ),
        (
            resource_dir
                .join("_up_")
                .join("dist")
                .join("runtime")
                .join(python_executable),
            "python",
        ),
        (resource_dir.join("runtime").join(native_executable), "native"),
        (resource_dir.join("runtime").join(python_executable), "python"),
        (resource_dir.join(native_executable), "native"),
        (resource_dir.join(python_executable), "python"),
    ];

    for (candidate, kind) in candidates {
        if candidate.exists() {
            return Ok(Some((candidate, kind)));
        }
    }

    Ok(None)
}

fn wait_for_backend(port: u16) -> Result<(), Box<dyn std::error::Error>> {
    let timeout_seconds = env::var("HORIZONE_BACKEND_STARTUP_TIMEOUT")
        .ok()
        .and_then(|value| value.parse::<u64>().ok())
        .unwrap_or(120);
    let deadline = Instant::now() + Duration::from_secs(timeout_seconds);
    while Instant::now() < deadline {
        if TcpStream::connect(("127.0.0.1", port)).is_ok() {
            return Ok(());
        }
        thread::sleep(Duration::from_millis(150));
    }
    Err(format!("HORIZONE backend did not start within {timeout_seconds} seconds").into())
}

#[cfg(test)]
mod tests {
    use super::{navigation_decision, NavigationDecision};

    fn parse_url(value: &str) -> tauri::Url {
        value.parse().expect("test URL should be valid")
    }

    #[test]
    fn allows_only_the_active_local_app_origin() {
        let port = 5058;

        assert_eq!(
            navigation_decision(&parse_url("http://127.0.0.1:5058/settings"), port),
            NavigationDecision::AllowInternal
        );
        assert_eq!(
            navigation_decision(&parse_url("http://127.0.0.1:5059/settings"), port),
            NavigationDecision::OpenExternal
        );
        assert_eq!(
            navigation_decision(&parse_url("http://localhost:5058/settings"), port),
            NavigationDecision::OpenExternal
        );
    }

    #[test]
    fn opens_http_links_externally_and_denies_other_schemes() {
        let port = 5058;

        assert_eq!(
            navigation_decision(&parse_url("https://github.com/Mikemaranon/HORIZONE"), port),
            NavigationDecision::OpenExternal
        );
        assert_eq!(
            navigation_decision(&parse_url("https://huggingface.co/models"), port),
            NavigationDecision::OpenExternal
        );
        assert_eq!(
            navigation_decision(&parse_url("file:///tmp/private.txt"), port),
            NavigationDecision::Deny
        );
        assert_eq!(
            navigation_decision(&parse_url("javascript:alert(1)"), port),
            NavigationDecision::Deny
        );
    }
}
