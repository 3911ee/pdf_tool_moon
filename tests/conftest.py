"""pytest fixtures"""
import sys
from pathlib import Path

import pytest
from PIL import Image
from pypdf import PdfWriter

# 确保项目根目录在 sys.path 中
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def tmp_dir(tmp_path):
    """临时工作目录"""
    return tmp_path


@pytest.fixture
def sample_pdf(tmp_path):
    """生成一个简单的测试 PDF（3 页）"""
    pdf_path = tmp_path / "test_sample.pdf"
    writer = PdfWriter()
    for i in range(3):
        writer.add_blank_page(width=595, height=842)  # A4
    writer.write(str(pdf_path))
    writer.close()
    return pdf_path


@pytest.fixture
def sample_pdfs(tmp_path):
    """生成两个测试 PDF"""
    pdfs = []
    for idx in range(2):
        pdf_path = tmp_path / f"test_{idx}.pdf"
        writer = PdfWriter()
        for i in range(2):  # 每个 2 页
            writer.add_blank_page(width=595, height=842)
        writer.write(str(pdf_path))
        writer.close()
        pdfs.append(pdf_path)
    return pdfs


@pytest.fixture
def sample_image(tmp_path):
    """生成一个测试图片（100x100 红色 PNG）"""
    img_path = tmp_path / "test_image.png"
    img = Image.new("RGB", (100, 100), color=(255, 0, 0))
    img.save(str(img_path), format="PNG")
    return img_path


@pytest.fixture
def sample_images(tmp_path):
    """生成两个测试图片"""
    paths = []
    for i, color in enumerate([(255, 0, 0), (0, 255, 0)]):
        img_path = tmp_path / f"test_img_{i}.png"
        img = Image.new("RGB", (100, 100), color=color)
        img.save(str(img_path), format="PNG")
        paths.append(img_path)
    return paths
