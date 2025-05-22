# Alchemist - PDF转PNG转换工具

![GUI界面截图](https://via.placeholder.com/800x500.png?text=GUI+Preview) <!-- 实际使用时请替换为截图 -->

跨平台的PDF转PNG转换工具，提供直观的图形界面和丰富的转换选项。

## 🌟 主要功能
- 可视化选择PDF文件/目录
- 灵活页面选择（单页/范围/all/first）
- 可调DPI（最高600dpi）
- 智能路径保留（保留源文件目录结构）
- 自定义文件名模板
- 图像后处理（旋转/灰度转换）
- 空运行模式（Dry Run）
- 多主题支持（内置10+ UI主题）
- 实时日志监控

## 🛠️ 安装指南

### 前置要求
- Python 3.8+
- [Poppler](https://poppler.freedesktop.org/) （各系统安装方式如下）

**安装Poppler**:
```bash
# macOS
brew install poppler

# Windows
# 1. 下载最新版：https://github.com/oschwartz10612/poppler-windows/releases
# 2. 将bin目录加入PATH环境变量

# Ubuntu/Debian
sudo apt-get install poppler-utils
```


