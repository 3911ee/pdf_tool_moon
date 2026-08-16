"""测试 engines/image_engine.py"""
import pytest
from PIL import Image
from pypdf import PdfReader

from engines.image_engine import images_to_pdf, convert_image_format


class TestImagesToPDF:
    def test_single_image(self, tmp_path, sample_image):
        output = tmp_path / "output.pdf"
        images_to_pdf([str(sample_image)], str(output))
        assert output.exists()
        reader = PdfReader(str(output))
        assert len(reader.pages) == 1
        reader.close()

    def test_multiple_images(self, tmp_path, sample_images):
        output = tmp_path / "output.pdf"
        images_to_pdf([str(p) for p in sample_images], str(output))
        assert output.exists()
        reader = PdfReader(str(output))
        assert len(reader.pages) == 2
        reader.close()

    def test_rgba_image(self, tmp_path):
        """RGBA 图片应被正确扁平化为白色背景"""
        img_path = tmp_path / "rgba.png"
        img = Image.new("RGBA", (50, 50), color=(255, 0, 0, 128))
        img.save(str(img_path), format="PNG")

        output = tmp_path / "output.pdf"
        images_to_pdf([str(img_path)], str(output))
        assert output.exists()
        reader = PdfReader(str(output))
        assert len(reader.pages) == 1
        reader.close()

    def test_empty_list(self, tmp_path):
        """空图片列表不应崩溃"""
        output = tmp_path / "output.pdf"
        images_to_pdf([], str(output))
        # 空列表时不产生 PDF 文件
        assert not output.exists()


class TestConvertImageFormat:
    def test_png_to_jpg(self, tmp_path, sample_image):
        out_dir = tmp_path / "converted"
        out_dir.mkdir()
        converted = convert_image_format([sample_image], "jpg", out_dir)
        assert len(converted) == 1
        assert converted[0].suffix == ".jpg"
        # 验证是有效的 JPEG
        img = Image.open(str(converted[0]))
        assert img.format == "JPEG"

    def test_png_to_webp(self, tmp_path, sample_image):
        out_dir = tmp_path / "converted"
        out_dir.mkdir()
        converted = convert_image_format([sample_image], "webp", out_dir)
        assert len(converted) == 1
        assert converted[0].suffix == ".webp"

    def test_batch_conversion(self, tmp_path, sample_images):
        out_dir = tmp_path / "converted"
        out_dir.mkdir()
        converted = convert_image_format(sample_images, "jpg", out_dir)
        assert len(converted) == 2
        for p in converted:
            assert p.suffix == ".jpg"
            assert p.exists()

    def test_tuple_items_preserve_original_names(self, tmp_path, sample_images):
        """(src, stem) 元组形式：输出保留用户原始文件名"""
        out_dir = tmp_path / "converted"
        out_dir.mkdir()
        items = [(sample_images[0], "照片A"), (sample_images[1], "照片B")]
        converted = convert_image_format(items, "png", out_dir)
        names = sorted(p.name for p in converted)
        assert names == ["照片A.png", "照片B.png"]

    def test_duplicate_names_not_overwritten(self, tmp_path, sample_images):
        out_dir = tmp_path / "converted"
        out_dir.mkdir()
        items = [(sample_images[0], "same"), (sample_images[1], "same")]
        converted = convert_image_format(items, "png", out_dir)
        names = sorted(p.name for p in converted)
        assert names == ["same.png", "same_2.png"]
        assert all(p.exists() for p in converted)


class TestImagesToPDFPageSize:
    def test_a4_mode(self, tmp_path, sample_image):
        output = tmp_path / "output.pdf"
        images_to_pdf([str(sample_image)], str(output), page_size="a4")
        reader = PdfReader(str(output))
        page = reader.pages[0]
        w = float(page.mediabox.width)
        h = float(page.mediabox.height)
        assert abs(w - 595) < 2 and abs(h - 842) < 2
        reader.close()
