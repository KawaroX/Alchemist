import { invoke } from "@tauri-apps/api/core";

const pdfForm = document.querySelector<HTMLFormElement>("#pdf-form");
const conversionOutput =
  document.querySelector<HTMLDivElement>("#conversion-output");
const convertButton =
  document.querySelector<HTMLButtonElement>("#convert_button");
const stopButton = document.querySelector<HTMLButtonElement>("#stop_button");

const browseInputFileButton =
  document.querySelector<HTMLButtonElement>("#browse_input_file");
const browseInputDirButton =
  document.querySelector<HTMLButtonElement>("#browse_input_dir");
const browseOutputDirButton =
  document.querySelector<HTMLButtonElement>("#browse_output_dir");

browseInputFileButton?.addEventListener("click", async () => {
  const filePath = (await invoke("open_file_dialog")) as string;
  if (filePath) {
    console.log(filePath, "");
    (document.getElementById("input_path") as HTMLInputElement).value =
      filePath;
  }
});

browseInputDirButton?.addEventListener("click", async () => {
  const dirPath = (await invoke("open_directory_dialog")) as string;
  if (dirPath) {
    (document.getElementById("input_path") as HTMLInputElement).value = dirPath;
  }
});

browseOutputDirButton?.addEventListener("click", async () => {
  const dirPath = (await invoke("open_directory_dialog")) as string;
  if (dirPath) {
    (document.getElementById("output_dir") as HTMLInputElement).value = dirPath;
  }
});

stopButton?.addEventListener("click", async () => {
  try {
    await fetch("http://localhost:5003/stop", {
      method: "POST",
    });
    conversionOutput!.innerHTML += `<p>转换终止请求已发送。</p>`;
  } catch (error) {
    conversionOutput!.innerHTML += `<p>错误: 无法发送终止请求: ${error}</p>`;
  } finally {
    convertButton!.disabled = false;
    stopButton!.disabled = true;
  }
});

pdfForm?.addEventListener("submit", async (event) => {
  event.preventDefault();

  convertButton!.disabled = true;
  stopButton!.disabled = false;
  conversionOutput!.innerHTML = ""; // Clear previous output

  const input_path = (document.getElementById("input_path") as HTMLInputElement)
    .value;
  const output_dir = (document.getElementById("output_dir") as HTMLInputElement)
    .value;
  const pages = (document.getElementById("pages") as HTMLInputElement).value;
  const dpi = (document.getElementById("dpi") as HTMLInputElement).value;
  const prefix = (document.getElementById("prefix") as HTMLInputElement).value;
  const output_filename_template = (
    document.getElementById("output_filename_template") as HTMLInputElement
  ).value;
  const post_export_action = (
    document.getElementById("post_export_action") as HTMLSelectElement
  ).value;
  const recursive = (document.getElementById("recursive") as HTMLInputElement)
    .checked;
  const preserve_structure = (
    document.getElementById("preserve_structure") as HTMLInputElement
  ).checked;
  const include_keywords = (
    document.getElementById("include_keywords") as HTMLInputElement
  ).value;
  const exclude_keywords = (
    document.getElementById("exclude_keywords") as HTMLInputElement
  ).value;
  const regex_filter = (
    document.getElementById("regex_filter") as HTMLInputElement
  ).value;
  const grayscale = (document.getElementById("grayscale") as HTMLInputElement)
    .checked;
  const rotate = parseInt(
    (document.getElementById("rotate") as HTMLSelectElement).value
  ); // Convert to integer

  const data = {
    input_path,
    output_dir,
    pages,
    dpi,
    prefix,
    output_filename_template,
    post_export_action,
    recursive,
    preserve_structure,
    include_keywords,
    exclude_keywords,
    regex_filter,
    grayscale,
    rotate,
  };

  try {
    const response = await fetch("http://localhost:5003/convert", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(data),
    });

    const result = await response.json();
    conversionOutput!.innerHTML = ""; // Clear previous output

    if (result.logs && Array.isArray(result.logs)) {
      result.logs.forEach((log: { level: string; message: string }) => {
        const p = document.createElement("p");
        p.textContent = log.message;
        p.classList.add(`log-${log.level.toLowerCase()}`); // Add class based on log level
        conversionOutput!.appendChild(p);
      });
    } else if (result.message) {
      conversionOutput!.innerHTML += `<p>${result.message}</p>`;
    } else {
      conversionOutput!.innerHTML += `<p>未知响应: ${JSON.stringify(
        result,
        null,
        2
      )}</p>`;
    }

    if (result.status === "completed") {
      conversionOutput!.innerHTML += `<p>转换完成！</p>`;
      if (result.output_path) {
        if (
          post_export_action === "open_file" ||
          post_export_action === "open_folder"
        ) {
          const pathToOpen = String(result.output_path); // 确保是字符串
          console.log("Attempting to open path:", pathToOpen);
          console.log("Post export action:", post_export_action);
          try {
            await invoke("open_path_in_system", { path: pathToOpen });
            if (post_export_action === "open_file") {
                conversionOutput!.innerHTML += `<p>请求打开文件: ${pathToOpen}</p>`;
            } else { // post_export_action === "open_folder"
                conversionOutput!.innerHTML += `<p>请求打开目录: ${pathToOpen}</p>`;
            }
          } catch (openError) {
            conversionOutput!.innerHTML += `<p>错误: 调用 Rust command 打开路径失败: ${openError}</p>`; 
          }
        }
      }
    } else if (result.status === "stopped") {
      conversionOutput!.innerHTML += `<p>转换已终止。</p>`;
    } else if (
      result.status === "error" ||
      result.status === "critical_error"
    ) {
      conversionOutput!.innerHTML += `<p>转换过程中发生错误。</p>`;
    }
  } catch (error) {
    conversionOutput!.innerHTML += `<p>错误: 无法连接到后端服务或请求失败: ${error}</p>`;
  } finally {
    convertButton!.disabled = false;
    stopButton!.disabled = true;
  }
});

const themeToggleButton =
  document.querySelector<HTMLButtonElement>("#theme-toggle");

// Function to apply the theme
function applyTheme(theme: string) {
  document.body.classList.toggle("dark-mode", theme === "dark");
  const iconSpan = themeToggleButton?.querySelector(".icon");
  if (iconSpan) {
    iconSpan.textContent = theme === "dark" ? "🌙" : "☀️";
  }
}

// Check for saved theme preference on load and set up event listeners
document.addEventListener("DOMContentLoaded", () => {
  const savedTheme = localStorage.getItem("theme");
  if (savedTheme) {
    applyTheme(savedTheme);
  } else if (
    window.matchMedia &&
    window.matchMedia("(prefers-color-scheme: dark)").matches
  ) {
    // If no saved theme, check system preference
    applyTheme("dark");
  } else {
    applyTheme("light");
  }

  // Add event listener for theme toggle button
  themeToggleButton?.addEventListener("click", () => {
    const currentTheme = document.body.classList.contains("dark-mode")
      ? "dark"
      : "light";
    const newTheme = currentTheme === "dark" ? "light" : "dark";
    applyTheme(newTheme);
    localStorage.setItem("theme", newTheme);
  });

  // Tab functionality
  const tabButtons =
    document.querySelectorAll<HTMLButtonElement>(".tab-button");
  const tabContents = document.querySelectorAll<HTMLDivElement>(".tab-content");

  tabButtons.forEach((button) => {
    button.addEventListener("click", () => {
      // Deactivate all tab buttons and contents
      tabButtons.forEach((btn) => btn.classList.remove("active"));
      tabContents.forEach((content) => content.classList.remove("active"));

      // Activate the clicked button and its corresponding content
      button.classList.add("active");
      const targetTabId = button.dataset.tab;
      const targetTabContent = document.getElementById(targetTabId || "");
      if (targetTabContent) {
        targetTabContent.classList.add("active");
      }
    });
  });
});
