#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import json
import logging
import subprocess
import re
from pathlib import Path
from pdf2image import convert_from_path, pdfinfo_from_path
from PIL import Image # Pillow for image processing
import threading
import platform
import argparse

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

def generate_unique_filename(original_path):
    """Generates a unique filename by appending a numerical suffix if the file already exists."""
    path = Path(original_path)
    if not path.exists():
        return path

    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    counter = 1
    while True:
        new_name = f"{stem}_copy_{counter}{suffix}"
        new_path = parent / new_name
        if not new_path.exists():
            return new_path
        counter += 1

def convert_single_pdf(pdf_path, output_dir_base, pages_to_convert_str, dpi, overwrite, prefix,
                       filename_template, grayscale, rotate_angle, dry_run,
                       preserve_structure=False, input_root_dir=None, stop_event=None): # Added stop_event
    global BUNDLED_POPPLER_PATH
    generated_image_paths = [] # Initialize list to store generated image paths
    try:
        pdf_info = pdfinfo_from_path(pdf_path, poppler_path=BUNDLED_POPPLER_PATH)
        total_pages = pdf_info.get("Pages", 0)
        if total_pages == 0:
            logger.warning(f"无法获取 '{pdf_path.name}' 的页数，可能文件已损坏或非标准PDF。跳过。")
            return [] # Return empty list
    except Exception as e:
        logger.error(f"读取PDF信息失败 '{pdf_path.name}': {e}。跳过。")
        return [] # Return empty list

    if stop_event and stop_event.is_set(): return [] # Check before processing pages

    pages_list = parse_page_ranges(pages_to_convert_str, total_pages)
    if pages_list is None: return []

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
            # Generate a unique filename instead of skipping
            original_output_png_path = output_png_path # Store original for logging
            output_png_path = generate_unique_filename(output_png_path)
            logger.info(f"文件 '{original_output_png_path.name}' 已存在，将保存为新文件: {output_png_path.name}")

        logger.info(f"准备转换: '{pdf_path.name}' (第 {page_num}/{total_pages} 页) -> '{output_png_path.resolve()}'")

        if dry_run:
            logger.info(f"[空运行] 将转换并保存到: {output_png_path.resolve()}")
            generated_image_paths.append(output_png_path.resolve().as_posix()) # Add to list even in dry run
            continue

        try:
            # Explicitly convert Path object to string for convert_from_path
            logger.debug(f"Calling convert_from_path with: path='{str(pdf_path)}', dpi={dpi}, first_page={page_num}, last_page={page_num}, poppler_path='{BUNDLED_POPPLER_PATH}'")
            images = convert_from_path(str(pdf_path), dpi=dpi, first_page=page_num, last_page=page_num, fmt='png', poppler_path=BUNDLED_POPPLER_PATH)
            if images:
                image = images[0]
                if grayscale:
                    image = image.convert("L")
                if rotate_angle != 0:
                    image = image.rotate(rotate_angle, expand=True)
                
                try:
                    image.save(output_png_path, 'PNG')
                    logger.info(f"成功保存: {output_png_path.resolve()}")
                    generated_image_paths.append(output_png_path.resolve().as_posix()) # Add to list
                except Exception as save_e:
                    logger.error(f"保存图片 '{output_png_path.name}' 时发生错误: {save_e}")
            else:
                logger.error(f"未能从 '{pdf_path.name}' 第 {page_num} 页生成图像。")
        except Exception as e:
            logger.error(f"转换 '{pdf_path.name}' 第 {page_num} 页时发生错误: {e}", exc_info=True) # Add exc_info for full traceback
    return generated_image_paths # Return the list of generated image paths

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

if __name__ == "__main__":
    # 备份并重定向stderr以消除macOS警告
    original_stderr = sys.stderr
    sys.stderr = open(os.devnull, 'w')
    try:
        find_and_set_bundled_poppler_path()

        parser = argparse.ArgumentParser(description="Convert PDF to PNG images")
        parser.add_argument("--input_path", required=True, help="Path to PDF file or directory")
        parser.add_argument("--output_dir", required=True, help="Path to output directory")
        parser.add_argument("--pages", default="first", help="Pages to convert (e.g., first, all, 1, 2-5)")
        parser.add_argument("--dpi", type=int, default=300, help="DPI of output images")
        parser.add_argument("--prefix", default="", help="Prefix for output filenames")
        parser.add_argument("--output_filename_template", default="{pdf_name}_page_{page_num}.png", help="Template for output filenames")
        parser.add_argument("--post_export_action", default="open_file", help="Action after export (open_file, open_folder, both, none)")
        parser.add_argument("--recursive", action="store_true", help="Recursively process subdirectories")
        parser.add_argument("--preserve_structure", action="store_true", help="Preserve directory structure (recursive only)")
        parser.add_argument("--include_keywords", default="", help="Comma-separated keywords to include in filenames")
        parser.add_argument("--exclude_keywords", default="", help="Comma-separated keywords to exclude in filenames")
        parser.add_argument("--regex_filter", default="", help="Regular expression to filter filenames")
        parser.add_argument("--grayscale", action="store_true", help="Convert to grayscale")
        parser.add_argument("--rotate", type=int, default=0, help="Rotation angle")
        #parser.add_argument("--overwrite", action="store_true", help="Overwrite existing PNG files") # Removed overwrite
        parser.add_argument("--dry_run", action="store_true", help="Dry run mode")
        parser.add_argument("--verbose_level", default="INFO", help="Verbose level (DEBUG, INFO, WARNING, ERROR, CRITICAL)")

        args = parser.parse_args()

        # Configure logging level
        logger.setLevel(args.verbose_level.upper())

        # Process PDF conversion
        input_path_obj = Path(args.input_path)
        output_dir_base = Path(args.output_dir)

        pdf_files_to_process = discover_pdf_files(
            input_path_obj, args.recursive,
            [k.strip() for k in args.include_keywords.split(',') if k.strip()],
            [k.strip() for k in args.exclude_keywords.split(',') if k.strip()],
            args.regex_filter
        )

        if not pdf_files_to_process:
            logger.warning("未找到符合条件的PDF文件进行处理。")
            sys.exit(0)

        logger.info(f"共找到 {len(pdf_files_to_process)} 个符合条件的PDF文件准备处理。")
        total_pngs_created, pdfs_processed_count = 0, 0
        input_root_for_structure = input_path_obj if input_path_obj.is_dir() else input_path_obj.parent

        for pdf_path in pdf_files_to_process:
            logger.info(f"开始处理PDF: '{pdf_path.resolve()}'")
            converted_for_this = convert_single_pdf(
                pdf_path, output_dir_base, args.pages, args.dpi,
                True, args.prefix, args.output_filename_template, # Set overwrite to True
                args.grayscale, args.rotate, args.dry_run,
                args.preserve_structure, input_root_for_structure,
                stop_event=None
            )

            if converted_for_this > 0:
                total_pngs_created += converted_for_this
                pdfs_processed_count += 1
            logger.info(f"PDF '{pdf_path.name}' 处理完成，{'计划' if args.dry_run else '实际'}生成 {converted_for_this} 张图片。")

        summary_action = "计划生成" if args.dry_run else "实际创建/覆盖"
        logger.info(f"\n--- {'空运行 ' if args.dry_run else ''}转换总结 ---")
        logger.info(f"扫描的PDF文件总数 (通过筛选后): {len(pdf_files_to_process)}")
        logger.info(f"至少成功处理一页的PDF文件数: {pdfs_processed_count}")
        logger.info(f"PNG图片{summary_action}总数: {total_pngs_created}")
        if total_pngs_created > 0 or (args.dry_run and pdfs_processed_count > 0):
            logger.info(f"所有输出已保存/计划保存在根目录: {output_dir_base.resolve()}")

        logger.info("转换流程结束。")


    finally:
        # 恢复原始stderr
        sys.stderr = original_stderr
