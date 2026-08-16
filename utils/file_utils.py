import re
import shutil
import time
from pathlib import Path
import logging

from config import MAX_UPLOAD_SIZE, FILE_RETENTION_SECONDS, MAX_FILES_PER_DIR

_logger = logging.getLogger("pdf-tools")

# Windows 保留文件名（不能用作用户可控的文件名）
_WINDOWS_RESERVED = {
    "con", "prn", "aux", "nul",
    *[f"com{i}" for i in range(1, 10)],
    *[f"lpt{i}" for i in range(1, 10)],
}


def safe_unlink(path):
    """安全删除文件，失败不抛异常"""
    try:
        if path.exists():
            path.unlink()
    except Exception:
        _logger.debug("无法删除文件: %s", path, exc_info=True)


def safe_rmdir(path):
    """安全删除目录，失败不抛异常"""
    try:
        if path.exists():
            shutil.rmtree(str(path), ignore_errors=True)
    except Exception:
        _logger.debug("无法删除目录: %s", path, exc_info=True)


def sanitize_stem(name, fallback="file", max_len=80):
    """清理用户文件名，返回安全的文件 stem。

    去除目录部分、扩展名、非法字符与 Windows 保留名，
    防止路径注入（如 "..\\..\\evil.pdf" 逃逸输出目录）。
    """
    if not name:
        return fallback
    name = str(name).replace("\\", "/")
    stem = Path(name).name          # 仅保留最后一段，去掉目录
    stem = Path(stem).stem          # 去掉扩展名
    stem = re.sub(r'[\x00-\x1f<>:"/\\|?*]', "_", stem).strip(" .")
    if stem.lower() in _WINDOWS_RESERVED:
        stem = f"_{stem}"
    if not stem:
        stem = fallback
    stem = stem[:max_len].rstrip(" .")
    return stem or fallback


def zip_member_name(name):
    """将用户文件名转为 zip 包内安全的成员名（仅保留文件名部分）"""
    return Path(str(name).replace("\\", "/")).name or "file"


def read_upload(file, max_size=None):
    """同步读取上传文件内容，校验大小和空内容"""
    from fastapi import HTTPException

    if max_size is None:
        max_size = MAX_UPLOAD_SIZE
    content = file.file.read()
    if len(content) > max_size:
        limit_mb = max_size / 1024 / 1024
        raise HTTPException(413, f"文件过大，最大 {limit_mb:.0f}MB")
    if not content:
        raise HTTPException(400, "上传文件为空")
    return content


def cleanup_old_files(*dirs):
    """清理旧文件（超过保留期限）"""
    for d in dirs:
        if not d.exists():
            continue
        for f in list(d.iterdir()):
            try:
                if time.time() - f.stat().st_mtime > FILE_RETENTION_SECONDS:
                    if f.is_file():
                        f.unlink()
                    elif f.is_dir():
                        shutil.rmtree(f, ignore_errors=True)
            except Exception:
                _logger.warning("清理文件失败: %s", f)


def limit_file_count(*dirs):
    """限制目录文件数，超过上限时删除最旧的文件"""
    for d in dirs:
        if not d.exists():
            continue
        files = sorted(d.iterdir(), key=lambda x: x.stat().st_mtime)
        if len(files) > MAX_FILES_PER_DIR:
            excess = len(files) - (MAX_FILES_PER_DIR - 200)
            for f in files[:excess]:
                try:
                    if f.is_file():
                        f.unlink()
                    elif f.is_dir():
                        shutil.rmtree(f, ignore_errors=True)
                except Exception:
                    _logger.warning("清理超额文件失败: %s", f)


# ---- 文件类型 magic bytes 校验 ----

_MAGIC_SIGNATURES = {
    ".pdf": [(0, b"%PDF")],
    ".docx": [(0, b"PK\x03\x04")],
    ".pptx": [(0, b"PK\x03\x04")],
    ".doc": [(0, b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")],  # OLE2
    ".ppt": [(0, b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")],  # OLE2
    ".jpg": [(0, b"\xff\xd8\xff")],
    ".jpeg": [(0, b"\xff\xd8\xff")],
    ".png": [(0, b"\x89PNG\r\n\x1a\n")],
    ".gif": [(0, b"GIF87a"), (0, b"GIF89a")],
    ".bmp": [(0, b"BM")],
    ".webp": [(0, b"RIFF"), (8, b"WEBP")],
    ".tiff": [(0, b"II*\x00"), (0, b"MM\x00*")],
    ".tif": [(0, b"II*\x00"), (0, b"MM\x00*")],
    ".ico": [(0, b"\x00\x00\x01\x00")],
}


def validate_file_signature(filename: str, content: bytes) -> None:
    """通过 magic bytes 校验文件真实类型，不匹配则抛出 HTTPException"""
    from fastapi import HTTPException

    ext = Path(filename).suffix.lower()
    signatures = _MAGIC_SIGNATURES.get(ext)
    if signatures is None:
        raise HTTPException(400, f"不支持的扩展名校验: {ext}")

    for offset, expected in signatures:
        if len(content) < offset + len(expected):
            continue
        if content[offset:offset + len(expected)] == expected:
            return  # 校验通过

    raise HTTPException(400, f"文件扩展名与内容不匹配: {filename}")
