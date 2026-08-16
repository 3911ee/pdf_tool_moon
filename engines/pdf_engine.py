"""PDF 引擎：压缩、预览、PDF→Word 转换"""
import io
import logging

import fitz
from PIL import Image
from pdf2docx import Converter

from config import COMPRESSION_LEVELS, COMPRESS_MAX_IMAGE_BYTES
from utils.task_progress import set_progress

_logger = logging.getLogger("pdf-tools")


# ---- PDF → Word (pdf2docx) ----

def pdf_to_word_pdf2docx(pdf_path, docx_path):
    """PDF → Word：直接解析 PDF 内容流 → 重建 DOCX"""
    cv = Converter(pdf_path)
    try:
        cv.convert(
            docx_path,
            multi_processing=False,
            clip_image_res_ratio=6.0,
            extract_stream_table=True,
            delete_end_line_hyphen=True,
            parse_lattice_table=True,
            parse_stream_table=True,
            min_section_height=10.0,
        )
    finally:
        cv.close()


# ---- PDF 压缩 ----

def _flatten_to_rgb(img, mask_img=None):
    """将任意模式的图片 + 可选外部遮罩扁平化为 RGB 白底图"""
    if mask_img is not None:
        if img.size != mask_img.size:
            mask_img = mask_img.resize(img.size, Image.LANCZOS)
        if mask_img.mode != "L":
            mask_img = mask_img.convert("L")
        if img.mode == "RGB":
            img = img.convert("RGBA")
        elif img.mode not in ("RGBA", "LA", "PA"):
            img = img.convert("RGBA")
        if img.mode == "RGBA":
            r, g, b, _ = img.split()
            img = Image.merge("RGBA", (r, g, b, mask_img))
        elif img.mode == "LA":
            l, _ = img.split()
            img = Image.merge("LA", (l, mask_img))
        elif img.mode == "PA":
            img = img.convert("RGBA")
            r, g, b, _ = img.split()
            img = Image.merge("RGBA", (r, g, b, mask_img))

    if img.mode == "P":
        img = img.convert("RGBA")
    if img.mode in ("RGBA", "LA", "PA"):
        background = Image.new("RGB", img.size, (255, 255, 255))
        if img.mode == "LA":
            background.paste(img, mask=img.split()[1])
        elif img.mode == "PA":
            img_rgb = img.convert("RGBA")
            background.paste(img_rgb, mask=img_rgb.split()[3])
            img_rgb.close()
        else:
            background.paste(img, mask=img.split()[3])
        img.close()
        img = background
    elif img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    return img


def _compress_image_bytes(img_bytes, ext, cfg, mask_bytes=None):
    """使用 PIL 重新压缩单张图片，返回 (bytes, new_ext)"""
    img = Image.open(io.BytesIO(img_bytes))
    mask_img = Image.open(io.BytesIO(mask_bytes)) if mask_bytes else None
    try:
        orig_w, orig_h = img.size
        max_dim = cfg["max_dim"]

        if max_dim > 0 and max(orig_w, orig_h) > max_dim:
            ratio = max_dim / max(orig_w, orig_h)
            new_w = int(orig_w * ratio)
            new_h = int(orig_h * ratio)
            img = img.resize((new_w, new_h), Image.LANCZOS)
            if mask_img is not None:
                mask_img = mask_img.resize((new_w, new_h), Image.LANCZOS)

        img = _flatten_to_rgb(img, mask_img)

        out_buf = io.BytesIO()
        if ext.lower() in ("png", "gif", "bmp"):
            if cfg["jpeg_quality"] >= 80:
                img.save(out_buf, format="PNG", optimize=True)
                new_ext = "png"
            else:
                img.save(out_buf, format="JPEG", quality=cfg["jpeg_quality"], optimize=True)
                new_ext = "jpg"
        else:
            img.save(out_buf, format="JPEG", quality=cfg["jpeg_quality"], optimize=True)
            new_ext = "jpg"

        return out_buf.getvalue(), new_ext
    finally:
        img.close()
        if mask_img is not None:
            mask_img.close()


def compress_pdf_file(input_path, output_path, level, task_id=""):
    """PDF 压缩：降低图片分辨率 + JPEG 重压缩 + 垃圾回收

    返回 {"processed": n, "skipped": m}：
    - 同一 xref 跨页共享的图片只处理一次（去重，减少内存与耗时）；
    - 超过 COMPRESS_MAX_IMAGE_BYTES 的单张图片跳过重压缩（防内存峰值），保留原图。
    """
    cfg = COMPRESSION_LEVELS[level]
    stats = {"processed": 0, "skipped": 0}
    doc = fitz.open(input_path)
    try:
        metadata = doc.metadata or {}
        keep_keys = {"title", "author", "subject", "keywords", "creator", "producer"}
        clean_meta = {k: v for k, v in metadata.items() if k in keep_keys and v}
        doc.set_metadata(clean_meta)

        # 第一遍：收集去重后的图片任务 xref -> (page_num, img_info)
        jobs = {}
        for page_num in range(len(doc)):
            for img_info in doc[page_num].get_images(full=True):
                xref = img_info[0]
                if xref not in jobs:
                    jobs[xref] = (page_num, img_info)

        total = len(jobs)
        for idx, (xref, (page_num, img_info)) in enumerate(jobs.items()):
            set_progress(task_id, int(idx / max(total, 1) * 100), f"图片压缩 ({idx + 1}/{total})")
            try:
                img_data = doc.extract_image(xref)
                if not img_data:
                    continue

                orig_bytes = img_data["image"]
                orig_ext = img_data.get("ext", "png")

                # 超大图降级：跳过重压缩，避免内存峰值
                if len(orig_bytes) > COMPRESS_MAX_IMAGE_BYTES:
                    _logger.warning(
                        "图片过大 (%.1fMB)，跳过重压缩 (xref=%d)",
                        len(orig_bytes) / 1024 / 1024, xref,
                    )
                    stats["skipped"] += 1
                    continue

                smask_xref = img_data.get("smask", 0)
                mask_bytes = None
                if smask_xref > 0:
                    try:
                        mask_data = doc.extract_image(smask_xref)
                        if mask_data:
                            mask_bytes = mask_data["image"]
                    except Exception:
                        _logger.warning(
                            "无法提取 SMask (xref=%d)，跳过遮罩合成", smask_xref
                        )

                compressed_bytes, new_ext = _compress_image_bytes(
                    orig_bytes, orig_ext, cfg, mask_bytes=mask_bytes
                )

                # 修复 #23：使用 stream 参数替代磁盘临时文件；
                # PyMuPDF 要求 filename/stream/pixmap 三选一，仅传 stream
                doc[page_num].replace_image(xref, stream=io.BytesIO(compressed_bytes))

                if smask_xref > 0:
                    try:
                        doc.xref_set_key(xref, "SMask", "null")
                    except Exception:
                        _logger.warning("无法清除 SMask 引用 (xref=%d)", xref)

                stats["processed"] += 1
            except Exception as e:
                _logger.warning("图片压缩跳过 (xref=%d): %s", xref, e)
                continue
            set_progress(task_id, int((idx + 1) / max(total, 1) * 100), f"图片压缩 ({idx + 1}/{total})")

        _logger.info(
            "压缩统计: 处理 %d 张, 跳过 %d 张, 等级=%s",
            stats["processed"], stats["skipped"], level,
        )
        set_progress(task_id, 100, "压缩完成")

        doc.save(
            output_path,
            garbage=cfg["garbage"],
            deflate=cfg["deflate"],
            clean=cfg["clean"],
            pretty=False,
            linear=False,
            no_new_id=False,
        )
    finally:
        doc.close()
    return stats


# ---- 页码解析 ----

def parse_page_numbers(s, total):
    """解析页码字符串: "1,3,5-7" → {1, 3, 5, 6, 7}"""
    result = set()
    for part in s.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            if "-" in part:
                a, b = part.split("-", 1)
                start, end = int(a.strip()), int(b.strip())
                if start < 1 or end > total or start > end:
                    raise ValueError(f"页码范围无效: {part}")
                result.update(range(start, end + 1))
            else:
                n = int(part)
                if n < 1 or n > total:
                    raise ValueError(f"页码超出范围: {n}（共 {total} 页）")
                result.add(n)
        except ValueError as e:
            raise ValueError(f"页码格式错误: '{part}'")
    return result
