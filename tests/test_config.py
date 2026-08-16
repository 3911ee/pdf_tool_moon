"""测试 config.py"""
import os
import importlib

import config


class TestDefaults:
    def test_max_upload_size_default(self):
        assert config.MAX_UPLOAD_SIZE == 200 * 1024 * 1024

    def test_preview_defaults(self):
        assert config.PREVIEW_MAX_PAGES == 200
        assert config.PREVIEW_DPI == 72
        assert config.PREVIEW_INITIAL_PAGES == 12
        assert config.PREVIEW_CACHE_SECONDS == 3600

    def test_com_timeout(self):
        assert config.COM_TIMEOUT == 120

    def test_upload_limits(self):
        assert config.MAX_UPLOAD_SIZE == 200 * 1024 * 1024
        assert config.MAX_FILES_PER_REQUEST == 20

    def test_compress_max_image_bytes(self):
        assert config.COMPRESS_MAX_IMAGE_BYTES == 50 * 1024 * 1024

    def test_shutdown_token_default(self):
        assert config.SHUTDOWN_TOKEN == ""

    def test_paths_exist(self):
        assert config.BASE_DIR.exists()
        assert config.UPLOAD_DIR.name == "uploads"
        assert config.OUTPUT_DIR.name == "outputs"
        assert config.LOG_DIR.name == "logs"

    def test_image_extensions(self):
        assert ".jpg" in config.IMAGE_EXTENSIONS
        assert ".png" in config.IMAGE_EXTENSIONS

    def test_format_map_keys(self):
        for fmt in ["png", "jpg", "jpeg", "webp", "bmp"]:
            assert fmt in config.FORMAT_MAP

    def test_compression_levels(self):
        assert "light" in config.COMPRESSION_LEVELS
        assert "recommended" in config.COMPRESSION_LEVELS
        assert "extreme" in config.COMPRESSION_LEVELS

    def test_cors_default(self):
        # 默认关闭跨域
        assert config.CORS_ORIGINS == []


class TestEnvOverrides:
    def test_env_override_max_upload(self, monkeypatch):
        monkeypatch.setenv("PDF_MAX_UPLOAD_SIZE", "52428800")  # 50MB
        importlib.reload(config)
        assert config.MAX_UPLOAD_SIZE == 52428800
        # 恢复
        monkeypatch.delenv("PDF_MAX_UPLOAD_SIZE", raising=False)
        importlib.reload(config)

    def test_env_override_preview_pages(self, monkeypatch):
        monkeypatch.setenv("PDF_PREVIEW_MAX_PAGES", "100")
        importlib.reload(config)
        assert config.PREVIEW_MAX_PAGES == 100
        monkeypatch.delenv("PDF_PREVIEW_MAX_PAGES", raising=False)
        importlib.reload(config)

    def test_env_override_dpi(self, monkeypatch):
        monkeypatch.setenv("PDF_PREVIEW_DPI", "150")
        importlib.reload(config)
        assert config.PREVIEW_DPI == 150
        monkeypatch.delenv("PDF_PREVIEW_DPI", raising=False)
        importlib.reload(config)

    def test_env_cors_multiple(self, monkeypatch):
        monkeypatch.setenv("PDF_CORS_ORIGINS", "http://a.com,http://b.com")
        importlib.reload(config)
        assert config.CORS_ORIGINS == ["http://a.com", "http://b.com"]
        monkeypatch.delenv("PDF_CORS_ORIGINS", raising=False)
        importlib.reload(config)

    def test_env_cors_with_spaces_and_empty(self, monkeypatch):
        monkeypatch.setenv("PDF_CORS_ORIGINS", " http://a.com , ,http://b.com ")
        importlib.reload(config)
        assert config.CORS_ORIGINS == ["http://a.com", "http://b.com"]
        monkeypatch.delenv("PDF_CORS_ORIGINS", raising=False)
        importlib.reload(config)

    def test_env_shutdown_token(self, monkeypatch):
        monkeypatch.setenv("PDF_SHUTDOWN_TOKEN", "secret123")
        importlib.reload(config)
        assert config.SHUTDOWN_TOKEN == "secret123"
        monkeypatch.delenv("PDF_SHUTDOWN_TOKEN", raising=False)
        importlib.reload(config)
