"""转换端点：Word→PDF、PPT→PDF、图片→PDF、图片格式互转、PDF→Word

说明：
- 所有处理端点均为同步 def，由 FastAPI 放入线程池执行，
  避免 CPU/COM 密集任务阻塞事件循环；
- 输出文件名一律带 uid 后缀，防止并发/同名覆盖与路径注入。
"""
import uuid
import zipfile
import logging
from pathlib import Path

from fastapi import APIRouter, File, UploadFile, HTTPException

from config import (
    UPLOAD_DIR, OUTPUT_DIR, IMAGE_EXTENSIONS, FORMAT_MAP,
    MAX_FILES_PER_REQUEST,
)
from engines.com_engine import word_to_pdf_batch, ppt_to_pdf_batch, ComBusyError
from engines.pdf_engine import pdf_to_word_pdf2docx
from engines.image_engine import (
    images_to_pdf,
    convert_image_format as convert_image_format_engine,
)
from utils.file_utils import (
    safe_unlink, safe_rmdir, read_upload,
    validate_file_signature, sanitize_stem, zip_member_name,
)

router = APIRouter()
_logger = logging.getLogger("pdf-tools")


# ---- 通用辅助函数 (#4 消除重复) ----

def _validate_extensions(files, allowed_exts):
    """校验文件扩展名"""
    for f in files:
        ext = Path(f.filename or "x").suffix.lower()
        if ext not in allowed_exts:
            raise HTTPException(400, f"不支持的格式: {f.filename} (允许: {allowed_exts})")


def _check_file_count(files):
    if len(files) > MAX_FILES_PER_REQUEST:
        raise HTTPException(400, f"单次最多上传 {MAX_FILES_PER_REQUEST} 个文件")


def _save_uploaded_files(files, uid):
    """保存上传文件到 UPLOAD_DIR（带大小/数量/签名校验）"""
    _check_file_count(files)
    saved = []
    for i, f in enumerate(files):
        content = read_upload(f)
        validate_file_signature(f.filename or f"file_{i}", content)
        ext = Path(f.filename or "x").suffix.lower()
        inp = UPLOAD_DIR / f"{uid}_{i}{ext}"
        inp.write_bytes(content)
        saved.append(inp)
    return saved


def _build_batch_zip(results, download_id):
    """将多个输出文件打包为 zip（成员名去重），返回 download_id"""
    zip_p = OUTPUT_DIR / f"{download_id}.zip"
    with zipfile.ZipFile(str(zip_p), "w", zipfile.ZIP_DEFLATED) as zf:
        for out, name in results:
            zf.write(str(out), name)
            safe_unlink(out)
    return download_id


def _unique_members(files):
    """为批量输出生成去重的 zip 成员名，返回 [(原名, 成员名)]"""
    seen = {}
    members = []
    for f in files:
        name = zip_member_name(f.filename or "file")
        stem = Path(name).stem
        seen[stem] = seen.get(stem, 0) + 1
        n = seen[stem]
        members.append(f"{stem}.pdf" if n == 1 else f"{stem}_{n}.pdf")
    return members


def _finalize_response(download_id, original_name, ext, **extra):
    payload = {
        "success": True, "download_id": download_id,
        "original_name": original_name, "download_ext": ext,
    }
    payload.update(extra)
    return payload


# ---- Word → PDF（同步 def，线程池执行）----

@router.post("/api/convert")
def convert_to_pdf(files: list[UploadFile] = File(...), task_id: str = ""):
    """Word → PDF，支持批量（多文件返回 zip）"""
    if not files:
        raise HTTPException(400, "请至少上传一个文件")
    _validate_extensions(files, {".doc", ".docx"})
    _check_file_count(files)

    batch = len(files) > 1
    safe_stem = sanitize_stem(files[0].filename)
    download_id = f"{safe_stem}_{uuid.uuid4().hex[:8]}"
    saved, results = [], []

    try:
        saved = _save_uploaded_files(files, uid=uuid.uuid4().hex)
        members = _unique_members(files)
        jobs = []
        for i, (inp, f) in enumerate(zip(saved, files)):
            out_name = members[i]
            out = OUTPUT_DIR / f"{download_id}_{i}_{out_name}" if batch else OUTPUT_DIR / f"{download_id}.pdf"
            jobs.append((str(inp), str(out)))
            results.append((out, out_name))
            _logger.info("Word→PDF [%d/%d]: %s", i + 1, len(files), f.filename)

        word_to_pdf_batch(jobs, task_id=task_id)

        if batch:
            _build_batch_zip(results, download_id)
            _logger.info("Word→PDF 批量完成: %d 个文件", len(files))
            return _finalize_response(
                download_id, f"共{len(files)}个文件", "zip", batch=True
            )
        _logger.info("Word→PDF 完成: %s", files[0].filename)
        return _finalize_response(download_id, safe_stem, "pdf")
    except HTTPException:
        raise
    except ComBusyError as e:
        raise HTTPException(503, str(e))
    except Exception as e:
        _logger.error("Word→PDF 失败: %s", e, exc_info=True)
        for out, _ in results:
            safe_unlink(out)
        raise HTTPException(500, f"转换失败: {e}")
    finally:
        for inp in saved:
            safe_unlink(inp)


# ---- PPT → PDF ----

@router.post("/api/convert-ppt")
def convert_ppt_to_pdf(files: list[UploadFile] = File(...), task_id: str = ""):
    """PPT → PDF，支持批量（多文件返回 zip）"""
    if not files:
        raise HTTPException(400, "请至少上传一个文件")
    _validate_extensions(files, {".ppt", ".pptx"})
    _check_file_count(files)

    batch = len(files) > 1
    safe_stem = sanitize_stem(files[0].filename)
    download_id = f"{safe_stem}_{uuid.uuid4().hex[:8]}"
    saved, results = [], []

    try:
        saved = _save_uploaded_files(files, uid=uuid.uuid4().hex)
        members = _unique_members(files)
        jobs = []
        for i, (inp, f) in enumerate(zip(saved, files)):
            out_name = members[i]
            out = OUTPUT_DIR / f"{download_id}_{i}_{out_name}" if batch else OUTPUT_DIR / f"{download_id}.pdf"
            jobs.append((str(inp), str(out)))
            results.append((out, out_name))
            _logger.info("PPT→PDF [%d/%d]: %s", i + 1, len(files), f.filename)

        ppt_to_pdf_batch(jobs, task_id=task_id)

        if batch:
            _build_batch_zip(results, download_id)
            _logger.info("PPT→PDF 批量完成: %d 个文件", len(files))
            return _finalize_response(
                download_id, f"共{len(files)}个文件", "zip", batch=True
            )
        _logger.info("PPT→PDF 完成: %s", files[0].filename)
        return _finalize_response(download_id, safe_stem, "pdf")
    except HTTPException:
        raise
    except ComBusyError as e:
        raise HTTPException(503, str(e))
    except Exception as e:
        _logger.error("PPT→PDF 失败: %s", e, exc_info=True)
        for out, _ in results:
            safe_unlink(out)
        raise HTTPException(500, f"转换失败: {e}")
    finally:
        for inp in saved:
            safe_unlink(inp)


# ---- 图片 → PDF ----

@router.post("/api/convert-image")
def convert_images_to_pdf(files: list[UploadFile] = File(...), page_size: str = ""):
    if not files:
        raise HTTPException(400, "请至少上传一张图片")
    if page_size not in ("", "fit", "a4"):
        raise HTTPException(400, f"不支持的页面尺寸: {page_size}（可选 fit / a4）")
    _validate_extensions(files, IMAGE_EXTENSIONS)

    safe_stem = sanitize_stem(files[0].filename or "images", fallback="images")
    download_id = f"{safe_stem}_{uuid.uuid4().hex[:8]}"
    saved = []

    try:
        saved = _save_uploaded_files(files, uid=uuid.uuid4().hex)
        out = OUTPUT_DIR / f"{download_id}.pdf"
        images_to_pdf([str(p) for p in saved], str(out), page_size=page_size or None)
    except HTTPException:
        raise
    except Exception as e:
        _logger.error("图片→PDF 失败: %s", e, exc_info=True)
        raise HTTPException(500, f"图片转换失败: {e}")
    finally:
        for p in saved:
            safe_unlink(p)

    return _finalize_response(download_id, f"共{len(files)}张图片", "pdf")


# ---- 图片格式互转 ----

@router.post("/api/convert-format")
def convert_images_format(files: list[UploadFile] = File(...), target: str = "png"):
    if not files:
        raise HTTPException(400, "请至少上传一张图片")
    target = target.lower()
    if target not in FORMAT_MAP:
        raise HTTPException(400, f"不支持的目标格式: {target}")
    _validate_extensions(files, IMAGE_EXTENSIONS)

    safe_stem = sanitize_stem(files[0].filename or "images", fallback="images")
    download_id = f"{safe_stem}_converted_{uuid.uuid4().hex[:8]}"
    uid = uuid.uuid4().hex
    d = OUTPUT_DIR / uid
    d.mkdir(exist_ok=True)
    saved = []

    try:
        saved = _save_uploaded_files(files, uid=uid)
        items = [
            (p, sanitize_stem(f.filename or f"image{i + 1}", fallback=f"image{i + 1}"))
            for i, (p, f) in enumerate(zip(saved, files))
        ]
        convert_image_format_engine(items, target, d)
    except HTTPException:
        raise
    except Exception as e:
        _logger.error("图片格式互转失败: %s", e, exc_info=True)
        raise HTTPException(500, f"格式转换失败: {e}")
    finally:
        for p in saved:
            safe_unlink(p)

    zip_p = OUTPUT_DIR / f"{download_id}.zip"
    try:
        with zipfile.ZipFile(str(zip_p), "w", zipfile.ZIP_DEFLATED) as zf:
            for f in sorted(d.iterdir()):
                zf.write(str(f), f.name)
                safe_unlink(f)
    finally:
        safe_rmdir(d)

    return _finalize_response(download_id, f"共{len(files)}张图片", "zip")


# ---- PDF → Word ----

@router.post("/api/pdf-to-word")
def pdf_to_word(file: UploadFile = File(...)):
    if Path(file.filename or "x").suffix.lower() != ".pdf":
        raise HTTPException(400, "仅支持 PDF 文件")
    content = read_upload(file)
    validate_file_signature(file.filename, content)

    safe_stem = sanitize_stem(file.filename)
    _logger.info("PDF→Word: %s", file.filename)
    uid = uuid.uuid4().hex
    download_id = f"{safe_stem}_{uid[:8]}"
    inp = UPLOAD_DIR / f"{uid}.pdf"
    inp.write_bytes(content)

    out = OUTPUT_DIR / f"{download_id}.docx"
    try:
        pdf_to_word_pdf2docx(str(inp), str(out))
        _logger.info("PDF→Word 完成: %s -> %s.docx", file.filename, download_id)
    except Exception as e:
        safe_unlink(out)  # 清理半成品
        _logger.error("PDF→Word 失败: %s - %s", file.filename, e)
        raise HTTPException(500, f"PDF 转 Word 失败: {e}")
    finally:
        safe_unlink(inp)

    if not out.exists() or out.stat().st_size < 100:
        raise HTTPException(500, "PDF 转 Word 失败：输出文件无效")

    return _finalize_response(download_id, safe_stem, "docx")
