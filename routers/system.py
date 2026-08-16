"""系统端点：健康检查、任务进度、关闭服务"""
import os
import signal
import threading
import time
import logging

from fastapi import APIRouter, HTTPException, Request

from config import SHUTDOWN_TOKEN
from utils.task_progress import get_progress

router = APIRouter()
_logger = logging.getLogger("pdf-tools")


@router.get("/api/health")
def health():
    """健康检查端点"""
    return {"status": "ok"}


@router.get("/api/task/{task_id}")
def task_status(task_id: str):
    """轮询长任务进度（由 Word/PPT/压缩等端点写入）"""
    progress = get_progress(task_id)
    if progress is None:
        raise HTTPException(404, "任务不存在或已过期")
    return {
        "success": True,
        "percent": progress["percent"],
        "message": progress["message"],
    }


def _trigger_shutdown():
    """延迟触发优雅关闭（让响应先返回给客户端）"""
    def _exit():
        time.sleep(0.4)
        try:
            # raise_signal 会调用主线程注册的 SIGTERM 处理器（uvicorn 优雅退出）
            signal.raise_signal(signal.SIGTERM)
        except Exception:
            os.kill(os.getpid(), signal.SIGTERM)

    threading.Thread(target=_exit, daemon=True).start()


@router.post("/api/shutdown")
async def shutdown(request: Request):
    """关闭服务。

    鉴权规则：
    - 配置了 PDF_SHUTDOWN_TOKEN 时，要求 X-Shutdown-Token 请求头匹配；
    - 未配置时仅允许本机（127.0.0.1 / ::1 / localhost）调用。
    """
    client_host = request.client.host if request.client else ""
    is_local = client_host in ("127.0.0.1", "::1", "localhost")
    token = request.headers.get("x-shutdown-token", "")

    if SHUTDOWN_TOKEN:
        if token != SHUTDOWN_TOKEN:
            raise HTTPException(403, "未授权：缺少有效的 X-Shutdown-Token")
    elif not is_local:
        raise HTTPException(403, "仅允许本机调用（或配置 PDF_SHUTDOWN_TOKEN）")

    _logger.info("收到关闭请求，正在退出...")
    _trigger_shutdown()
    return {"success": True, "message": "服务正在关闭"}
