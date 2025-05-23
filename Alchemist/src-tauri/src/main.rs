// Prevents additional console window on Windows in release, DO NOT REMOVE!!
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use tauri_plugin_dialog::FilePath;
use tauri::{command, generate_handler, AppHandle, Manager};
use tauri_plugin_dialog::DialogExt;
use tokio::sync::oneshot;
use tokio::process::Command as TokioCommand; // Use tokio::process::Command
use tokio::io::AsyncBufReadExt; // For reading stdout/stderr asynchronously
use std::process::Stdio; // Still need Stdio from std::process

#[command]
async fn open_file_dialog(app_handle: AppHandle) -> Option<String> {
    let (tx, rx) = oneshot::channel(); // 只保留一个 channel
    app_handle.dialog().file().pick_file(move |file_path_option: Option<FilePath>| { // 明确参数类型
        // 将 Option<FilePath> 转换为 Option<String>
        // FilePath 结构体有一个公共方法 into_path_buf() 来获取 PathBuf
        let result = file_path_option.map(|fp| fp.into_path().expect("REASON").display().to_string());
        let _ = tx.send(result);
    });
    // rx.await.unwrap_or_default() 对于 Option<String> 来说，default 是 None
    rx.await.unwrap_or(None) // 如果通道被关闭或没有值，则返回 None
}

#[command]
async fn open_directory_dialog(app_handle: AppHandle) -> Option<String> {
    let (tx, rx) = oneshot::channel(); // 只保留一个 channel
    app_handle.dialog().file().pick_folder(move |file_path_option: Option<FilePath>| { // 明确参数类型
        let result = file_path_option.map(|fp| fp.into_path().expect("REASON").display().to_string());
        let _ = tx.send(result);
    });
    rx.await.unwrap_or(None) // 如果通道被关闭或没有值，则返回 None
}

#[command]
async fn start_python_backend(app_handle: AppHandle) -> Result<String, String> {
    // In development, resource_dir might point to target/debug, which is not where the backend is.
    // For development, assume backend is relative to the project root.
    // For production, resource_dir() should correctly point to the bundled resources.
    let python_script_path = if cfg!(debug_assertions) {
        // In dev mode, current_dir is src-tauri/, so navigate up one level to Alchemist/ then into backend/
        std::env::current_dir().map_err(|e| e.to_string())?.join("..").join("backend").join("flask_api.py")
    } else {
        // In release mode, resources are bundled
        app_handle.path().resource_dir().map_err(|e| e.to_string())?.join("backend").join("flask_api.py")
    };

    if !python_script_path.exists() {
        return Err(format!("Python script not found at: {:?}", python_script_path));
    }

    println!("Attempting to start Python backend at: {:?}", python_script_path);

    let mut command = TokioCommand::new("python3"); // Changed to python3
    command.args(&[python_script_path.to_str().unwrap()]);
    command.stdout(Stdio::piped());
    command.stderr(Stdio::piped());

    let mut child = command.spawn()
        .map_err(|e| format!("Failed to spawn python process: {}", e))?;

    let pid_string = child.id().map_or("N/A".to_string(), |id| id.to_string()); // Get PID before moving child

    let stdout = child.stdout.take().ok_or_else(|| "Failed to capture stdout".to_string())?;
    let stderr = child.stderr.take().ok_or_else(|| "Failed to capture stderr".to_string())?;

    tokio::spawn(async move {
        let mut stdout_reader = tokio::io::BufReader::new(stdout).lines();
        let mut stderr_reader = tokio::io::BufReader::new(stderr).lines();

        loop {
            tokio::select! {
                stdout_line = stdout_reader.next_line() => {
                    match stdout_line {
                        Ok(Some(line)) => println!("[Python Backend stdout]: {}", line),
                        Ok(None) => break, // EOF
                        Err(e) => eprintln!("Error reading stdout: {}", e),
                    }
                },
                stderr_line = stderr_reader.next_line() => {
                    match stderr_line {
                        Ok(Some(line)) => eprintln!("[Python Backend stderr]: {}", line),
                        Ok(None) => break, // EOF
                        Err(e) => eprintln!("Error reading stderr: {}", e),
                    }
                },
                else => break, // Both streams closed
            }
        }
        // Wait for the child process to exit
        let _ = child.wait().await; // .await is correct here for tokio::process::Child::wait()
    });

    Ok(format!("Python backend started with PID: {}", pid_string)) // Use the stored PID string
}

#[tauri::command]
async fn open_path_in_system(path: String) -> Result<(), String> {
    // 打印将要打开的路径，用于调试
    println!("[Rust Command] Attempting to open path: {}", path);

    #[cfg(target_os = "windows")]
    {
        // Windows: 使用 "explorer" 可以打开文件或文件夹
        // 或者使用 "start" 命令，它更通用一些
        // Command::new("explorer")
        //     .arg(&path)
        //     .spawn()
        //     .map_err(|e| format!("Failed to open path on Windows with explorer: {}", e))?;
        tokio::process::Command::new("cmd")
            .args(["/C", "start", "", &path]) // 使用 start 命令, "" 是标题参数
            .spawn()
            .map_err(|e| format!("Failed to open path on Windows with start: {}", e))?;
    }
    #[cfg(target_os = "macos")]
    {
        // macOS: 使用 "open" 命令
        tokio::process::Command::new("open")
            .arg(&path)
            .spawn()
            .map_err(|e| format!("Failed to open path on macOS: {}", e))?;
    }
    #[cfg(target_os = "linux")]
    {
        // Linux: 使用 "xdg-open" 命令
        tokio::process::Command::new("xdg-open")
            .arg(&path)
            .spawn()
            .map_err(|e| format!("Failed to open path on Linux: {}", e))?;
    }

    Ok(())
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init()) // Initialize the opener plugin
        .plugin(tauri_plugin_shell::init()) // Initialize the shell plugin
        // .plugin(tauri_plugin_process::init()) // Remove plugin init as we are using tokio::process
        .invoke_handler(generate_handler![open_file_dialog, open_directory_dialog, start_python_backend,
            open_path_in_system])
        .setup(|app| {
            let app_handle = app.app_handle().clone(); // Clone app_handle here
            tauri::async_runtime::spawn(async move {
                match start_python_backend(app_handle).await { // Removed .clone() here as it's already cloned
                    Ok(msg) => println!("{}", msg),
                    Err(err) => eprintln!("Error starting Python backend: {}", err),
                }
            });
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
