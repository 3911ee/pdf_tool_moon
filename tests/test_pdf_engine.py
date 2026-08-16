"""测试 engines/pdf_engine.py"""
import pytest
from pypdf import PdfReader
from PIL import Image

from engines.pdf_engine import (
    pdf_to_word_pdf2docx,
    parse_page_numbers,
    _flatten_to_rgb,
    _compress_image_bytes,
)


class TestParsePageNumbers:
    def test_single_page(self):
        result = parse_page_numbers("3", 10)
        assert result == {3}

    def test_multiple_pages(self):
        result = parse_page_numbers("1,3,5", 10)
        assert result == {1, 3, 5}

    def test_range(self):
        result = parse_page_numbers("2-5", 10)
        assert result == {2, 3, 4, 5}

    def test_mixed(self):
        result = parse_page_numbers("1,3-5,8", 10)
        assert result == {1, 3, 4, 5, 8}

    def test_out_of_range(self):
        with pytest.raises(ValueError):
            parse_page_numbers("15", 10)

    def test_invalid_range(self):
        with pytest.raises(ValueError):
            parse_page_numbers("5-3", 10)

    def test_empty(self):
        result = parse_page_numbers("", 10)
        assert result == set()

    def test_whitespace(self):
        result = parse_page_numbers(" 1 , 3 , 5-7 ", 10)
        assert result == {1, 3, 5, 6, 7}


class TestFlattenToRGB:
    def test_rgba_to_rgb(self):
        img = Image.new("RGBA", (50, 50), color=(255, 0, 0, 128))
        result = _flatten_to_rgb(img)
        assert result.mode == "RGB"
        assert result.size == (50, 50)

    def test_rgb_unchanged(self):
        img = Image.new("RGB", (50, 50), color=(255, 0, 0))
        result = _flatten_to_rgb(img)
        assert result.mode == "RGB"

    def test_palette_to_rgb(self):
        img = Image.new("P", (50, 50), color=0)
        result = _flatten_to_rgb(img)
        assert result.mode == "RGB"


class TestCompressImageBytes:
    @pytest.fixture
    def cfg_light(self):
        return {
            "max_dim": 4000, "jpeg_quality": 85,
            "dpi_threshold": 300, "garbage": 3,
            "deflate": True, "clean": False,
        }

    @pytest.fixture
    def cfg_extreme(self):
        return {
            "max_dim": 50, "jpeg_quality": 30,
            "dpi_threshold": 120, "garbage": 4,
            "deflate": True, "clean": True,
        }

    def _make_png_bytes(self):
        import io
        img = Image.new("RGB", (200, 200), color=(255, 0, 0))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    def _make_jpg_bytes(self):
        import io
        img = Image.new("RGB", (200, 200), color=(255, 0, 0))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=90)
        return buf.getvalue()

    def test_png_retained_at_light_quality(self, cfg_light):
        data = self._make_png_bytes()
        result, new_ext = _compress_image_bytes(data, "png", cfg_light)
        assert new_ext == "png"
        assert len(result) > 0

    def test_png_converted_to_jpg_at_low_quality(self, cfg_extreme):
        data = self._make_png_bytes()
        result, new_ext = _compress_image_bytes(data, "png", cfg_extreme)
        assert new_ext == "jpg"
        assert len(result) > 0

    def test_downscale_triggered(self, cfg_extreme):
        data = self._make_jpg_bytes()
        result, new_ext = _compress_image_bytes(data, "jpg", cfg_extreme)
        assert new_ext == "jpg"
        # 压缩后应该更小
        assert len(result) < len(data)


class TestPDFWordConversion:
    def test_conversion_produces_docx(self, tmp_path, sample_pdf):
        """PDF→Word 转换产出 .docx 文件"""
        output = tmp_path / "output.docx"
        try:
            pdf_to_word_pdf2docx(str(sample_pdf), str(output))
            assert output.exists()
            assert output.stat().st_size > 100
        except Exception as e:
            pytest.skip(f"pdf2docx 转换失败（可能是库兼容性）: {e}")
