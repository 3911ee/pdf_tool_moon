"""图片引擎：图片→PDF、格式互转"""
import logging
from pathlib import Path

from PIL import Image

from config import FORMAT_MAP, SAVE_OPTIONS

_logger = logging.getLogger("pdf-tools")

A4_PAGE_POINTS = (595, 842)  # PDF 页面点单位（约 A4）


def _flatten_image_to_rgb(img):
    """将任意模式的图片扁平化为白底 RGB 图片（消费原对象）"""
    if img.mode in ("RGBA", "P", "LA"):
        rgb = Image.new("RGB", img.size, (255, 255, 255))
        if img.mode == "P":
            img = img.convert("RGBA")
        rgb.paste(img, mask=img.split()[-1] if img.mode == "RGBA" else None)
        img.close()
        return rgb
    if img.mode != "RGB":
        img = img.convert("RGB")
    return img


def images_to_pdf(image_paths, pdf_path, page_size=None):
    """多张图片合并为 PDF，每张一页。

    page_size="a4" 时按比例缩放并居中放置在 A4 页面；
    否则（默认）每页大小与图片一致。
    """
    imgs = []
    try:
        for p in image_paths:
            img = _flatten_image_to_rgb(Image.open(p))
            if page_size == "a4":
                scale = min(A4_PAGE_POINTS[0] / img.width, A4_PAGE_POINTS[1] / img.height)
                w = max(1, int(img.width * scale))
                h = max(1, int(img.height * scale))
                resized = img.resize((w, h), Image.LANCZOS)
                img.close()
                page = Image.new("RGB", A4_PAGE_POINTS, (255, 255, 255))
                page.paste(resized, ((A4_PAGE_POINTS[0] - w) // 2, (A4_PAGE_POINTS[1] - h) // 2))
                resized.close()
                img = page
            imgs.append(img)
        if imgs:
            # 72dpi 时像素尺寸即为点单位尺寸，保证 A4 页面大小精确
            resolution = 72.0 if page_size == "a4" else 100.0
            imgs[0].save(
                pdf_path, "PDF", resolution=resolution,
                save_all=True, append_images=imgs[1:]
            )
    finally:
        for img in imgs:
            try:
                img.close()
            except Exception:
                _logger.debug("关闭图片失败", exc_info=True)


def convert_image_format(items, target_format, output_dir):
    """批量图片格式转换，输出到指定目录。

    items 元素可以是路径（Path/str，输出名取路径 stem），
    或 (src_path, stem) 元组（保留用户原始文件名）。
    重名时自动追加 _2/_3 后缀，避免互相覆盖。
    """
    converted = []
    for i, item in enumerate(items):
        if isinstance(item, (tuple, list)):
            src, stem = Path(item[0]), str(item[1])
        else:
            src = Path(str(item))
            stem = src.stem

        img = Image.open(str(src))
        try:
            if target_format in ("jpg", "jpeg"):
                img = _flatten_image_to_rgb(img)
            elif target_format == "gif":
                if img.mode not in ("P", "L"):
                    img = img.convert("P", palette=Image.Palette.ADAPTIVE)

            out = output_dir / f"{stem}.{target_format}"
            n = 2
            while out.exists():
                out = output_dir / f"{stem}_{n}.{target_format}"
                n += 1

            img.save(str(out), FORMAT_MAP[target_format], **SAVE_OPTIONS.get(target_format, {}))
            converted.append(out)
        finally:
            img.close()
    return converted
