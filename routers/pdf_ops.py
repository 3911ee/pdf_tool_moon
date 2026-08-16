"""PDF 操作端点：合并、拆分、预览、删页、压缩

说明：所有处理端点均为同步 def（线程池执行），
避免 CPU 密集任务阻塞事件循环。
"""
import io
import re
import time
import uuid
import base64
import zipfile
import logging
from pathlib import Path

from fastapi import APIRouter, File, UploadFile, HTTPException
from pypdf import PdfReader, PdfWriter
from PIL import Image
import fitz

from config import (
    UPLOAD_DIR, OUTPUT_DIR, COMPRESSION_LEVELS,
    PREVIEW_MAX_PAGES, PREVIEW_DPI, PREVIEW_INITIAL_PAGES, PREVIEW_CACHE_SECONDS,
    MAX_FILES_PER_REQUEST,
)
from engines.pdf_engine import compress_pdf_file, parse_page_numbers
from utils.file_utils import (
    safe_unlink, safe_rmdir, read_upload,
    validate_file_signature, sanitize_stem,
)

router = APIRouter()
_logger = logging.getLogger("pdf-tools")

_PREVIEW_ID_RE = re.compile(r"^[0-9a-f]{8,64}$")


# ---- PDF 合并 ----

@router.post("/api/merge-pdf")
def merge_pdfs(files: list[UploadFile] = File(...)):
    if not files or len(files) < 2:
        raise HTTPException(400, "请至少上传 2 个 PDF 文件")
    if len(files) > MAX_FILES_PER_REQUEST:
        raise HTTPException(400, f"单次最多上传 {MAX_FILES_PER_REQUEST} 个文件")
    for f in files:
        if Path(f.filename or "x").suffix.lower() != ".pdf":
            raise HTTPException(400, f"仅支持 PDF 文件: {f.filename}")

    safe_stem = sanitize_stem(files[0].filename or "pdf", fallback="pdf")
    download_id = f"{safe_stem}_merged_{uuid.uuid4().hex[:8]}"
    uid = uuid.uuid4().hex
    saved = []

    try:
        for i, f in enumerate(files):
            content = read_upload(f)
            validate_file_signature(f.filename or f"file_{i}", content)
            p = UPLOAD_DIR / f"{uid}_{i}.pdf"
            p.write_bytes(content)
            saved.append(p)

        out = OUTPUT_DIR / f"{download_id}.pdf"
        w = PdfWriter()
        try:
            for p in saved:
                r = PdfReader(str(p))
                try:
                    for pg in r.pages:
                        w.add_page(pg)
                finally:
                    r.close()
            w.write(str(out))
        finally:
            w.close()
    except HTTPException:
        raise
    except Exception as e:
        _logger.error("PDF 合并失败: %s", e, exc_info=True)
        raise HTTPException(500, f"PDF 合并失败: {e}")
    finally:
        for p in saved:
            safe_unlink(p)

    return {
        "success": True, "download_id": download_id,
        "original_name": f"合并 {len(files)} 个 PDF", "download_ext": "pdf",
    }


# ---- PDF 拆分 ----

@router.post("/api/split-pdf")
def split_pdf(file: UploadFile = File(...), positions: str = ""):
    if Path(file.filename or "x").suffix.lower() != ".pdf":
        raise HTTPException(400, "仅支持 PDF 文件")
    content = read_upload(file)
    validate_file_signature(file.filename, content)

    safe_stem = sanitize_stem(file.filename)
    download_id = f"{safe_stem}_split_{uuid.uuid4().hex[:8]}"
    uid = uuid.uuid4().hex
    inp = UPLOAD_DIR / f"{uid}.pdf"
    inp.write_bytes(content)

    d = OUTPUT_DIR / uid
    d.mkdir(exist_ok=True)
    r = None
    pc = 0

    try:
        r = PdfReader(str(inp))
        total = len(r.pages)
        sp = []
        if positions.strip():
            for p in positions.split(","):
                p = p.strip()
                if p:
                    n = int(p)
                    if n < 1 or n > total:
                        raise HTTPException(400, f"页码超出范围: {n}（共 {total} 页）")
                    sp.append(n)
            sp = sorted(set(sp))

        if not sp:
            for i, pg in enumerate(r.pages):
                w = PdfWriter()
                try:
                    w.add_page(pg)
                    w.write(str(d / f"page_{i + 1}.pdf"))
                finally:
                    w.close()
            pc = total
        else:
            ranges = []
            start = 1
            for pos in sp:
                ranges.append((start, pos))
                start = pos + 1
            if start <= total:
                ranges.append((start, total))
            for idx, (s, e) in enumerate(ranges, 1):
                w = PdfWriter()
                try:
                    for i in range(s - 1, e):
                        w.add_page(r.pages[i])
                    label = f"page_{s}.pdf" if s == e else f"pages_{s}-{e}.pdf"
                    w.write(str(d / f"{idx:02d}_{label}"))
                finally:
                    w.close()
            pc = len(ranges)
    except HTTPException:
        raise
    except Exception as e:
        _logger.error("PDF 拆分失败: %s", e, exc_info=True)
        raise HTTPException(500, f"PDF 拆分失败: {e}")
    finally:
        safe_unlink(inp)
        if r:
            try:
                r.close()
            except Exception:
                _logger.debug("PdfReader 关闭失败", exc_info=True)

    zip_p = OUTPUT_DIR / f"{download_id}.zip"
    try:
        with zipfile.ZipFile(str(zip_p), "w", zipfile.ZIP_DEFLATED) as zf:
            for f in sorted(d.iterdir(), key=lambda x: x.name):
                zf.write(str(f), f.name)
                safe_unlink(f)
    finally:
        safe_rmdir(d)

    return {
        "success": True, "download_id": download_id,
        "original_name": f"拆分 {pc} 份", "download_ext": "zip",
    }


# ---- PDF 预览（首批渲染 + 按需加载） ----

def _render_page(doc, index):
    """渲染单页为 base64 JPEG 缩略图"""
    page = doc[index]
    pix = page.get_pixmap(dpi=PREVIEW_DPI)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    try:
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=75)
        b64 = base64.b64encode(buf.getvalue()).decode()
        return {
            "num": index + 1, "width": pix.width, "height": pix.height,
            "src": f"data:image/jpeg;base64,{b64}",
        }
    finally:
        img.close()


def _cleanup_preview_cache():
    """清理过期的预览缓存文件"""
    try:
        now = time.time()
        for p in UPLOAD_DIR.glob("preview_*.pdf"):
            try:
                if now - p.stat().st_mtime > PREVIEW_CACHE_SECONDS:
                    p.unlink()
            except Exception:
                pass
    except Exception:
        _logger.debug("预览缓存清理失败", exc_info=True)


@router.post("/api/preview-pages")
def preview_pages(file: UploadFile = File(...)):
    """上传 PDF 并返回首批缩略图；其余页面经 /api/preview-page 按需加载"""
    if Path(file.filename or "x").suffix.lower() != ".pdf":
        raise HTTPException(400, "仅支持 PDF 文件")
    content = read_upload(file)
    validate_file_signature(file.filename, content)

    uid = uuid.uuid4().hex
    inp = UPLOAD_DIR / f"preview_{uid}.pdf"
    inp.write_bytes(content)
    _cleanup_preview_cache()

    try:
        doc = fitz.open(str(inp))
        try:
            total = len(doc)
            limit = min(total, PREVIEW_MAX_PAGES)
            initial = min(limit, PREVIEW_INITIAL_PAGES)
            pages = [_render_page(doc, i) for i in range(initial)]
        finally:
            doc.close()
    except Exception as e:
        safe_unlink(inp)
        _logger.error("预览生成失败: %s", e, exc_info=True)
        raise HTTPException(500, f"预览生成失败: {e}")

    return {
        "success": True, "total": total, "preview_id": uid,
        "limit": limit, "initial": initial,
        "truncated": total > limit, "pages": pages,
    }


@router.get("/api/preview-page")
def preview_page(preview_id: str, page: int):
    """按需加载单页缩略图（preview_id 为 /api/preview-pages 返回值）"""
    if not _PREVIEW_ID_RE.fullmatch(preview_id):
        raise HTTPException(400, "无效的预览标识")
    if page < 1:
        raise HTTPException(400, "页码无效")

    inp = UPLOAD_DIR / f"preview_{preview_id}.pdf"
    if not inp.exists():
        raise HTTPException(404, "预览已过期，请重新上传文件")

    doc = None
    try:
        doc = fitz.open(str(inp))
        total = len(doc)
        limit = min(total, PREVIEW_MAX_PAGES)
        if page > limit:
            raise HTTPException(400, f"页码超出范围（可预览 {limit} 页）")
        return {"success": True, "num": page, **_render_page(doc, page - 1)}
    except HTTPException:
        raise
    except Exception as e:
        _logger.error("单页预览生成失败: %s", e, exc_info=True)
        raise HTTPException(500, f"预览生成失败: {e}")
    finally:
        if doc:
            doc.close()


# ---- PDF 删页 ----

@router.post("/api/delete-pages")
def delete_pages(file: UploadFile = File(...), pages: str = ""):
    if Path(file.filename or "x").suffix.lower() != ".pdf":
        raise HTTPException(400, "仅支持 PDF 文件")
    if not pages.strip():
        raise HTTPException(400, "请指定要删除的页码，如 pages=1,3,5-7")
    content = read_upload(file)
    validate_file_signature(file.filename, content)

    safe_stem = sanitize_stem(file.filename)
    download_id = f"{safe_stem}_removed_{uuid.uuid4().hex[:8]}"
    uid = uuid.uuid4().hex
    inp = UPLOAD_DIR / f"{uid}.pdf"
    inp.write_bytes(content)

    out = OUTPUT_DIR / f"{download_id}.pdf"
    r = w = None

    try:
        r = PdfReader(str(inp))
        total = len(r.pages)
        try:
            dp = parse_page_numbers(pages, total)
        except ValueError as e:
            raise HTTPException(400, str(e))
        if not dp:
            raise HTTPException(400, "未指定有效的页码")
        if len(dp) >= total:
            raise HTTPException(400, "不能删除全部页面")

        w = PdfWriter()
        try:
            for i in range(total):
                if (i + 1) not in dp:
                    w.add_page(r.pages[i])
            w.write(str(out))
        finally:
            w.close()
            w = None
    except HTTPException:
        raise
    except Exception as e:
        safe_unlink(out)
        _logger.error("删除页面失败: %s", e, exc_info=True)
        raise HTTPException(500, f"删除页面失败: {e}")
    finally:
        safe_unlink(inp)
        if w:
            try:
                w.close()
            except Exception:
                _logger.debug("PdfWriter 关闭失败", exc_info=True)
        if r:
            try:
                r.close()
            except Exception:
                _logger.debug("PdfReader 关闭失败", exc_info=True)

    return {
        "success": True, "download_id": download_id,
        "original_name": f"删除 {len(dp)} 页", "download_ext": "pdf",
    }


# ---- PDF 压缩 ----

@router.post("/api/compress-pdf")
def compress_pdf(file: UploadFile = File(...), level: str = "recommended", task_id: str = ""):
    if Path(file.filename or "x").suffix.lower() != ".pdf":
        raise HTTPException(400, "仅支持 PDF 文件")
    if level not in COMPRESSION_LEVELS:
        raise HTTPException(
            400,
            f"不支持的压缩等级: '{level}'，可选: {', '.join(COMPRESSION_LEVELS.keys())}",
        )

    safe_stem = sanitize_stem(file.filename)
    _logger.info("PDF 压缩 [%s]: %s", level, file.filename)

    content = read_upload(file)
    validate_file_signature(file.filename, content)
    original_size = len(content)

    uid = uuid.uuid4().hex
    download_id = f"{safe_stem}_compressed_{level}_{uid[:8]}"
    inp = UPLOAD_DIR / f"{uid}.pdf"
    inp.write_bytes(content)

    out = OUTPUT_DIR / f"{download_id}.pdf"

    try:
        stats = compress_pdf_file(str(inp), str(out), level, task_id=task_id)
    except Exception as e:
        safe_unlink(out)
        _logger.error("PDF 压缩失败: %s - %s", file.filename, e)
        raise HTTPException(500, f"PDF 压缩失败: {e}")
    finally:
        safe_unlink(inp)

    compressed_size = out.stat().st_size
    ratio = (1 - compressed_size / original_size) * 100 if original_size > 0 else 0

    _logger.info(
        "PDF 压缩完成 [%s]: %.2fMB → %.2fMB (%.1f%%)",
        level, original_size / 1024 / 1024, compressed_size / 1024 / 1024, ratio,
    )

    return {
        "success": True,
        "download_id": download_id,
        "original_name": f"{safe_stem} ({COMPRESSION_LEVELS[level]['label']})",
        "download_ext": "pdf",
        "original_size": original_size,
        "compressed_size": compressed_size,
        "ratio": round(ratio, 1),
        "level": level,
        "images_processed": stats["processed"],
        "images_skipped": stats["skipped"],
    }
