"""COM 引擎：Word/PPT → PDF 转换（Windows + Microsoft Office 必需）

并发模型：
- Word 与 PPT 各使用独立锁，两类转换可以并行；
- Office 应用实例按线程缓存复用（避免每次启动/退出 Office 的秒级开销）；
- 同一类型的转换串行执行（Office 单实例不支持并发打开文档）；
- 应用实例损坏（崩溃/无响应）时自动销毁并在下次请求重建。
"""
import gc
import os
import threading
import logging

import pythoncom
import win32com.client

from config import COM_TIMEOUT
from utils.task_progress import set_progress

_logger = logging.getLogger("pdf-tools")


class ComBusyError(Exception):
    """COM 服务繁忙（等待锁超时），路由层映射为 503"""


# ---- 全局实例登记（服务关闭时统一退出） ----
_instances = set()
_instances_lock = threading.Lock()

# ---- 线程级 COM 初始化登记 ----
_com_init_lock = threading.Lock()
_com_initialized_threads = set()


def _ensure_com():
    """确保当前线程已初始化 COM（每线程一次）"""
    tid = threading.get_ident()
    if tid in _com_initialized_threads:
        return
    pythoncom.CoInitialize()
    with _com_init_lock:
        _com_initialized_threads.add(tid)


class _ComAppCache:
    """按线程缓存 COM 应用实例：复用 + 故障自愈"""

    def __init__(self, name):
        self.name = name
        self._lock = threading.Lock()
        self._local = threading.local()

    # ---- 锁 ----
    def acquire(self):
        if not self._lock.acquire(timeout=COM_TIMEOUT):
            raise ComBusyError(f"{self.name} 服务正忙，请稍后重试")
        try:
            _ensure_com()
        except Exception:
            self._lock.release()
            raise
        return True

    def release(self):
        try:
            self._lock.release()
        except RuntimeError:
            pass
        gc.collect()

    # ---- 实例 ----
    def get(self):
        return getattr(self._local, "app", None)

    def set(self, app):
        self._local.app = app
        with _instances_lock:
            _instances.add(app)

    def invalidate(self):
        """销毁当前线程缓存的应用实例（应用损坏时调用）"""
        app = self.get()
        self._local.app = None
        if app is not None:
            with _instances_lock:
                _instances.discard(app)
            try:
                app.Quit()
            except Exception:
                _logger.debug("%s Quit 失败", self.name, exc_info=True)
        gc.collect()

    @staticmethod
    def is_alive(app):
        """探测应用是否存活（属性访问失败即认为已崩溃）"""
        try:
            _ = app.Visible
            return True
        except Exception:
            return False


_WORD_CACHE = _ComAppCache("Word")
_PPT_CACHE = _ComAppCache("PPT")


def quit_com_pools():
    """服务关闭时退出所有缓存的 Office 实例（尽力而为）"""
    with _instances_lock:
        apps = list(_instances)
        _instances.clear()
    for app in apps:
        try:
            app.Quit()
        except Exception:
            _logger.debug("Office 实例退出失败", exc_info=True)


# ---- Word ----

def _create_word():
    word = win32com.client.Dispatch("Word.Application")
    word.Visible = False
    try:
        word.DisplayAlerts = 0  # wdAlertsNone：抑制弹窗，避免挂起
    except Exception:
        pass
    try:
        word.Options.BackgroundSave = False
    except Exception:
        pass
    return word


def _convert_word_doc(word, docx_path, pdf_path):
    doc = None
    try:
        doc = word.Documents.Open(
            os.path.abspath(docx_path), ReadOnly=True, AddToRecentFiles=False
        )
        doc.SaveAs(os.path.abspath(pdf_path), FileFormat=17)  # wdFormatPDF
    except Exception as e:
        raise RuntimeError(f"Word 转换失败: {e}") from e
    finally:
        if doc is not None:
            try:
                doc.Close(False)
            except Exception:
                _logger.debug("Word 文档关闭失败", exc_info=True)


# ---- PowerPoint ----

def _create_ppt():
    ppt = win32com.client.Dispatch("PowerPoint.Application")
    try:
        ppt.DisplayAlerts = 1  # ppAlertsNone
    except Exception:
        pass
    return ppt


def _convert_ppt_doc(powerpoint, ppt_path, pdf_path):
    pres = None
    try:
        pres = powerpoint.Presentations.Open(
            os.path.abspath(ppt_path), WithWindow=False
        )
        pres.SaveAs(os.path.abspath(pdf_path), 32)  # ppSaveAsPDF
    except Exception as e:
        raise RuntimeError(f"PPT 转换失败: {e}") from e
    finally:
        if pres is not None:
            try:
                pres.Close()
            except Exception:
                _logger.debug("PPT 演示文稿关闭失败", exc_info=True)


# ---- 批量转换核心 ----

def _batch_convert(cache, creator, convert_one, items, task_id, label):
    """单个会话内串行转换多个文件，复用应用实例并上报进度"""
    if not items:
        return
    cache.acquire()
    app = None
    try:
        app = cache.get()
        if app is None:
            app = creator()
            cache.set(app)
        total = len(items)
        for i, (src, dst) in enumerate(items):
            set_progress(task_id, int(i / total * 100), f"{label} 转换 ({i + 1}/{total})")
            convert_one(app, src, dst)
            set_progress(task_id, int((i + 1) / total * 100), f"{label} 转换 ({i + 1}/{total})")
        set_progress(task_id, 100, f"{label} 转换完成")
    except Exception:
        # 应用级故障：销毁实例，下次请求重建；文档级错误保留原异常
        if app is not None and not cache.is_alive(app):
            _logger.warning("%s 应用无响应，销毁实例以便重建", label)
            cache.invalidate()
        raise
    finally:
        cache.release()


def word_to_pdf_batch(items, task_id=""):
    """批量 Word → PDF；items: [(src_path, dst_path)]"""
    _batch_convert(_WORD_CACHE, _create_word, _convert_word_doc, items, task_id, "Word")


def ppt_to_pdf_batch(items, task_id=""):
    """批量 PPT → PDF；items: [(src_path, dst_path)]"""
    _batch_convert(_PPT_CACHE, _create_ppt, _convert_ppt_doc, items, task_id, "PPT")


def word_to_pdf_win32(docx_path, pdf_path):
    """单文件 Word → PDF（兼容旧接口）"""
    word_to_pdf_batch([(docx_path, pdf_path)])


def ppt_to_pdf_win32(ppt_path, pdf_path):
    """单文件 PPT → PDF（兼容旧接口）"""
    ppt_to_pdf_batch([(ppt_path, pdf_path)])
