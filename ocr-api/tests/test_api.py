"""
Tests for the OCR API.

Run with:  pytest -v
"""
import io
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from app.main import app
from app.services.ocr_service import OCRService

client = TestClient(app)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# Endpoint validation
# ---------------------------------------------------------------------------

def test_reject_unsupported_extension():
    r = client.post(
        "/api/v1/ocr",
        files={"file": ("document.txt", b"hello", "text/plain")},
    )
    assert r.status_code == 400
    assert "Unsupported file type" in r.json()["detail"]


def test_reject_empty_file():
    r = client.post(
        "/api/v1/ocr",
        files={"file": ("image.png", b"", "image/png")},
    )
    assert r.status_code == 400
    assert "empty" in r.json()["detail"].lower()


# ---------------------------------------------------------------------------
# OCRService unit tests
# ---------------------------------------------------------------------------

def test_to_markdown_all_caps_heading():
    svc = OCRService()
    result = svc._to_markdown("INVOICE\n\nDate: 2024-01-15")
    assert "## INVOICE" in result
    assert "Date: 2024-01-15" in result


def test_to_markdown_bullet_list():
    svc = OCRService()
    result = svc._to_markdown("• Item one\n• Item two")
    assert "- Item one" in result
    assert "- Item two" in result


def test_to_markdown_empty():
    svc = OCRService()
    assert OCRService()._to_markdown("") == ""


def test_looks_like_heading_all_caps():
    assert OCRService._looks_like_heading("SUMMARY") is True


def test_looks_like_heading_too_long():
    long_line = "A" * 90
    assert OCRService._looks_like_heading(long_line) is False


def test_looks_like_heading_ends_with_period():
    assert OCRService._looks_like_heading("Introduction.") is False


def test_pages_to_markdown_single_page():
    svc = OCRService()
    result = svc._pages_to_markdown(["Hello world"])
    assert "## Page" not in result
    assert "Hello world" in result


def test_pages_to_markdown_multiple_pages():
    svc = OCRService()
    result = svc._pages_to_markdown(["Page one content", "Page two content"])
    assert "## Page 1" in result
    assert "## Page 2" in result
    assert "---" in result


# ---------------------------------------------------------------------------
# Integration: image OCR (mocked Tesseract)
# ---------------------------------------------------------------------------

@patch("app.services.ocr_service.OCRService._tesseract_image", return_value="Hello World")
def test_process_image_mocked(mock_tess):
    """End-to-end through the endpoint with a tiny PNG (Tesseract mocked)."""
    # 1×1 red PNG
    import struct, zlib
    def make_png():
        def chunk(name, data):
            c = struct.pack(">I", len(data)) + name + data
            return c + struct.pack(">I", zlib.crc32(name + data) & 0xFFFFFFFF)
        png = b"\x89PNG\r\n\x1a\n"
        png += chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
        png += chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00"))
        png += chunk(b"IEND", b"")
        return png

    r = client.post(
        "/api/v1/ocr",
        files={"file": ("test.png", make_png(), "image/png")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["filename"] == "test.png"
    assert "Hello World" in body["markdown"]


# ---------------------------------------------------------------------------
# Integration: text PDF (mocked pdfplumber)
# ---------------------------------------------------------------------------

def test_process_text_pdf_mocked():
    expected_md = "## TITLE\n\nSome extracted text here."

    with patch.object(
        __import__("app.services.ocr_service", fromlist=["OCRService"]).OCRService,
        "_process_pdf",
        return_value=expected_md,
    ):
        r = client.post(
            "/api/v1/ocr",
            files={"file": ("doc.pdf", b"%PDF-fake", "application/pdf")},
        )
        assert r.status_code == 200
        body = r.json()
        assert "## TITLE" in body["markdown"]
        assert "Some extracted text here." in body["markdown"]
