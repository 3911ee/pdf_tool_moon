"""测试 utils/task_progress.py"""
import pytest

import utils.task_progress as tp


class TestSetGetProgress:
    def test_set_and_get(self):
        tp.set_progress("a" * 32, 42, "处理中")
        p = tp.get_progress("a" * 32)
        assert p == {"percent": 42, "message": "处理中"}
        tp.clear_progress("a" * 32)

    def test_clear(self):
        tp.set_progress("b" * 32, 10)
        tp.clear_progress("b" * 32)
        assert tp.get_progress("b" * 32) is None

    def test_invalid_id_ignored(self):
        tp.set_progress("../evil", 10)
        assert tp.get_progress("../evil") is None
        tp.set_progress("", 10)
        assert tp.get_progress("") is None

    def test_unknown_id(self):
        assert tp.get_progress("c" * 32) is None

    def test_percent_clamped(self):
        tp.set_progress("d" * 32, 150)
        assert tp.get_progress("d" * 32)["percent"] == 100
        tp.set_progress("d" * 32, -5)
        assert tp.get_progress("d" * 32)["percent"] == 0
        tp.clear_progress("d" * 32)

    def test_expiry(self, monkeypatch):
        monkeypatch.setattr(tp, "_TTL_SECONDS", -1)
        tp.set_progress("e" * 32, 50)
        assert tp.get_progress("e" * 32) is None
