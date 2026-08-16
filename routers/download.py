"""下载端点"""
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from config import OUTPUT_DIR

router = APIRouter()

MEDIA_MAP = {
    "pdf": "application/pdf",
    "zip": "application/zip",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def _validate_download_id(download_id):
    """下载标识必须是单个安全文件名（防路径遍历）"""
    if download_id != Path(download_id).name or download_id in (".", ".."):
        raise HTTPException(400, "非法的下载标识")


@router.get("/api/download/{download_id}")
def download_file(download_id: str, ext: str = ""):
    _validate_download_id(download_id)

    if ext:
        if ext not in MEDIA_MAP:
            raise HTTPException(400, "不支持的扩展名")
        file_path = OUTPUT_DIR / f"{download_id}.{ext}"
        if not file_path.exists():
            raise HTTPException(404, "文件不存在或已过期")
        return FileResponse(
            str(file_path), filename=f"{download_id}.{ext}",
            media_type=MEDIA_MAP[ext],
        )

    for e, media in MEDIA_MAP.items():
        file_path = OUTPUT_DIR / f"{download_id}.{e}"
        if file_path.exists():
            return FileResponse(
                str(file_path), filename=f"{download_id}.{e}", media_type=media,
            )

    raise HTTPException(404, "文件不存在或已过期")
