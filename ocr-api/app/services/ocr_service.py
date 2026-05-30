"""
OCR Service
-----------
Strategy:
  - PDF (text-based)  → pdfplumber (fast, perfect fidelity, no OCR needed)
  - PDF (scanned)     → pdf2image → Tesseract per page
  - Image             → Tesseract

Output is always Markdown: headings are preserved where detected,
paragraphs are separated by blank lines.
"""
from __future__ import annotations

import io
import re
import logging
from pathlib import Path

try:
    import pdfplumber
except ImportError:
    pdfplumber = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


class OCRService:
    # Minimum characters extracted by pdfplumber to consider a PDF text-based
    TEXT_PDF_THRESHOLD = 50

    def process(self, data: bytes, suffix: str, filename: str = "file") -> str:
        if suffix == ".pdf":
            return self._process_pdf(data, filename)
        return self._process_image(data, filename)

    # ------------------------------------------------------------------
    # PDF handling
    # ------------------------------------------------------------------

    def _process_pdf(self, data: bytes, filename: str) -> str:
        """Try pdfplumber first; fall back to Tesseract for scanned PDFs."""
        if pdfplumber is None:
            raise RuntimeError("pdfplumber not installed")

        pages_text: list[str] = []

        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                pages_text.append(text.strip())

        total_chars = sum(len(t) for t in pages_text)

        if total_chars >= self.TEXT_PDF_THRESHOLD:
            logger.info("Text-based PDF detected (%d chars). Using pdfplumber.", total_chars)
            return self._pages_to_markdown(pages_text)

        logger.info("Scanned PDF detected (only %d chars). Falling back to Tesseract.", total_chars)
        return self._ocr_pdf_with_tesseract(data)

    def _ocr_pdf_with_tesseract(self, data: bytes) -> str:
        try:
            from pdf2image import convert_from_bytes
        except ImportError as e:
            raise RuntimeError("pdf2image not installed") from e

        images = convert_from_bytes(data, dpi=300)
        pages_text = [self._tesseract_image(img) for img in images]
        return self._pages_to_markdown(pages_text)

    # ------------------------------------------------------------------
    # Image handling
    # ------------------------------------------------------------------

    def _process_image(self, data: bytes, filename: str) -> str:
        try:
            from PIL import Image
        except ImportError as e:
            raise RuntimeError("Pillow not installed") from e

        img = Image.open(io.BytesIO(data))
        text = self._tesseract_image(img)
        return self._to_markdown(text)

    # ------------------------------------------------------------------
    # Tesseract wrapper
    # ------------------------------------------------------------------

    def _tesseract_image(self, img) -> str:
        try:
            import pytesseract
        except ImportError as e:
            raise RuntimeError("pytesseract not installed") from e

        # PSM 3 = fully automatic page segmentation (default)
        config = "--psm 3 --oem 1"
        return pytesseract.image_to_string(img, config=config, lang="eng+hrv").strip()

    # ------------------------------------------------------------------
    # Markdown conversion helpers
    # ------------------------------------------------------------------

    def _pages_to_markdown(self, pages: list[str]) -> str:
        if len(pages) == 1:
            return self._to_markdown(pages[0])

        parts: list[str] = []
        for i, page_text in enumerate(pages, start=1):
            parts.append(f"## Page {i}\n\n{self._to_markdown(page_text)}")
        return "\n\n---\n\n".join(parts)

    def _to_markdown(self, raw: str) -> str:
        """
        Light-touch conversion of raw OCR text to Markdown.
        - Lines that look like headings (ALL CAPS / Title Case, short) → ## heading
        - Bullet-like lines → Markdown list items
        - Everything else → paragraph (blank line between blocks)
        """
        if not raw:
            return ""

        lines = raw.splitlines()
        out: list[str] = []
        prev_blank = True

        for line in lines:
            stripped = line.strip()

            if not stripped:
                if not prev_blank:
                    out.append("")
                prev_blank = True
                continue

            # Heading detection: short ALL-CAPS or Title Case line (<= 80 chars, no sentence punctuation)
            if self._looks_like_heading(stripped):
                if not prev_blank:
                    out.append("")
                out.append(f"## {stripped}")
                out.append("")
                prev_blank = True
                continue

            # Bullet detection
            bullet_match = re.match(r'^[\-\*\•]\s+(.+)', stripped)
            if bullet_match:
                out.append(f"- {bullet_match.group(1)}")
                prev_blank = False
                continue

            # Numbered list
            num_match = re.match(r'^(\d+[\.\)]\s+)(.+)', stripped)
            if num_match:
                out.append(f"{num_match.group(1)}{num_match.group(2)}")
                prev_blank = False
                continue

            out.append(stripped)
            prev_blank = False

        return "\n".join(out).strip()

    @staticmethod
    def _looks_like_heading(line: str) -> bool:
        if len(line) > 80:
            return False
        # Skip if it ends with common sentence punctuation
        if line.endswith((".", ",", ";", ":")):
            return False
        words = line.split()
        if len(words) > 10:
            return False
        # ALL CAPS
        if line == line.upper() and any(c.isalpha() for c in line):
            return True
        # Title Case (at least 2 words, all capitalised)
        if len(words) >= 2 and all(w[0].isupper() for w in words if w[0].isalpha()):
            return True
        return False
