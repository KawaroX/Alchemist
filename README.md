# Alchemist 炼金术士 - PDF 转 PNG

**Alchemist** 是一款强大的、用户友好的图形界面工具，旨在将您的 PDF 文档页面如炼金术般精准而优雅地转换为高质量的 PNG 图像。

---

## ✨ 项目愿景 (Vision)

在信息洪流的时代，文档的视觉呈现愈发重要。"Alchemist" 致力于打破 PDF 的固有形态，释放其内含的视觉信息，如同炼金术士将凡物点化为金，将静态的文档页面转化为生动、清晰、易于分享和使用的图像瑰宝。我们追求的不仅是转换，更是一种创造的体验。

## 🚀 主要特性 (Features)

- **直观的图形用户界面 (GUI)**：无需命令行操作，所有功能一目了然，轻松上手。
- **灵活的输入方式**：
  - 支持转换单个 PDF 文件。
  - 支持批量处理整个文件夹内的所有 PDF 文档。
  - 可选择递归处理子文件夹。
- **精准的页面选择**：
  - 转换指定单页、多页（如 "1,3,5"）。
  - 转换连续页面范围（如 "2-7"）。
  - 支持特殊指令如 "first" (首页) 或 "all" (所有页面)。
- **高质量图像输出**：
  - 自定义输出 PNG 图像的 DPI（分辨率），确保图像清晰度。
  - 支持转换为灰度图像。
  - 提供图像旋转功能（90°, 180°, 270°）。
- **高级文件管理**：
  - 自定义输出目录。
  - 可选择在递归处理时保留原始目录结构。
  - 自定义输出文件名前缀。
  - 强大的文件名模板功能，精确控制输出文件名格式（例如：`{pdf_name}_page_{page_num}.png`）。
  - 文件名筛选：通过包含/排除关键字或正则表达式精确选择要处理的 PDF 文件。
- **高效与便捷**：
  - 提供“覆盖已存在文件”选项。
  - “空运行”(Dry Run)模式：预览将要执行的操作，而不实际生成文件。
  - **任务终止**：对于耗时较长的转换任务，可以中途安全终止。
  - **配置管理**：保存当前复杂的设置为 JSON 配置文件，方便后续一键加载；也可随时恢复默认设置。
- **清晰的日志输出**：实时显示处理进度、成功信息、警告及错误，便于追踪。可自定义日志显示级别。

## 🛠️ 安装与运行 (Installation & Usage)

**依赖项 (Prerequisites):**

1.  **Python 3**: (建议 Python 3.8 或更高版本)
2.  **Poppler**: 这是 PDF 渲染的核心库。
    - **Windows**:
      1.  从 [Oskar Neustroev 维护的 Poppler for Windows 构建](https://github.com/oschwartz10612/poppler-windows/releases) 下载最新的二进制包 (通常是包含 MinGW 字样的 `.zip` 文件)。
      2.  解压后，将其中的 `bin` 目录路径添加到系统的 `PATH` 环境变量中。
      3.  （对于打包版）或者，按照“打包为可执行程序”部分的说明，将 Poppler 文件捆绑到应用中。
    - **macOS**: 推荐使用 Homebrew 安装: `brew install poppler`
    - **Linux (Debian/Ubuntu)**: `sudo apt-get install poppler-utils`
3.  **Python 库**:
    ```bash
    pip install Pillow pdf2image
    # (可选，为了更好的GUI主题) pip install ttkthemes
    ```

**直接运行脚本:**

1.  克隆或下载本项目。
2.  确保上述依赖项已安装。
3.  在项目根目录下运行：
    ```bash
    python pdf_converter_gui.py
    ```
    (脚本文件名以您实际保存的为准)

## 📦 打包为可执行程序 (Windows & macOS "开包即用")

您可以将 **Alchemist** 打包成独立的可执行应用程序，方便在没有 Python 环境的电脑上运行。我们推荐使用 PyInstaller。

1.  安装 PyInstaller:

    ```bash
    pip install pyinstaller
    ```

2.  **准备 Poppler 文件以供捆绑 (主要针对 Windows)**:
    a. 在您的项目目录下创建一个文件夹，例如 `poppler_for_bundling_win/`。
    b. 将您下载的 Windows 版 Poppler 的 `bin/` 目录（包含 `.exe` 和 `.dll` 文件，例如来自 `poppler-24.08.0/Library/bin/`）的**所有内容**复制到 `poppler_for_bundling_win/bin/`。
    c. 将 Poppler 的 `share/poppler/` 目录（包含 `cidToUnicode` 等数据，例如来自顶层的 `poppler-24.08.0/share/poppler/`）**整个 `poppler` 文件夹**复制到 `poppler_for_bundling_win/share/` 下，形成 `poppler_for_bundling_win/share/poppler/`。
    d. (可选) 如果有 `share/glib-2.0/schemas/`，也按类似结构复制。

3.  **执行打包命令 (在对应操作系统上分别执行)**:

    - **Windows**:

      ```bash
      pyinstaller --noconsole --name Alchemist ^
      --add-data "poppler_for_bundling_win\bin;poppler\bin" ^
      --add-data "poppler_for_bundling_win\share\poppler;poppler\share\poppler" ^
      --add-data "poppler_for_bundling_win\share\glib-2.0\schemas;poppler\share\glib-2.0\schemas" ^
      --icon=your_app_icon.ico ^
      pdf_converter_gui.py
      ```

      _(请将 `your_app_icon.ico` 替换为您的图标文件路径；如果 `glib-2.0/schemas` 不存在，可移除对应 `--add-data` 行)_

    - **macOS**:
      对于 macOS，更简单的分发方式是依赖用户通过 Homebrew 自行安装 Poppler。脚本会自动尝试使用系统路径中的 Poppler。
      ```bash
      pyinstaller --windowed --name Alchemist \
      --icon=your_app_icon.icns \
      pdf_converter_gui.py
      ```
      _(请将 `your_app_icon.icns` 替换为您的图标文件路径)_
      如果您希望在 macOS 上也完全捆绑 Poppler（这会更复杂，可能需要使用 `install_name_tool` 调整库路径），则需要添加相应的 `--add-data` 命令来包含从 Homebrew 安装中提取的 Poppler `bin`, `lib`, `share/poppler` 文件。

4.  打包完成后，可执行程序会位于 `dist/Alchemist` 文件夹内。

## 📖 使用指南 (Quick Guide)

| 参数     | 默认值 | 说明                             |
| -------- | ------ | -------------------------------- |
| 页面范围 | first  | 支持 first/all/页码/范围(如 1-5) |
| DPI      | 300    | 图像输出质量                     |
| 覆盖模式 | 关闭   | 覆盖已存在的 PNG 文件            |
| 灰度转换 | 关闭   | 输出黑白图像                     |

1.  启动 **Alchemist** 应用程序。
2.  **输入/输出设置**:
    - 点击“浏览文件”或“浏览目录”选择源 PDF 文件或包含 PDF 的文件夹。
    - （可选）点击“浏览目录”指定 PNG 图片的输出文件夹。若不指定，则在源文件/文件夹旁边创建 `_pngs_gui` 后缀的目录。
    - （可选）设置输出文件名的前缀和自定义模板。
3.  **转换核心参数**:
    - 在“转换页面”框中输入要转换的页面（如 "1", "3-5", "all", "first"）。
    - 设置所需的 DPI。
    - 勾选是否覆盖已存在文件或进行“空运行”。
4.  **文件发现与筛选**:
    - 若处理文件夹，可勾选“递归处理子目录”和“保留目录结构”。
    - 使用关键字或正则表达式精确筛选要处理的 PDF 文件。
5.  **图像后处理**:
    - 选择是否转换为灰度图。
    - 选择旋转角度。
6.  **配置管理**:
    - 点击“加载配置”可载入之前保存的设置。
    - 点击“保存配置”可将当前所有设置存为一个 JSON 文件。
    - 点击“恢复默认”将所有选项重置。
7.  **开始转换**:
    - 点击“开始转换”按钮。
    - 如果任务耗时较长，可以点击“终止转换”按钮来停止当前操作。
8.  **查看日志**: 在下方的日志区域查看详细的处理过程和结果。

## 💡 提示 (Tips)

- **Poppler**: 确保 Poppler 已正确安装并可被系统访问（尤其是在直接运行 Python 脚本或未完全捆绑 Poppler 的 macOS 应用时）。
- **文件名模板占位符**: `{pdf_name}`, `{pdf_suffix}`, `{page_num}`, `{total_pages}`, `{dpi}`, `{prefix}`, `{original_dir_name}`, `{relative_parent_dir_name}`。
- **性能**: 处理大量或非常大的 PDF 文件，尤其是高 DPI 转换时，可能需要较长时间和较多系统资源。

## 🤝 贡献 (Contributing)

欢迎各种形式的贡献，包括 Bug 报告、功能建议或代码贡献。

## 📄 许可证 (License)

MIT License
