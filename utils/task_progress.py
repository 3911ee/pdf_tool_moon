"""任务进度存储：进程内内存实现，供前端轮询读取。

task_id 由前端生成（uuid hex），后端严格校验格式，
防止利用 task_id 做注入或撑爆内存。
"""
import re
import threading
import time

_lock = threading.Lock()
_store = {}

_ID_RE = re.compile(r"^[0-9a-fA-F]{8,64}$")
_TTL_SECONDS = 600          # 进度条目保留 10 分钟
_MAX_ENTRIES = 500          # 防止内存无限增长


def _valid(task_id):
    return isinstance(task_id, str) and bool(_ID_RE.fullmatch(task_id))


def set_progress(task_id, percent, message=""):
    """更新任务进度（无效 task_id 静默忽略）"""
    if not _valid(task_id):
        return
    percent = max(0, min(100, int(percent)))
    now = time.time()
    with _lock:
        _store[task_id] = {"percent": percent, "message": str(message), "time": now}
        # 超上限时淘汰最旧条目
        if len(_store) > _MAX_ENTRIES:
            oldest = sorted(_store, key=lambda k: _store[k]["time"])[: len(_store) - _MAX_ENTRIES]
            for k in oldest:
                _store.pop(k, None)


def get_progress(task_id):
    """读取任务进度；不存在或已过期返回 None"""
    if not _valid(task_id):
        return None
    with _lock:
        entry = _store.get(task_id)
        if entry is None:
            return None
        if time.time() - entry["time"] > _TTL_SECONDS:
            _store.pop(task_id, None)
            return None
        return {"percent": entry["percent"], "message": entry["message"]}


def clear_progress(task_id):
    """清除任务进度条目"""
    if _valid(task_id):
        with _lock:
            _store.pop(task_id, None)
