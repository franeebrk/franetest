import struct
import zlib
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.services.ocr_service import OCRService

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_reject_unsupported_extension():
    r = client.post("/api/v1/ocr", files={"file": ("document.txt", b"hello", "text/plain")})
    assert r.status_code == 400
    assert "Unsupported file type" in r.json()["detail"]


def test_reject_empty_file():
    r = client.post("/api/v1/ocr", files={"file": ("image.png", b"", "image/png")})
    assert r.status_code == 400
    assert "empty" in r.json()["detail"].lower()


def test_to_markdown_bullet_list():
    result = OCRService()._to_markdown("• Item one\n• Item two")
    assert "- Item one" in result
    assert "- Item two" in result


def test_to_markdown_empty():
    assert OCRService()._to_markdown("") == ""


def test_join_pages_single_page():
    result = OCRService()._join_pages(["Hello world"])
    assert "## Page" not in result
    assert "Hello world" in result


def test_join_pages_multiple_pages():
    result = OCRService()._join_pages(["Page one content", "Page two content"])
    assert "## Page 1" in result
    assert "## Page 2" in result
    assert "---" in result


def _tiny_png() -> bytes:
    def chunk(name, data):
        c = struct.pack(">I", len(data)) + name + data
        return c + struct.pack(">I", zlib.crc32(name + data) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00"))
    png += chunk(b"IEND", b"")
    return png


@patch("app.services.ocr_service.OCRService._tesseract_image", return_value="Hello World")
def test_process_image_mocked(mock_tess):
    r = client.post("/api/v1/ocr", files={"file": ("test.png", _tiny_png(), "image/png")})
    assert r.status_code == 200
    body = r.json()
    assert body["filename"] == "test.png"
    assert "Hello World" in body["markdown"]


def test_process_text_pdf_mocked():
    expected_md = "## TITLE\n\nSome extracted text here."
    with patch.object(OCRService, "_process_pdf", return_value=expected_md):
        r = client.post("/api/v1/ocr", files={"file": ("doc.pdf", b"%PDF-fake", "application/pdf")})
        assert r.status_code == 200
        assert expected_md in r.json()["markdown"]


@patch("app.services.ocr_service.OCRService._tesseract_image", return_value="OCR TEXT PAGE 2")
def test_hybrid_pdf_digital_and_scanned(mock_tess):
    import fitz

    doc = fitz.open()
    doc.new_page().insert_text((72, 100), "Digitalni tekst koji PyMuPDF cita izravno bez OCR-a.")
    p2 = doc.new_page()
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 200, 200))
    pix.clear_with(255)
    p2.insert_image(p2.rect, pixmap=pix)
    data = doc.tobytes()
    doc.close()

    result = OCRService().process(data, ".pdf", "hybrid.pdf")

    assert "Digitalni tekst koji PyMuPDF cita izravno" in result
    assert "OCR TEXT PAGE 2" in result
    mock_tess.assert_called_once()
