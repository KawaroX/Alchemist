from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import json
from pathlib import Path
import logging
import threading
import sys

# Import the pdf_converter module
# Assuming pdf_converter.py is in the same directory or accessible via PYTHONPATH
import pdf_converter

app = Flask(__name__)
CORS(app)

# Global variable for the stop event
stop_conversion_event = threading.Event()

# Custom logging handler to capture messages
class LogCaptureHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.log_messages = []
        self.formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%H:%M:%S')

    def emit(self, record):
        self.log_messages.append({
            'level': record.levelname,
            'message': self.format(record)
        })

    def get_logs(self):
        return self.log_messages

    def clear_logs(self):
        self.log_messages = []

log_capture_handler = LogCaptureHandler()
# Add the handler to the pdf_converter's logger
pdf_converter.logger.addHandler(log_capture_handler)
pdf_converter.logger.setLevel(logging.DEBUG) # Ensure all levels are captured

@app.route('/convert', methods=['POST'])
def convert_pdf():
    log_capture_handler.clear_logs() # Clear logs from previous runs
    stop_conversion_event.clear() # Clear stop signal for new conversion

    try:
        data = request.get_json()
        input_path_str = data.get('input_path')
        output_dir_str = data.get('output_dir')
        pages = data.get('pages', 'first')
        dpi = data.get('dpi', 300)
        prefix = data.get('prefix', '')
        output_filename_template = data.get('output_filename_template', "{pdf_name}_page_{page_num}.png")
        post_export_action = data.get('post_export_action', 'open_file')
        recursive = data.get('recursive', False)
        preserve_structure = data.get('preserve_structure', False)
        include_keywords = data.get('include_keywords', '')
        exclude_keywords = data.get('exclude_keywords', '')
        regex_filter = data.get('regex_filter', '')
        grayscale = data.get('grayscale', False)
        rotate = data.get('rotate', 0)
        dry_run = data.get('dry_run', False) # Assuming dry_run can be passed from frontend
        overwrite = data.get('overwrite', False) # Assuming overwrite can be passed from frontend

        # Convert comma-separated strings to lists
        include_keywords_list = [k.strip() for k in include_keywords.split(',') if k.strip()]
        exclude_keywords_list = [k.strip() for k in exclude_keywords.split(',') if k.strip()]

        input_path_obj = Path(input_path_str)
        if not input_path_obj.exists():
            pdf_converter.logger.error(f"错误: 输入路径 '{input_path_obj}' 不存在。")
            return jsonify({'logs': log_capture_handler.get_logs(), 'status': 'error'}), 400

        output_dir_base = Path(output_dir_str) if output_dir_str else \
                          input_path_obj.parent / (f"{input_path_obj.name}_PNGs" if input_path_obj.is_dir() else f"{input_path_obj.stem}_PNGs")

        if not dry_run:
            try:
                output_dir_base.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                pdf_converter.logger.error(f"无法创建或访问输出根目录 '{output_dir_base.resolve()}': {e}")
                return jsonify({'logs': log_capture_handler.get_logs(), 'status': 'error'}), 500
        pdf_converter.logger.info(f"PNG图片将输出到根目录: {output_dir_base.resolve()}")

        pdf_files_to_process = pdf_converter.discover_pdf_files(
            input_path_obj, recursive,
            include_keywords_list, exclude_keywords_list,
            regex_filter
        )

        if not pdf_files_to_process:
            pdf_converter.logger.warning("未找到符合条件的PDF文件进行处理。")
            return jsonify({'logs': log_capture_handler.get_logs(), 'status': 'warning'}), 200

        pdf_converter.logger.info(f"共找到 {len(pdf_files_to_process)} 个符合条件的PDF文件准备处理。")
        all_generated_image_paths = [] # List to collect all generated image paths
        pdfs_processed_count = 0
        input_root_for_structure = input_path_obj if input_path_obj.is_dir() else input_path_obj.parent

        for pdf_path in pdf_files_to_process:
            if stop_conversion_event.is_set():
                pdf_converter.logger.info("转换任务被用户终止。")
                break

            pdf_converter.logger.info(f"开始处理PDF: '{pdf_path.resolve()}'")
            # convert_single_pdf now returns a list of generated image paths
            generated_paths_for_this_pdf = pdf_converter.convert_single_pdf(
                pdf_path, output_dir_base, pages, dpi,
                overwrite, prefix, output_filename_template,
                grayscale, rotate, dry_run,
                preserve_structure, input_root_for_structure,
                stop_event=stop_conversion_event
            )

            if generated_paths_for_this_pdf:
                all_generated_image_paths.extend(generated_paths_for_this_pdf)
                pdfs_processed_count += 1
            pdf_converter.logger.info(f"PDF '{pdf_path.name}' 处理完成，{'计划' if dry_run else '实际'}生成 {len(generated_paths_for_this_pdf)} 张图片。")

        summary_action = "计划生成" if dry_run else "实际创建/覆盖"
        pdf_converter.logger.info(f"\n--- {'空运行 ' if dry_run else ''}转换总结 ---")
        pdf_converter.logger.info(f"扫描的PDF文件总数 (通过筛选后): {len(pdf_files_to_process)}")
        pdf_converter.logger.info(f"至少成功处理一页的PDF文件数: {pdfs_processed_count}")
        pdf_converter.logger.info(f"PNG图片{summary_action}总数: {len(all_generated_image_paths)}")
        if all_generated_image_paths or (dry_run and pdfs_processed_count > 0):
            pdf_converter.logger.info(f"所有输出已保存/计划保存在根目录: {output_dir_base.resolve()}")

        # Determine the output_path based on post_export_action
        final_output_path = None
        if post_export_action == "open_file":
            if len(all_generated_image_paths) == 1:
                final_output_path = all_generated_image_paths[0] # Return the single image path
                pdf_converter.logger.info(f"将返回单个图片路径用于打开: {final_output_path}")
            elif all_generated_image_paths:
                # If multiple images generated, but user chose "open_file",
                # we default to opening the folder, or the first image.
                # For now, let's open the folder if multiple images are generated.
                final_output_path = output_dir_base.resolve().as_posix()
                pdf_converter.logger.info(f"生成了多张图片，但选择了'打开文件'，将返回输出目录: {final_output_path}")
            else:
                # No images generated, but user chose "open_file", still open folder if it exists
                final_output_path = output_dir_base.resolve().as_posix()
                pdf_converter.logger.info(f"未生成图片，但选择了'打开文件'，将返回输出目录: {final_output_path}")
        elif post_export_action == "open_folder":
            final_output_path = output_dir_base.resolve().as_posix()
            pdf_converter.logger.info(f"选择了'打开文件夹'，将返回输出目录: {final_output_path}")
        else: # "do_nothing" or other cases
            final_output_path = output_dir_base.resolve().as_posix() if all_generated_image_paths else None
            pdf_converter.logger.info(f"选择了'不执行任何操作'或默认，将返回输出目录（如果存在图片）: {final_output_path}")

        if stop_conversion_event.is_set():
            pdf_converter.logger.info("转换流程已终止。")
            return jsonify({'logs': log_capture_handler.get_logs(), 'status': 'stopped', 'output_path': final_output_path}), 200
        else:
            pdf_converter.logger.info("转换流程结束。")
            return jsonify({'logs': log_capture_handler.get_logs(), 'status': 'completed', 'output_path': final_output_path}), 200

    except Exception as e:
        pdf_converter.logger.critical(f"转换过程中发生严重错误: {e}", exc_info=True)
        return jsonify({'logs': log_capture_handler.get_logs(), 'status': 'critical_error'}), 500

@app.route('/stop', methods=['POST'])
def stop_conversion():
    stop_conversion_event.set()
    pdf_converter.logger.info("终止转换请求已发送。")
    return jsonify({'message': 'Conversion stop signal sent.'}), 200

if __name__ == '__main__':
    # Ensure Poppler path is set when running Flask directly for testing
    pdf_converter.find_and_set_bundled_poppler_path()
    app.run(debug=True, host='0.0.0.0', port=5003)
