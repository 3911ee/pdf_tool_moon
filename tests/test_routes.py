"""路由层 API 测试（TestClient）：安全防护 + 核心功能回归"""
import io
import zipfile

import pytest
from PIL import Image
from pypdf import PdfReader, PdfWriter
import fitz
from fastapi.testclient import TestClient

import utils.file_utils


# ---- 工具函数 ----

def _pdf_bytes(pages=3):
    """生成内存 PDF 字节"""
    w = PdfWriter()
    for _ in range(pages):
        w.add_blank_page(width=595, height=842)
    buf = io.BytesIO()
    w.write(buf)
    w.close()
    return buf.getvalue()


def _image_pdf_bytes():
    """生成含一张图片的 PDF（用于压缩测试）"""
    img_buf = io.BytesIO()
    img = Image.new("RGB", (400, 400), color=(200, 30, 30))
    img.save(img_buf, format="PNG")
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_image(fitz.Rect(50, 50, 450, 450), stream=img_buf.getvalue())
    out = doc.tobytes()
    doc.close()
    return out


def _png_bytes():
    buf = io.BytesIO()
    img = Image.new("RGB", (100, 100), color=(0, 128, 255))
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def client(tmp_path, monkeypatch):
    """测试客户端：上传/输出目录重定向到临时目录，避免污染项目目录"""
    from routers import convert as rc, pdf_ops as rp, download as rd
    up = tmp_path / "uploads"
    out = tmp_path / "outputs"
    up.mkdir()
    out.mkdir()
    monkeypatch.setattr(rc, "UPLOAD_DIR", up)
    monkeypatch.setattr(rc, "OUTPUT_DIR", out)
    monkeypatch.setattr(rp, "UPLOAD_DIR", up)
    monkeypatch.setattr(rp, "OUTPUT_DIR", out)
    monkeypatch.setattr(rd, "OUTPUT_DIR", out)

    from app import app
    with TestClient(app) as c:
        yield c, up, out


# ---- 下载安全 ----

class TestDownloadSecurity:
    def test_download_ok(self, client):
        c, up, out = client
        files = [
            ("files", ("a.pdf", _pdf_bytes(), "application/pdf")),
            ("files", ("b.pdf", _pdf_bytes(2), "application/pdf")),
        ]
        r = c.post("/api/merge-pdf", files=files)
        assert r.status_code == 200
        did = r.json()["download_id"]
        assert "_merged_" in did  # 输出命名使用英文后缀
        dl = c.get(f"/api/download/{did}?ext=pdf")
        assert dl.status_code == 200
        assert dl.headers["content-type"] == "application/pdf"

    def test_download_without_ext(self, client):
        c, up, out = client
        files = [
            ("files", ("a.pdf", _pdf_bytes(), "application/pdf")),
            ("files", ("b.pdf", _pdf_bytes(2), "application/pdf")),
        ]
        r = c.post("/api/merge-pdf", files=files)
        did = r.json()["download_id"]
        assert c.get(f"/api/download/{did}").status_code == 200

    def test_download_ext_traversal_rejected(self, client):
        c, up, out = client
        # ext 参数带路径穿越字符必须被拒绝
        r = c.get("/api/download/x?ext=..%2F..%2Fconfig")
        assert r.status_code == 400
        r = c.get("/api/download/x?ext=..%2F..%2F..%2Fwindows%2Fwin.ini")
        assert r.status_code == 400

    def test_download_id_traversal_rejected(self, client):
        c, up, out = client
        # ".." 会被路径规范化到 /api（未命中下载路由，404）；编码斜杠同样无法命中
        assert c.get("/api/download/..").status_code == 404
        assert c.get("/api/download/..%2F..%2Fconfig").status_code in (400, 404)

    def test_download_missing_file_404(self, client):
        c, up, out = client
        assert c.get("/api/download/ghost?ext=pdf").status_code == 404


# ---- 文件名注入防护 ----

class TestFilenameInjection:
    def test_merge_with_traversal_filename(self, client):
        c, up, out = client
        files = [
            ("files", ("..\\..\\evil.pdf", _pdf_bytes(), "application/pdf")),
            ("files", ("b.pdf", _pdf_bytes(2), "application/pdf")),
        ]
        r = c.post("/api/merge-pdf", files=files)
        assert r.status_code == 200
        did = r.json()["download_id"]
        assert ".." not in did and "/" not in did and "\\" not in did
        # 输出必须落在 outputs 目录内
        assert (out / f"{did}.pdf").exists()
        assert not (out.parent / "evil_合并.pdf").exists()
        assert not (out.parent / "evil.pdf").exists()

    def test_convert_format_with_traversal_filename(self, client):
        c, up, out = client
        r = c.post(
            "/api/convert-format?target=png",
            files=[("files", ("../../up.png", _png_bytes(), "image/png"))],
        )
        assert r.status_code == 200
        did = r.json()["download_id"]
        assert ".." not in did
        assert (out / f"{did}.zip").exists()


# ---- 上传限制 ----

class TestUploadLimits:
    def test_too_many_files(self, client):
        c, up, out = client
        files = [("files", (f"f{i}.pdf", _pdf_bytes(1), "application/pdf")) for i in range(21)]
        r = c.post("/api/merge-pdf", files=files)
        assert r.status_code == 400

    def test_size_limit_413(self, client, monkeypatch):
        monkeypatch.setattr(utils.file_utils, "MAX_UPLOAD_SIZE", 512)
        c, up, out = client
        files = [
            ("files", ("a.pdf", _pdf_bytes(3), "application/pdf")),
            ("files", ("b.pdf", _pdf_bytes(2), "application/pdf")),
        ]
        r = c.post("/api/merge-pdf", files=files)
        assert r.status_code == 413

    def test_empty_file_400(self, client):
        c, up, out = client
        r = c.post(
            "/api/merge-pdf",
            files=[
                ("files", ("a.pdf", b"", "application/pdf")),
                ("files", ("b.pdf", _pdf_bytes(1), "application/pdf")),
            ],
        )
        assert r.status_code == 400


# ---- 核心功能回归 ----

class TestConvertFormat:
    def test_png_to_jpg_and_zip_download(self, client):
        """回归：修复端点函数与引擎同名遮蔽导致的 500"""
        c, up, out = client
        r = c.post(
            "/api/convert-format?target=jpg",
            files=[("files", ("test.png", _png_bytes(), "image/png"))],
        )
        assert r.status_code == 200
        did = r.json()["download_id"]
        dl = c.get(f"/api/download/{did}?ext=zip")
        assert dl.status_code == 200
        zf = zipfile.ZipFile(io.BytesIO(dl.content))
        names = zf.namelist()
        assert any(n.endswith(".jpg") for n in names)
        # 保留用户原始文件名（非 uid 临时名）
        assert "test.jpg" in names

    def test_bad_target_400(self, client):
        c, up, out = client
        r = c.post(
            "/api/convert-format?target=exe",
            files=[("files", ("t.png", _png_bytes(), "image/png"))],
        )
        assert r.status_code == 400


class TestImageToPdf:
    def test_a4_page_size(self, client):
        c, up, out = client
        r = c.post(
            "/api/convert-image?page_size=a4",
            files=[("files", ("pic.png", _png_bytes(), "image/png"))],
        )
        assert r.status_code == 200
        did = r.json()["download_id"]
        dl = c.get(f"/api/download/{did}?ext=pdf")
        reader = PdfReader(io.BytesIO(dl.content))
        page = reader.pages[0]
        w = float(page.mediabox.width)
        h = float(page.mediabox.height)
        assert abs(w - 595) < 2 and abs(h - 842) < 2
        reader.close()

    def test_bad_page_size_400(self, client):
        c, up, out = client
        r = c.post(
            "/api/convert-image?page_size=a3",
            files=[("files", ("pic.png", _png_bytes(), "image/png"))],
        )
        assert r.status_code == 400


class TestPreviewFlow:
    def test_preview_and_lazy_page(self, client):
        c, up, out = client
        r = c.post(
            "/api/preview-pages",
            files=[("file", ("doc.pdf", _pdf_bytes(3), "application/pdf"))],
        )
        assert r.status_code == 200
        data = r.json()
        assert data["success"] and data["total"] == 3
        assert data["preview_id"]
        assert len(data["pages"]) == 3  # 3 页少于首批渲染数

        # 按需加载单页
        p = c.get(f"/api/preview-page?preview_id={data['preview_id']}&page=2")
        assert p.status_code == 200
        assert p.json()["num"] == 2
        assert p.json()["src"].startswith("data:image/jpeg;base64,")

    def test_preview_page_out_of_range(self, client):
        c, up, out = client
        r = c.post(
            "/api/preview-pages",
            files=[("file", ("doc.pdf", _pdf_bytes(2), "application/pdf"))],
        )
        pid = r.json()["preview_id"]
        assert c.get(f"/api/preview-page?preview_id={pid}&page=99").status_code == 400

    def test_preview_invalid_id(self, client):
        c, up, out = client
        assert c.get("/api/preview-page?preview_id=../../x&page=1").status_code == 400

    def test_preview_expired_id_404(self, client):
        c, up, out = client
        assert c.get(f"/api/preview-page?preview_id={'ab' * 16}&page=1").status_code == 404


class TestDeletePages:
    def test_delete_pages_and_download(self, client):
        c, up, out = client
        r = c.post(
            "/api/delete-pages?pages=2",
            files=[("file", ("doc.pdf", _pdf_bytes(3), "application/pdf"))],
        )
        assert r.status_code == 200
        did = r.json()["download_id"]
        dl = c.get(f"/api/download/{did}?ext=pdf")
        reader = PdfReader(io.BytesIO(dl.content))
        assert len(reader.pages) == 2
        reader.close()

    def test_delete_all_pages_rejected(self, client):
        c, up, out = client
        r = c.post(
            "/api/delete-pages?pages=1-3",
            files=[("file", ("doc.pdf", _pdf_bytes(3), "application/pdf"))],
        )
        assert r.status_code == 400


class TestSplitPdf:
    def test_split_by_position(self, client):
        c, up, out = client
        r = c.post(
            "/api/split-pdf?positions=2",
            files=[("file", ("doc.pdf", _pdf_bytes(3), "application/pdf"))],
        )
        assert r.status_code == 200
        did = r.json()["download_id"]
        dl = c.get(f"/api/download/{did}?ext=zip")
        zf = zipfile.ZipFile(io.BytesIO(dl.content))
        names = zf.namelist()
        assert len(names) == 2
        assert all("pages_" in n or "page_" in n for n in names)


class TestCompressPdf:
    def test_compress_with_stats(self, client):
        c, up, out = client
        r = c.post(
            "/api/compress-pdf?level=extreme",
            files=[("file", ("img.pdf", _image_pdf_bytes(), "application/pdf"))],
        )
        assert r.status_code == 200
        data = r.json()
        assert data["success"]
        assert data["images_processed"] >= 1
        assert data["images_skipped"] >= 0
        assert "ratio" in data
        assert (out / f"{data['download_id']}.pdf").exists()

    def test_compress_bad_level_400(self, client):
        c, up, out = client
        r = c.post(
            "/api/compress-pdf?level=nuclear",
            files=[("file", ("d.pdf", _pdf_bytes(1), "application/pdf"))],
        )
        assert r.status_code == 400


# ---- 系统端点 ----

class TestSystem:
    def test_health(self, client):
        c, up, out = client
        assert c.get("/api/health").json() == {"status": "ok"}

    def test_task_unknown_404(self, client):
        c, up, out = client
        assert c.get("/api/task/" + "0" * 32).status_code == 404
        assert c.get("/api/task/bad!id").status_code == 404

    def test_task_progress_flow(self, client):
        from utils.task_progress import set_progress
        tid = "f" * 32
        set_progress(tid, 66, "测试")
        c, up, out = client
        r = c.get(f"/api/task/{tid}")
        assert r.status_code == 200
        assert r.json()["percent"] == 66

    def test_shutdown_requires_token(self, client, monkeypatch):
        from routers import system as rs
        monkeypatch.setattr(rs, "SHUTDOWN_TOKEN", "secret123")
        monkeypatch.setattr(rs, "_trigger_shutdown", lambda: None)
        c, up, out = client
        assert c.post("/api/shutdown").status_code == 403
        assert c.post("/api/shutdown", headers={"X-Shutdown-Token": "wrong"}).status_code == 403
        assert c.post("/api/shutdown", headers={"X-Shutdown-Token": "secret123"}).status_code == 200

    def test_shutdown_remote_denied_without_token(self, client, monkeypatch):
        from routers import system as rs
        monkeypatch.setattr(rs, "SHUTDOWN_TOKEN", "")
        monkeypatch.setattr(rs, "_trigger_shutdown", lambda: None)
        c, up, out = client
        # TestClient 的客户端地址是 "testclient"，应视为非本机被拒绝
        assert c.post("/api/shutdown").status_code == 403
