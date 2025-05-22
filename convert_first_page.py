import os
from pdf2image import convert_from_path
from pathlib import Path

# --- 配置开始 ---
# 新的PDF文件夹路径
PDF_SOURCE_DIR = Path("/Users/kawarox/文件-本地/汇总/05项目证明")

# 输出PNG图片的文件夹路径 (将创建在源目录旁边)
OUTPUT_PNG_DIR = PDF_SOURCE_DIR.parent / (PDF_SOURCE_DIR.name + "_PNG_第一页")

# DPI (Dots Per Inch) - 图像分辨率
DPI = 200
# --- 配置结束 ---

def convert_pdfs_to_pngs():
    """
    遍历PDF_SOURCE_DIR中的所有PDF文件，
    将其第一页转换为PNG，并保存到OUTPUT_PNG_DIR。
    """
    if not PDF_SOURCE_DIR.exists() or not PDF_SOURCE_DIR.is_dir():
        print(f"错误: 指定的PDF源目录不存在或不是一个目录: {PDF_SOURCE_DIR}")
        print("请检查脚本中的 PDF_SOURCE_DIR 配置。")
        return

    OUTPUT_PNG_DIR.mkdir(parents=True, exist_ok=True)
    print(f"PDF源目录: {PDF_SOURCE_DIR}")
    print(f"输出目录: {OUTPUT_PNG_DIR}")

    pdf_files_found = 0
    converted_count = 0

    for item in PDF_SOURCE_DIR.iterdir():
        if item.is_file() and item.suffix.lower() == '.pdf':
            pdf_files_found += 1
            
            pdf_path = item
            output_png_filename = item.stem + ".png"
            output_png_path = OUTPUT_PNG_DIR / output_png_filename

            print(f"\n正在处理: {pdf_path.name}")

            if output_png_path.exists():
                print(f"警告: 文件 {output_png_path.name} 已存在于输出目录，将跳过。")
                continue

            try:
                images = convert_from_path(
                    pdf_path,
                    dpi=DPI,
                    first_page=1,
                    last_page=1,
                    fmt='png',
                    poppler_path=None
                )

                if images:
                    images[0].save(output_png_path, 'PNG')
                    print(f"成功: {pdf_path.name} -> {output_png_path.name}")
                    converted_count += 1
                else:
                    print(f"错误: 未能从 {pdf_path.name} 生成图像。")

            except Exception as e:
                print(f"错误: 处理 {pdf_path.name} 时发生错误: {e}")
        # elif item.is_dir():
            # print(f"跳过子目录: {item.name}") # 可选
        # elif item.is_file():
            # print(f"跳过非PDF文件: {item.name}") # 可选

    print(f"\n--- 转换完成 ---")
    print(f"共扫描到 {pdf_files_found} 个PDF文件。")
    print(f"成功转换 {converted_count} 个PDF的第一页。")
    if converted_count > 0:
        print(f"PNG图片已保存到: {OUTPUT_PNG_DIR}")
    elif pdf_files_found > 0:
        print(f"没有新的图片被转换（可能已存在或发生错误）。")
    else:
        print(f"在目录 {PDF_SOURCE_DIR} 中未找到PDF文件。")

if __name__ == "__main__":
    convert_pdfs_to_pngs()
