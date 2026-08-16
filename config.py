import os
from pathlib import Path

# ---- 路径 ----
BASE_DIR = Path(__file__).parent
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "outputs"
LOG_DIR = BASE_DIR / "logs"

# ---- 文件大小限制 ----
MAX_UPLOAD_SIZE = int(os.environ.get("PDF_MAX_UPLOAD_SIZE", 200 * 1024 * 1024))  # 默认 200MB
MAX_FILES_PER_REQUEST = int(os.environ.get("PDF_MAX_FILES_PER_REQUEST", 20))  # 单次请求最多文件数

# ---- 预览 ----
PREVIEW_MAX_PAGES = int(os.environ.get("PDF_PREVIEW_MAX_PAGES", 200))
PREVIEW_DPI = int(os.environ.get("PDF_PREVIEW_DPI", 72))
PREVIEW_INITIAL_PAGES = int(os.environ.get("PDF_PREVIEW_INITIAL_PAGES", 50))  # 首批渲染页数（其余按需加载）
PREVIEW_CACHE_SECONDS = int(os.environ.get("PDF_PREVIEW_CACHE_SECONDS", 3600))  # 预览缓存保留 1h

# ---- COM 引擎 ----
COM_TIMEOUT = int(os.environ.get("PDF_COM_TIMEOUT", 120))

# ---- 文件保留 ----
FILE_RETENTION_SECONDS = int(os.environ.get("PDF_FILE_RETENTION", 86400))  # 24h
MAX_FILES_PER_DIR = int(os.environ.get("PDF_MAX_FILES_PER_DIR", 500))

# ---- CORS（默认关闭跨域，仅同源访问；需要跨域时用环境变量显式配置）----
CORS_ORIGINS = [o.strip() for o in os.environ.get("PDF_CORS_ORIGINS", "").split(",") if o.strip()]

# ---- 服务关闭鉴权 ----
SHUTDOWN_TOKEN = os.environ.get("PDF_SHUTDOWN_TOKEN", "")

# ---- PDF 压缩 ----
# 超过该大小的单张图片不重压缩（防止内存峰值过高），保留原图
COMPRESS_MAX_IMAGE_BYTES = int(os.environ.get("PDF_COMPRESS_MAX_IMAGE_BYTES", 50 * 1024 * 1024))

# ---- 日志 ----
LOG_LEVEL = os.environ.get("PDF_LOG_LEVEL", "INFO")
LOG_MAX_BYTES = 5 * 1024 * 1024  # 5MB
LOG_BACKUP_COUNT = 3

# ---- 图片格式 ----
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff", ".tif", ".ico"}

FORMAT_MAP = {
    "png": "PNG", "jpg": "JPEG", "jpeg": "JPEG", "webp": "WEBP",
    "bmp": "BMP", "gif": "GIF", "tiff": "TIFF", "ico": "ICO",
}

SAVE_OPTIONS = {
    "jpg": {"quality": 100, "subsampling": 0},
    "jpeg": {"quality": 100, "subsampling": 0},
    "webp": {"lossless": True},
    "tiff": {"compression": None},
}

# ---- PDF 压缩级别 ----
COMPRESSION_LEVELS = {
    "light": {
        "label": "轻度压缩",
        "desc": "保持高清品质，最小程度压缩",
        "max_dim": 4000,
        "jpeg_quality": 85,
        "dpi_threshold": 300,
        "garbage": 3,
        "deflate": True,
        "clean": False,
    },
    "recommended": {
        "label": "推荐压缩",
        "desc": "均衡质量与文件大小（推荐）",
        "max_dim": 2200,
        "jpeg_quality": 55,
        "dpi_threshold": 180,
        "garbage": 4,
        "deflate": True,
        "clean": True,
    },
    "extreme": {
        "label": "极致压缩",
        "desc": "最大化压缩，文件最小体积",
        "max_dim": 1440,
        "jpeg_quality": 30,
        "dpi_threshold": 120,
        "garbage": 4,
        "deflate": True,
        "clean": True,
    },
}
