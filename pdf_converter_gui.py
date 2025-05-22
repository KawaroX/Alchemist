#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import os
import sys
import json
import logging
import subprocess
import re
from pathlib import Path
from pdf2image import convert_from_path, pdfinfo_from_path
from PIL import Image, ImageTk # Pillow for image processing and Tkinter display
import threading
import queue
import platform 

# --- 全局日志记录器 ---
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG) 

# --- 默认配置 ---
DEFAULT_CONFIG = {
    "input_path": "",
    "output_dir": "",
    "pages": "first",
    "dpi": 300,
    "prefix": "",
    "overwrite": False,
    "recursive": False,
    "include_keywords": [], 
    "exclude_keywords": [], 
    "regex_filter": "",
    "preserve_structure": False,
    "output_filename_template": "{pdf_name}_page_{page_num}.png",
    "grayscale": False,
    "rotate": 0,
    "dry_run": False,
    "verbose_level": "INFO", # 默认GUI日志级别改为INFO
    "post_export_action": "open_file", # open_file, open_folder, both, none
}

# --- Poppler路径处理 ---
BUNDLED_POPPLER_PATH = None 

def get_application_path():
    if getattr(sys, 'frozen', False):  
        if hasattr(sys, '_MEIPASS'):    
            return Path(sys._MEIPASS)
        else:  
            return Path(sys.executable).parent
    else:  
        return Path(__file__).parent.resolve()

def check_and_prompt_homebrew_poppler():
    """Mac专用检测Homebrew和Poppler"""
    logger.info("正在检测macOS环境下的Poppler安装情况...")
    
    # 检测Homebrew是否安装
    if os.system("which brew >/dev/null 2>&1") != 0:
        logger.error("未找到Homebrew！请先安装Homebrew：")
        logger.error("安装命令（粘贴到终端执行）：")
        logger.error('/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"')
        return None
    
    # 检测poppler是否通过Homebrew安装
    poppler_path = Path("/opt/homebrew/opt/poppler/bin")
    poppler_exe = poppler_path / "pdfinfo"
    
    if not poppler_exe.exists():
        logger.error("未通过Homebrew安装poppler！请执行以下命令安装：")
        logger.error("brew install poppler")
        return None
    
    logger.info(f"检测到Homebrew安装的poppler路径: {poppler_path}")
    return str(poppler_path)

def find_and_set_bundled_poppler_path():
    global BUNDLED_POPPLER_PATH
    system = platform.system()
    
    if system == "Darwin":  # macOS
        BUNDLED_POPPLER_PATH = check_and_prompt_homebrew_poppler()
        if not BUNDLED_POPPLER_PATH:
            logger.warning("无法找到有效的poppler路径，转换可能失败！")
            
    elif system == "Windows":
        app_path = get_application_path()
        potential_poppler_bin_dir = app_path / "poppler_to_bundle" / "Library" / "bin"
        poppler_test_exe_name = "pdfinfo.exe"
        
        if (potential_poppler_bin_dir / poppler_test_exe_name).is_file():
            BUNDLED_POPPLER_PATH = str(potential_poppler_bin_dir)
            logger.info(f"成功定位到捆绑的Poppler路径: {BUNDLED_POPPLER_PATH}")
        else:
            logger.warning(f"未在预期的路径 '{potential_poppler_bin_dir}' 找到捆绑的Poppler。")
            logger.warning("请确认已正确放置poppler_to_bundle目录或已安装系统PATH中的Poppler。")
    
    else:  # Linux/其他系统
        logger.info("非Windows/macOS系统，依赖系统PATH中的poppler")
        BUNDLED_POPPLER_PATH = None
    
    return BUNDLED_POPPLER_PATH

# --- 核心转换逻辑 ---
def parse_page_ranges(page_str, total_pages):
    if not page_str or page_str.lower() == 'first':
        return [1] if total_pages > 0 else []
    if page_str.lower() == 'all':
        return list(range(1, total_pages + 1))
    pages = set()
    try:
        parts = page_str.split(',')
        for part in parts:
            part = part.strip()
            if '-' in part:
                start_str, end_str = part.split('-', 1)
                start = int(start_str)
                end = int(end_str)
                if not (0 < start <= end <= total_pages):
                    raise ValueError(f"页面范围 {part} 对于总共 {total_pages} 页的PDF无效。")
                pages.update(range(start, end + 1))
            else:
                page_num = int(part)
                if not (0 < page_num <= total_pages):
                    raise ValueError(f"页码 {page_num} 对于总共 {total_pages} 页的PDF无效。")
                pages.add(page_num)
    except ValueError as e:
        logger.error(f"解析页面字符串 '{page_str}' 失败: {e}")
        return None
    return sorted(list(pages))

def generate_output_filename(template, pdf_path, page_num, total_pages, dpi, prefix, original_input_dir=None):
    pdf_name = pdf_path.stem
    pdf_suffix = pdf_path.suffix
    original_dir_name = pdf_path.parent.name
    relative_parent_dir_name = ""
    if original_input_dir and pdf_path.parent != original_input_dir:
        try:
            relative_path = pdf_path.parent.relative_to(original_input_dir)
            relative_parent_dir_name = relative_path.name if relative_path.name else relative_path.parent.name 
        except ValueError:
            relative_parent_dir_name = original_dir_name
    
    default_filename = f"{prefix}{pdf_name}_page_{page_num}.png"
    if not template:
        return default_filename
    try:
        filename = template.format(
            pdf_name=pdf_name, pdf_suffix=pdf_suffix, page_num=page_num,
            total_pages=total_pages, dpi=dpi, prefix=prefix,
            original_dir_name=original_dir_name,
            relative_parent_dir_name=relative_parent_dir_name
        )
        if not filename.lower().endswith(".png"):
            filename += ".png"
        return filename
    except KeyError as e:
        logger.warning(f"文件名模板 '{template}' 中存在未知占位符: {e}。将使用默认文件名格式。")
        return default_filename
    except Exception as e:
        logger.warning(f"应用文件名模板 '{template}' 时出错: {e}。将使用默认文件名格式。")
        return default_filename

def convert_single_pdf(pdf_path, output_dir_base, pages_to_convert_str, dpi, overwrite, prefix,
                       filename_template, grayscale, rotate_angle, dry_run,
                       preserve_structure=False, input_root_dir=None, stop_event=None): # Added stop_event
    global BUNDLED_POPPLER_PATH 
    try:
        pdf_info = pdfinfo_from_path(pdf_path, poppler_path=BUNDLED_POPPLER_PATH)
        total_pages = pdf_info.get("Pages", 0)
        if total_pages == 0:
            logger.warning(f"无法获取 '{pdf_path.name}' 的页数，可能文件已损坏或非标准PDF。跳过。")
            return 0
    except Exception as e:
        logger.error(f"读取PDF信息失败 '{pdf_path.name}': {e}。跳过。")
        return 0

    if stop_event and stop_event.is_set(): return 0 # Check before processing pages

    pages_list = parse_page_ranges(pages_to_convert_str, total_pages)
    if pages_list is None: return 0

    converted_count_for_this_pdf = 0
    current_output_dir = output_dir_base
    if preserve_structure and input_root_dir and pdf_path.parent != input_root_dir:
        try:
            relative_subdir = pdf_path.parent.relative_to(input_root_dir)
            current_output_dir = output_dir_base / relative_subdir
        except ValueError:
            logger.warning(f"无法为 {pdf_path} 保留目录结构，因为它不在 {input_root_dir} 之下。")

    if not dry_run:
        current_output_dir.mkdir(parents=True, exist_ok=True)
    else:
        logger.info(f"[空运行] {'将会创建' if not current_output_dir.exists() else '输出目录已存在'}: {current_output_dir.resolve()}")

    for page_num in pages_list:
        if stop_event and stop_event.is_set():
            logger.info(f"PDF '{pdf_path.name}' 的页面处理被终止。")
            break # Stop processing pages for this PDF

        output_filename = generate_output_filename(
            filename_template, pdf_path, page_num, total_pages, dpi, prefix,
            original_input_dir=input_root_dir
        )
        output_png_path = current_output_dir / output_filename

        if output_png_path.exists() and not overwrite:
            logger.info(f"跳过 (已存在且未指定覆盖): {output_png_path.resolve()}")
            continue

        logger.info(f"准备转换: '{pdf_path.name}' (第 {page_num}/{total_pages} 页) -> '{output_png_path.resolve()}'")

        if dry_run:
            logger.info(f"[空运行] 将转换并保存到: {output_png_path.resolve()}")
            converted_count_for_this_pdf +=1 
            continue

        try:
            images = convert_from_path(pdf_path, dpi=dpi, first_page=page_num, last_page=page_num, fmt='png', poppler_path=BUNDLED_POPPLER_PATH)
            if images:
                image = images[0]
                if grayscale:
                    image = image.convert("L")
                if rotate_angle != 0:
                    image = image.rotate(rotate_angle, expand=True)
                image.save(output_png_path, 'PNG')
                logger.info(f"成功保存: {output_png_path.resolve()}")
                converted_count_for_this_pdf += 1
            else:
                logger.error(f"未能从 '{pdf_path.name}' 第 {page_num} 页生成图像。")
        except Exception as e:
            logger.error(f"转换 '{pdf_path.name}' 第 {page_num} 页时发生错误: {e}")
    return converted_count_for_this_pdf

def discover_pdf_files(input_path_obj, recursive, include_keywords_list, exclude_keywords_list, regex_filter_str):
    pdf_files_to_process = []
    regex = None
    if regex_filter_str:
        try:
            regex = re.compile(regex_filter_str)
        except re.error as e:
            logger.error(f"无效的正则表达式 '{regex_filter_str}': {e}。将忽略此筛选器。")
    
    files_to_scan = []
    if input_path_obj.is_file():
        if input_path_obj.suffix.lower() == '.pdf':
            files_to_scan.append(input_path_obj)
        else:
            logger.warning(f"输入路径 '{input_path_obj}' 是一个文件但不是PDF，已跳过。")
            return []
    elif input_path_obj.is_dir():
        iterator = input_path_obj.rglob('*.pdf') if recursive else input_path_obj.glob('*.pdf')
        files_to_scan.extend(list(iterator))

    for pdf_file in files_to_scan:
        if pdf_file.is_file():
            if check_filename_filters(pdf_file.name, include_keywords_list, exclude_keywords_list, regex):
                pdf_files_to_process.append(pdf_file)
            else:
                logger.debug(f"文件 '{pdf_file.name}' 未通过文件名筛选，已跳过。")
    return pdf_files_to_process

def check_filename_filters(filename, include_keywords, exclude_keywords, regex_obj):
    if include_keywords: 
        if not any(keyword.lower() in filename.lower() for keyword in include_keywords if keyword):
            return False
    if exclude_keywords: 
        if any(keyword.lower() in filename.lower() for keyword in exclude_keywords if keyword):
            return False
    if regex_obj:
        if not regex_obj.search(filename):
            return False
    return True

# --- Tkinter GUI部分 ---
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("PDF转PNG")
        self.geometry("980x820") 

        self.log_queue = queue.Queue()
        self.current_config = DEFAULT_CONFIG.copy()
        self.stop_conversion_event = threading.Event() # Event for stopping conversion
        self.conversion_thread = None # To keep a reference to the conversion thread
        
        try:
            from ttkthemes import ThemedTk
            s = ttk.Style(self)
            available_themes = s.theme_names()
            if "clam" in available_themes: 
                s.theme_use("clam")
                logger.info("应用 'clam' 主题。")
            elif "vista" in available_themes and sys.platform == "win32":
                 s.theme_use("vista")
                 logger.info("应用 'vista' 主题。")
        except ImportError:
            logger.info("ttkthemes 库未找到，使用默认Tkinter外观。")
        except tk.TclError as e:
            logger.warning(f"应用主题失败: {e}")

        self._create_widgets()
        self._setup_logging_gui()
        self.after(100, self._process_log_queue)

    def _setup_logging_gui(self):
        gui_log_handler = QueueHandler(self.log_queue)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%H:%M:%S')
        gui_log_handler.setFormatter(formatter)
        logger.addHandler(gui_log_handler)
        self._update_logger_level()

    def _update_logger_level(self):
        level_str = self.vars["verbose_level"].get()
        level = logging.getLevelName(level_str.upper())
        for handler in logger.handlers:
            if isinstance(handler, QueueHandler): 
                 handler.setLevel(level)
        logger.setLevel(min(level, logger.level)) 

    def _process_log_queue(self):
        while not self.log_queue.empty():
            message = self.log_queue.get_nowait()
            self.log_text.config(state=tk.NORMAL)
            self.log_text.insert(tk.END, message + "\n")
            self.log_text.see(tk.END) 
            self.log_text.config(state=tk.DISABLED)
        self.after(100, self._process_log_queue) 

    def _on_mousewheel(self, event):
        # 更平滑的滚动实现
        scroll_speed = 1  # 基础滚动速度
        scroll_unit = "units"  # 使用"units"而非"pages"更平滑
        
        # 根据平台确定滚动方向和量
        if sys.platform == "darwin":  # macOS
            delta = event.delta
            # 在Mac上delta值较小，需要放大
            scroll_speed = max(1, abs(delta) // 10)
        elif event.num == 4:  # Linux scroll up
            delta = 120
        elif event.num == 5:  # Linux scroll down
            delta = -120
        else:  # Windows或其他平台
            delta = event.delta if hasattr(event, 'delta') else 0
        
        if delta:
            # 计算滚动方向和量
            direction = -1 if delta > 0 else 1
            scroll_amount = direction * scroll_speed
            
            # 获取当前滚动位置
            first_vis, last_vis = self.canvas.yview()
            
            # 边界检查 - 防止过度滚动
            if (direction < 0 and first_vis <= 0) or (direction > 0 and last_vis >= 1):
                return "break"  # 已经到达边界
            
            # 执行平滑滚动
            self.canvas.yview_scroll(scroll_amount, scroll_unit)
            
            # 防止事件冒泡
            return "break"


    def _create_widgets(self):
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # --- 顶部固定操作按钮栏 ---
        top_action_buttons_frame = ttk.Frame(main_frame, padding=(0, 0, 0, 10)) 
        top_action_buttons_frame.pack(side=tk.TOP, fill=tk.X)

        self.start_button = ttk.Button(top_action_buttons_frame, text="开始转换", command=self._start_conversion_thread, style="Accent.TButton")
        self.start_button.pack(side=tk.RIGHT, padx=(10,0)) 
        
        self.stop_button = ttk.Button(top_action_buttons_frame, text="终止转换", command=self._request_stop_conversion, state=tk.DISABLED)
        self.stop_button.pack(side=tk.RIGHT, padx=(5,0))


        config_buttons_frame = ttk.Frame(top_action_buttons_frame)
        config_buttons_frame.pack(side=tk.LEFT)
        ttk.Button(config_buttons_frame, text="加载配置", command=self._load_config_from_file).pack(side=tk.LEFT, padx=(0,5))
        ttk.Button(config_buttons_frame, text="保存配置", command=self._save_config_to_file).pack(side=tk.LEFT, padx=(0,5))
        ttk.Button(config_buttons_frame, text="恢复默认", command=self._restore_defaults).pack(side=tk.LEFT)


        # --- PanedWindow for scrollable config and log ---
        paned_window = ttk.PanedWindow(main_frame, orient=tk.VERTICAL)
        paned_window.pack(fill=tk.BOTH, expand=True)

        # --- 配置区域 (可滚动) ---
        config_frame_container = ttk.Frame(paned_window) 
        paned_window.add(config_frame_container, weight=75) 

        self.canvas = tk.Canvas(config_frame_container, highlightthickness=0) # Store as instance variable
        scrollbar = ttk.Scrollbar(config_frame_container, orient="vertical", command=self.canvas.yview)
        self.config_scrollable_frame = ttk.Frame(self.canvas, padding="10") 
        
        self.canvas_window_item_id = self.canvas.create_window((0, 0), window=self.config_scrollable_frame, anchor="nw")

        def _on_canvas_configure(event):
            canvas_width = event.width
            self.canvas.itemconfig(self.canvas_window_item_id, width=canvas_width)
        self.canvas.bind('<Configure>', _on_canvas_configure)

        self.config_scrollable_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        
        # Bind mouse wheel events to canvas and scrollable frame
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind("<Button-4>", self._on_mousewheel)
        self.canvas.bind("<Button-5>", self._on_mousewheel)
        
        # Also bind to scrollable frame and its children
        self.config_scrollable_frame.bind("<MouseWheel>", self._on_mousewheel)
        self.config_scrollable_frame.bind("<Button-4>", self._on_mousewheel)
        self.config_scrollable_frame.bind("<Button-5>", self._on_mousewheel)
        
        # Bind to main window for better coverage
        self.bind("<MouseWheel>", self._on_mousewheel)
        self.bind("<Button-4>", self._on_mousewheel)
        self.bind("<Button-5>", self._on_mousewheel)


        scrollbar.pack(side=tk.RIGHT, fill=tk.Y) 
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True) 


        # --- 日志区域 ---
        log_frame_container = ttk.Frame(paned_window, padding=(0,10,0,0)) 
        paned_window.add(log_frame_container, weight=25)

        ttk.Label(log_frame_container, text="程序日志与状态:", font="-weight bold").pack(anchor=tk.W, pady=(0,5))
        self.log_text = scrolledtext.ScrolledText(log_frame_container, wrap=tk.WORD, state=tk.DISABLED, height=10, relief=tk.SOLID, borderwidth=1)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        # --- Tkinter变量初始化 ---
        self.vars = {key: tk.StringVar(value=str(val)) if not isinstance(val, bool) and not isinstance(val, list)
                                   else tk.BooleanVar(value=val) if isinstance(val, bool)
                                   else tk.StringVar(value=",".join(val) if val else "") 
                     for key, val in self.current_config.items()}
        self.vars["rotate"] = tk.IntVar(value=self.current_config["rotate"])
        self.vars["verbose_level"] = tk.StringVar(value=self.current_config["verbose_level"])

        # --- 控件布局 ---
        PAD_X_LABEL = (5, 5) 
        PAD_X_WIDGET = (0, 10)
        PAD_Y_ROW = (6, 6) 
        GROUP_PAD_Y = (10, 10) 
        INPUT_WIDTH = 55 

        # --- 输入/输出设置 ---
        lf_io = ttk.LabelFrame(self.config_scrollable_frame, text=" 输入/输出设置 ", padding="10")
        lf_io.pack(fill=tk.X, padx=5, pady=GROUP_PAD_Y, expand=True) 
        
        row_idx = 0
        ttk.Label(lf_io, text="输入PDF文件/目录:").grid(row=row_idx, column=0, sticky=tk.W, padx=PAD_X_LABEL, pady=PAD_Y_ROW)
        ttk.Entry(lf_io, textvariable=self.vars["input_path"], width=INPUT_WIDTH).grid(row=row_idx, column=1, sticky=tk.EW, padx=PAD_X_WIDGET, pady=PAD_Y_ROW)
        
        browse_buttons_frame_input = ttk.Frame(lf_io)
        browse_buttons_frame_input.grid(row=row_idx, column=2, sticky=tk.E, padx=PAD_X_WIDGET, pady=PAD_Y_ROW)
        ttk.Button(browse_buttons_frame_input, text="浏览文件", command=self._browse_input_file, width=10).pack(side=tk.LEFT, padx=(0,2))
        ttk.Button(browse_buttons_frame_input, text="浏览目录", command=self._browse_input_dir, width=10).pack(side=tk.LEFT)
        row_idx += 1

        ttk.Label(lf_io, text="输出PNG目录:").grid(row=row_idx, column=0, sticky=tk.W, padx=PAD_X_LABEL, pady=PAD_Y_ROW)
        ttk.Entry(lf_io, textvariable=self.vars["output_dir"], width=INPUT_WIDTH).grid(row=row_idx, column=1, sticky=tk.EW, padx=PAD_X_WIDGET, pady=PAD_Y_ROW)
        ttk.Button(lf_io, text="浏览目录", command=self._browse_output_dir, width=10).grid(row=row_idx, column=2, sticky=tk.E, padx=PAD_X_WIDGET, pady=PAD_Y_ROW)
        row_idx += 1
        
        ttk.Label(lf_io, text="输出文件名前缀:").grid(row=row_idx, column=0, sticky=tk.W, padx=PAD_X_LABEL, pady=PAD_Y_ROW)
        ttk.Entry(lf_io, textvariable=self.vars["prefix"], width=30).grid(row=row_idx, column=1, sticky=tk.W, padx=PAD_X_WIDGET, pady=PAD_Y_ROW) 
        row_idx += 1
        
        ttk.Label(lf_io, text="文件名模板:").grid(row=row_idx, column=0, sticky=tk.W, padx=PAD_X_LABEL, pady=PAD_Y_ROW)
        ttk.Entry(lf_io, textvariable=self.vars["output_filename_template"], width=INPUT_WIDTH).grid(row=row_idx, column=1, columnspan=2, sticky=tk.EW, padx=PAD_X_WIDGET, pady=PAD_Y_ROW)
        lf_io.columnconfigure(1, weight=1)
        row_idx += 1

        ttk.Label(lf_io, text="导出后操作:").grid(row=row_idx, column=0, sticky=tk.W, padx=PAD_X_LABEL, pady=PAD_Y_ROW)
        ttk.OptionMenu(lf_io, self.vars["post_export_action"], "open_file", "open_file", "open_folder", "both", "none").grid(row=row_idx, column=1, sticky=tk.W, padx=PAD_X_WIDGET, pady=PAD_Y_ROW)

        # --- 转换核心参数 ---
        lf_conversion = ttk.LabelFrame(self.config_scrollable_frame, text=" 转换核心参数 ", padding="10")
        lf_conversion.pack(fill=tk.X, padx=5, pady=GROUP_PAD_Y, expand=True)
        
        conv_param_frame = ttk.Frame(lf_conversion) 
        conv_param_frame.pack(fill=tk.X)
        conv_param_frame.columnconfigure(0, weight=0) 
        conv_param_frame.columnconfigure(1, weight=1) 
        conv_param_frame.columnconfigure(2, weight=0) 
        conv_param_frame.columnconfigure(3, weight=0) 

        ttk.Label(conv_param_frame, text="转换页面 (例: first, all, 1, 2-5):").grid(row=0, column=0, sticky=tk.W, padx=PAD_X_LABEL, pady=PAD_Y_ROW)
        ttk.Entry(conv_param_frame, textvariable=self.vars["pages"], width=30).grid(row=0, column=1, sticky=tk.EW, padx=PAD_X_WIDGET, pady=PAD_Y_ROW)
        ttk.Label(conv_param_frame, text="DPI:").grid(row=0, column=2, sticky=tk.W, padx=(20 + PAD_X_LABEL[0], PAD_X_LABEL[1]), pady=PAD_Y_ROW)
        ttk.Entry(conv_param_frame, textvariable=self.vars["dpi"], width=7).grid(row=0, column=3, sticky=tk.W, padx=PAD_X_WIDGET, pady=PAD_Y_ROW)

        conv_bool_frame = ttk.Frame(lf_conversion)
        conv_bool_frame.pack(fill=tk.X, pady=(PAD_Y_ROW[0]+2,0)) 
        ttk.Checkbutton(conv_bool_frame, text="覆盖已存在PNG", variable=self.vars["overwrite"]).pack(side=tk.LEFT, padx=PAD_X_LABEL, pady=PAD_Y_ROW)
        ttk.Checkbutton(conv_bool_frame, text="空运行模式 (Dry Run)", variable=self.vars["dry_run"]).pack(side=tk.LEFT, padx=PAD_X_LABEL, pady=PAD_Y_ROW)

        # --- 文件发现与筛选 ---
        lf_discovery = ttk.LabelFrame(self.config_scrollable_frame, text=" 文件发现与筛选 ", padding="10")
        lf_discovery.pack(fill=tk.X, padx=5, pady=GROUP_PAD_Y, expand=True)

        row_idx = 0
        discovery_bool_frame = ttk.Frame(lf_discovery)
        discovery_bool_frame.grid(row=row_idx, column=0, columnspan=2, sticky=tk.W, pady=PAD_Y_ROW)
        ttk.Checkbutton(discovery_bool_frame, text="递归处理子目录", variable=self.vars["recursive"]).pack(side=tk.LEFT, padx=PAD_X_LABEL)
        ttk.Checkbutton(discovery_bool_frame, text="保留目录结构 (递归时)", variable=self.vars["preserve_structure"]).pack(side=tk.LEFT, padx=PAD_X_LABEL)
        row_idx += 1

        ttk.Label(lf_discovery, text="包含关键字 (逗号分隔):").grid(row=row_idx, column=0, sticky=tk.W, padx=PAD_X_LABEL, pady=PAD_Y_ROW)
        ttk.Entry(lf_discovery, textvariable=self.vars["include_keywords"], width=INPUT_WIDTH).grid(row=row_idx, column=1, sticky=tk.EW, padx=PAD_X_WIDGET, pady=PAD_Y_ROW)
        row_idx += 1
        ttk.Label(lf_discovery, text="排除关键字 (逗号分隔):").grid(row=row_idx, column=0, sticky=tk.W, padx=PAD_X_LABEL, pady=PAD_Y_ROW)
        ttk.Entry(lf_discovery, textvariable=self.vars["exclude_keywords"], width=INPUT_WIDTH).grid(row=row_idx, column=1, sticky=tk.EW, padx=PAD_X_WIDGET, pady=PAD_Y_ROW)
        row_idx += 1
        ttk.Label(lf_discovery, text="正则表达式筛选文件名:").grid(row=row_idx, column=0, sticky=tk.W, padx=PAD_X_LABEL, pady=PAD_Y_ROW)
        ttk.Entry(lf_discovery, textvariable=self.vars["regex_filter"], width=INPUT_WIDTH).grid(row=row_idx, column=1, sticky=tk.EW, padx=PAD_X_WIDGET, pady=PAD_Y_ROW)
        lf_discovery.columnconfigure(1, weight=1)

        # --- 图像后处理 ---
        lf_postprocess = ttk.LabelFrame(self.config_scrollable_frame, text=" 图像后处理 ", padding="10")
        lf_postprocess.pack(fill=tk.X, padx=5, pady=GROUP_PAD_Y, expand=True)
        
        post_proc_frame = ttk.Frame(lf_postprocess) 
        post_proc_frame.pack(fill=tk.X)
        ttk.Checkbutton(post_proc_frame, text="转换为灰度图", variable=self.vars["grayscale"]).pack(side=tk.LEFT, padx=PAD_X_LABEL, pady=PAD_Y_ROW)
        ttk.Label(post_proc_frame, text="旋转角度:").pack(side=tk.LEFT, padx=(20 + PAD_X_LABEL[0], PAD_X_LABEL[1]), pady=PAD_Y_ROW)
        ttk.OptionMenu(post_proc_frame, self.vars["rotate"], self.current_config["rotate"], 0, 90, 180, 270, -90, -180, -270).pack(side=tk.LEFT, padx=PAD_X_WIDGET, pady=PAD_Y_ROW)

        # --- 日志级别控制 ---
        log_control_frame = ttk.Frame(self.config_scrollable_frame, padding=(0, 5, 0, 10))
        log_control_frame.pack(fill=tk.X, padx=5, pady=(10,5), expand=True)
        ttk.Label(log_control_frame, text="日志级别 (GUI):").pack(side=tk.LEFT, padx=PAD_X_LABEL)
        log_level_menu = ttk.OptionMenu(log_control_frame, self.vars["verbose_level"], self.current_config["verbose_level"], "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL", command=lambda _: self._update_logger_level())
        log_level_menu.pack(side=tk.LEFT, padx=PAD_X_WIDGET)
        
        # --- 全局样式 (放在最后，确保所有控件类型都已创建) ---
        style = ttk.Style(self)
        style.configure("Accent.TButton", font="-weight bold", padding=(10, 5))
        style.configure("TLabelFrame.Label", font="-weight bold") 


    def _browse_input_file(self):
        filepath = filedialog.askopenfilename(title="选择PDF文件", filetypes=(("PDF 文件", "*.pdf"), ("所有文件", "*.*")))
        if filepath: self.vars["input_path"].set(filepath)

    def _browse_input_dir(self):
        dirpath = filedialog.askdirectory(title="选择包含PDF的目录")
        if dirpath: self.vars["input_path"].set(dirpath)

    def _browse_output_dir(self):
        dirpath = filedialog.askdirectory(title="选择输出PNG的目录")
        if dirpath: self.vars["output_dir"].set(dirpath)

    def _get_current_settings_from_gui(self):
        settings = {}
        for key, var in self.vars.items():
            if isinstance(var, tk.BooleanVar): settings[key] = var.get()
            elif isinstance(var, tk.IntVar): settings[key] = var.get()
            else: 
                val_str = var.get()
                if key in ["include_keywords", "exclude_keywords"]:
                    settings[key] = [k.strip() for k in val_str.split(',') if k.strip()] if val_str else []
                elif key == "dpi":
                    try: settings[key] = int(val_str)
                    except ValueError:
                        logger.error(f"DPI值 '{val_str}' 无效，将使用默认值 {DEFAULT_CONFIG['dpi']}.")
                        settings[key] = DEFAULT_CONFIG['dpi']
                else: settings[key] = val_str
        return settings

    def _load_config_from_file(self):
        filepath = filedialog.askopenfilename(title="加载配置文件", filetypes=(("JSON 文件", "*.json"), ("所有文件", "*.*")))
        if not filepath: return
        try:
            with open(filepath, 'r', encoding='utf-8') as f: loaded_config = json.load(f)
            self.current_config = DEFAULT_CONFIG.copy()
            self.current_config.update(loaded_config) 
            self._update_gui_from_current_config()
            logger.info(f"已从 '{filepath}' 加载配置。")
            messagebox.showinfo("加载成功", f"已从 '{Path(filepath).name}' 加载配置。")
        except Exception as e:
            logger.error(f"加载配置文件 '{filepath}' 失败: {e}")
            messagebox.showerror("加载失败", f"加载配置文件失败: {e}")
            
    def _update_gui_from_current_config(self):
        for key, var_obj in self.vars.items():
            value_to_set = self.current_config.get(key, DEFAULT_CONFIG.get(key)) 
            if isinstance(var_obj, tk.BooleanVar): var_obj.set(bool(value_to_set))
            elif isinstance(var_obj, tk.IntVar): var_obj.set(int(value_to_set))
            elif key in ["include_keywords", "exclude_keywords"]: 
                var_obj.set(",".join(value_to_set) if isinstance(value_to_set, list) else "")
            else: var_obj.set(str(value_to_set))
        self._update_logger_level() 

    def _save_config_to_file(self):
        current_settings = self._get_current_settings_from_gui()
        filepath = filedialog.asksaveasfilename(title="保存当前配置", defaultextension=".json", filetypes=(("JSON 文件", "*.json"), ("所有文件", "*.*")))
        if not filepath: return
        try:
            with open(filepath, 'w', encoding='utf-8') as f: json.dump(current_settings, f, indent=4, ensure_ascii=False)
            logger.info(f"当前配置已保存到 '{filepath}'。")
            messagebox.showinfo("保存成功", f"配置已保存到 '{Path(filepath).name}'。")
        except Exception as e:
            logger.error(f"保存配置文件到 '{filepath}' 失败: {e}")
            messagebox.showerror("保存失败", f"保存配置文件失败: {e}")

    def _restore_defaults(self):
        if messagebox.askyesno("确认", "确定要恢复所有设置为默认值吗？"):
            self.current_config = DEFAULT_CONFIG.copy()
            self._update_gui_from_current_config()
            logger.info("所有设置已恢复为默认值。")

    def _request_stop_conversion(self):
        if self.conversion_thread and self.conversion_thread.is_alive():
            logger.info("终止转换请求已发送...")
            self.stop_conversion_event.set()
            self.stop_button.config(state=tk.DISABLED) # Disable stop button once pressed

    def _start_conversion_thread(self):
        self.start_button.config(state=tk.DISABLED, text="正在转换...")
        self.stop_button.config(state=tk.NORMAL) # Enable Stop button
        self.stop_conversion_event.clear() # Clear any previous stop signal

        self.log_text.config(state=tk.NORMAL); self.log_text.delete('1.0', tk.END); self.log_text.config(state=tk.DISABLED)
        settings = self._get_current_settings_from_gui()
        
        self.conversion_thread = threading.Thread(target=self._conversion_worker, args=(settings,), daemon=True)
        self.conversion_thread.start()

    def _finalize_conversion_ui(self):
        self.start_button.config(state=tk.NORMAL, text="开始转换")
        self.stop_button.config(state=tk.DISABLED)
        logger.info("UI已更新，准备进行下一次转换。")


    def _conversion_worker(self, settings):
        try:
            logger.info("转换任务开始...")
            logger.debug(f"当前转换设置: {json.dumps(settings, indent=2, ensure_ascii=False)}")
            input_path_str = settings["input_path"]
            if not input_path_str:
                logger.error("错误: 未指定输入路径。")
                self.after(0, lambda: messagebox.showerror("错误", "请输入PDF文件或目录路径。"))
                return

            input_path_obj = Path(input_path_str)
            if not input_path_obj.exists():
                logger.error(f"错误: 输入路径 '{input_path_obj}' 不存在。")
                self.after(0, lambda: messagebox.showerror("错误", f"输入路径 '{input_path_obj}' 不存在。"))
                return

            output_dir_base_str = settings["output_dir"]
            if output_dir_base_str: output_dir_base = Path(output_dir_base_str)
            else:
                output_dir_base = input_path_obj.parent / (f"{input_path_obj.name}_pngs" if input_path_obj.is_dir() else f"{input_path_obj.stem}_pngs")
            
            if not settings["dry_run"]:
                try: output_dir_base.mkdir(parents=True, exist_ok=True)
                except OSError as e:
                    logger.error(f"无法创建或访问输出根目录 '{output_dir_base.resolve()}': {e}")
                    self.after(0, lambda: messagebox.showerror("错误", f"无法创建输出目录: {e}"))
                    return
            logger.info(f"PNG图片将输出到根目录: {output_dir_base.resolve()}")

            pdf_files_to_process = discover_pdf_files(
                input_path_obj, settings["recursive"],
                settings["include_keywords"], settings["exclude_keywords"],
                settings["regex_filter"]
            )
            if not pdf_files_to_process:
                logger.warning("未找到符合条件的PDF文件进行处理。")
                if not self.stop_conversion_event.is_set(): # Only show if not stopped by user
                    self.after(0, lambda: messagebox.showinfo("提示", "未找到符合条件的PDF文件。"))
                return
            
            if self.stop_conversion_event.is_set():
                logger.info("转换任务在文件发现后被终止。")
                return

            logger.info(f"共找到 {len(pdf_files_to_process)} 个符合条件的PDF文件准备处理。")
            total_pngs_created, pdfs_processed_count = 0, 0
            input_root_for_structure = input_path_obj if input_path_obj.is_dir() else input_path_obj.parent

            for pdf_path in pdf_files_to_process:
                if self.stop_conversion_event.is_set():
                    logger.info("转换任务被用户终止。")
                    break 

                logger.info(f"开始处理PDF: '{pdf_path.resolve()}'")
                converted_for_this = convert_single_pdf(
                    pdf_path, output_dir_base, settings["pages"], settings["dpi"],
                    settings["overwrite"], settings["prefix"], settings["output_filename_template"],
                    settings["grayscale"], settings["rotate"], settings["dry_run"],
                    settings["preserve_structure"], input_root_for_structure,
                    stop_event=self.stop_conversion_event # Pass the event
                )
                if self.stop_conversion_event.is_set(): # Check after call, in case it was set during
                    logger.info(f"PDF '{pdf_path.name}' 的处理在转换函数调用后被终止。")
                    break

                if converted_for_this > 0:
                    total_pngs_created += converted_for_this
                    pdfs_processed_count += 1
                logger.info(f"PDF '{pdf_path.name}' 处理完成，{'计划' if settings['dry_run'] else '实际'}生成 {converted_for_this} 张图片。")

            summary_action = "计划生成" if settings["dry_run"] else "实际创建/覆盖"
            logger.info(f"\n--- {'空运行 ' if settings['dry_run'] else ''}转换总结 ---")
            logger.info(f"扫描的PDF文件总数 (通过筛选后): {len(pdf_files_to_process)}")
            logger.info(f"至少成功处理一页的PDF文件数: {pdfs_processed_count}")
            logger.info(f"PNG图片{summary_action}总数: {total_pngs_created}")
            if total_pngs_created > 0 or (settings["dry_run"] and pdfs_processed_count > 0):
                logger.info(f"所有输出已保存/计划保存在根目录: {output_dir_base.resolve()}")
            
            if self.stop_conversion_event.is_set():
                logger.info("转换流程已终止。")
                self.after(0, lambda: messagebox.showinfo("已终止", "转换任务已被用户终止。"))
            else:
                logger.info("转换流程结束。")
                msg_title, msg_body = "", ""
                if not settings['dry_run'] and total_pngs_created > 0 :
                     msg_title, msg_body = "完成", f"转换完成！共生成 {total_pngs_created} 张图片。"
                     
                     # 根据用户选择执行导出后操作
                     action = settings.get("post_export_action", "open_file")
                     if action != "none":
                         try:
                             if action in ["open_file", "both"] and pdfs_processed_count == 1:
                                 # 只处理了一个PDF文件，打开第一个生成的PNG文件
                                 first_pdf = pdf_files_to_process[0]
                                 first_png = output_dir_base / generate_output_filename(
                                     settings["output_filename_template"], first_pdf, 1, 1,
                                     settings["dpi"], settings["prefix"], input_root_for_structure
                                 )
                                 if first_png.exists():
                                     if platform.system() == "Windows":
                                         os.startfile(first_png)
                                     elif platform.system() == "Darwin":
                                         subprocess.run(["open", str(first_png)])
                                     elif platform.system() == "Linux":
                                         subprocess.run(["xdg-open", str(first_png)])
                             
                             if action in ["open_folder", "both"]:
                                 if platform.system() == "Windows":
                                     os.startfile(output_dir_base)
                                 elif platform.system() == "Darwin":
                                     subprocess.run(["open", str(output_dir_base)])
                                 elif platform.system() == "Linux":
                                     subprocess.run(["xdg-open", str(output_dir_base)])
                         except Exception as e:
                             logger.warning(f"执行导出后操作失败: {e}")
                             
                elif settings['dry_run'] and pdfs_processed_count > 0 :
                     msg_title, msg_body = "空运行完成", "空运行模式已完成，请检查日志。"
                elif not pdf_files_to_process: pass 
                else: 
                     msg_title, msg_body = "提示", "未生成新的图片（可能已存在或发生错误）。"
                if msg_title: self.after(0, lambda t=msg_title, b=msg_body: messagebox.showinfo(t,b))

        except Exception as e:
            logger.critical(f"转换过程中发生严重错误: {e}", exc_info=True)
            if not self.stop_conversion_event.is_set(): # Avoid double message if stopped
                self.after(0, lambda: messagebox.showerror("严重错误", f"发生严重错误: {e}"))
        finally:
            self.after(0, self._finalize_conversion_ui)


class QueueHandler(logging.Handler):
    def __init__(self, log_queue): super().__init__(); self.log_queue = log_queue
    def emit(self, record): self.log_queue.put(self.format(record))

if __name__ == "__main__":
    # 备份并重定向stderr以消除macOS警告
    original_stderr = sys.stderr
    sys.stderr = open(os.devnull, 'w')
    try:
        find_and_set_bundled_poppler_path()
        app = App() 
        if not any(isinstance(h, QueueHandler) for h in logger.handlers): 
            ch = logging.StreamHandler(sys.stderr); ch.setFormatter(logging.Formatter('%(levelname)s (fb): %(message)s')); ch.setLevel(logging.INFO) 
            logger.addHandler(ch); logger.info("GUI QueueHandler not found, added console fallback.")
        try: pass 
        except Exception as e: logger.debug(f"Icon load failed: {e}")
        app.mainloop()
    finally:
        # 恢复原始stderr
        sys.stderr = original_stderr
