"""测试 utils/file_utils.py"""
import pytest
from fastapi import HTTPException

from utils.file_utils import (
    safe_unlink, safe_rmdir, cleanup_old_files,
    limit_file_count, validate_file_signature, read_upload,
    sanitize_stem, zip_member_name,
)


class TestSafeOperations:
    def test_safe_unlink_existing(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello")
        assert f.exists()
        safe_unlink(f)
        assert not f.exists()

    def test_safe_unlink_nonexistent(self, tmp_path):
        f = tmp_path / "noexist.txt"
        safe_unlink(f)  # 不抛异常

    def test_safe_rmdir_existing(self, tmp_path):
        d = tmp_path / "subdir"
        d.mkdir()
        (d / "file.txt").write_text("x")
        assert d.exists()
        safe_rmdir(d)
        assert not d.exists()

    def test_safe_rmdir_nonexistent(self, tmp_path):
        d = tmp_path / "nosubdir"
        safe_rmdir(d)  # 不抛异常


class TestCleanup:
    def test_cleanup_old_files(self, tmp_path):
        d = tmp_path / "cleanup_test"
        d.mkdir()
        f = d / "old.txt"
        f.write_text("x")
        # 文件刚创建，不会被清理
        cleanup_old_files(d)
        assert f.exists()

    def test_cleanup_nonexistent_dir(self, tmp_path):
        d = tmp_path / "ghost"
        cleanup_old_files(d)  # 不抛异常

    def test_limit_file_count(self, tmp_path):
        d = tmp_path / "limit_test"
        d.mkdir()
        # 只创建少量文件，不会被清理
        for i in range(5):
            (d / f"{i}.txt").write_text("x")
        limit_file_count(d)
        assert len(list(d.iterdir())) == 5


class TestSanitizeStem:
    def test_path_traversal(self):
        stem = sanitize_stem("..\\..\\evil.pdf")
        assert ".." not in stem
        assert "/" not in stem and "\\" not in stem
        assert stem == "evil"

    def test_forward_slash_traversal(self):
        stem = sanitize_stem("../../windows/win")
        assert stem == "win"

    def test_illegal_chars(self):
        stem = sanitize_stem('a<b>:c"d|e?f*g.pdf')
        assert set('< > : " | ? *'.split()) & set(stem) == set()
        assert stem.startswith("a_b")

    def test_windows_reserved_name(self):
        assert sanitize_stem("con.pdf") == "_con"
        assert sanitize_stem("COM1.docx") == "_COM1"
        assert sanitize_stem("nul") == "_nul"

    def test_empty_fallback(self):
        assert sanitize_stem("") == "file"
        assert sanitize_stem("   ") == "file"
        assert sanitize_stem("..") == "file"

    def test_long_name_truncated(self):
        stem = sanitize_stem("x" * 200 + ".pdf")
        assert len(stem) <= 80

    def test_extension_removed(self):
        assert sanitize_stem("报告.docx") == "报告"


class TestZipMemberName:
    def test_strips_directories(self):
        assert zip_member_name("../dir/file.pdf") == "file.pdf"
        assert zip_member_name("a\\b\\c.pdf") == "c.pdf"

    def test_empty_fallback(self):
        assert zip_member_name("") == "file"


class TestValidateFileSignature:
    def test_valid_pdf(self):
        content = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n..."
        validate_file_signature("test.pdf", content)  # 不抛异常

    def test_invalid_pdf(self):
        content = b"Not a PDF file"
        with pytest.raises(HTTPException) as exc:
            validate_file_signature("fake.pdf", content)
        assert "不匹配" in str(exc.value.detail)

    def test_valid_png(self):
        content = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR..."
        validate_file_signature("test.png", content)  # 不抛异常

    def test_invalid_png(self):
        content = b"Not a PNG"
        with pytest.raises(HTTPException):
            validate_file_signature("test.png", content)

    def test_valid_jpg(self):
        content = b"\xff\xd8\xff\xe0\x00\x10JFIF..."
        validate_file_signature("test.jpg", content)  # 不抛异常

    def test_valid_docx(self):
        content = b"PK\x03\x04\x14\x00\x00\x00..."
        validate_file_signature("test.docx", content)  # 不抛异常

    def test_unsupported_extension(self):
        with pytest.raises(HTTPException):
            validate_file_signature("test.xyz", b"anything")
