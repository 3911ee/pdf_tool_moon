"""PDF 工具包 — FastAPI 主入口"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config import BASE_DIR, UPLOAD_DIR, OUTPUT_DIR, CORS_ORIGINS
from utils.logging_config import setup_logging
from utils.file_utils import cleanup_old_files, limit_file_count

# ---- 日志 ----
_logger = setup_logging()

# ---- 启动清理 ----
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时清理 + 日志"""
    _logger.info("========== PDF 工具包 启动 ==========")
    cleanup_old_files(UPLOAD_DIR, OUTPUT_DIR)
    limit_file_count(UPLOAD_DIR, OUTPUT_DIR)
    yield
    # 退出缓存的 Office 实例，避免残留 Word/PowerPoint 进程
    try:
        from engines.com_engine import quit_com_pools
        quit_com_pools()
    except Exception:
        _logger.debug("Office 实例清理失败", exc_info=True)
    _logger.info("========== PDF 工具包 关闭 ==========")


# ---- 应用初始化 ----
app = FastAPI(title="PDF 转换工具", lifespan=lifespan)

# CORS 中间件 (#16)：默认关闭跨域；仅当显式配置 PDF_CORS_ORIGINS 时启用
if CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# ---- 注册路由 ----
from routers.convert import router as convert_router
from routers.pdf_ops import router as pdf_ops_router
from routers.download import router as download_router
from routers.system import router as system_router

app.include_router(convert_router)
app.include_router(pdf_ops_router)
app.include_router(download_router)
app.include_router(system_router)

# ---- 挂载静态文件 ----
app.mount("/", StaticFiles(directory=str(BASE_DIR / "static"), html=True), name="static")
