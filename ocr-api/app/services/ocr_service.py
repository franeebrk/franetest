"""
OCR Service
-----------
Strategy:
  - PDF (text-based)  → pymupdf
  - PDF (scanned)     → pdf2image → Tesseract per page
  - Image             → table detection (img2table), fallback Tesseract
"""
from __future__ import annotations

import io
import re
import logging

try:
    import pdfplumber
except ImportError:
    pdfplumber = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


class OCRService:
    TEXT_PDF_THRESHOLD = 50

    def process(self, data: bytes, suffix: str, filename: str = "file") -> str:
        if suffix == ".pdf":
            return self._process_pdf(data, filename)
        return self._process_image(data, filename)

    def _process_pdf(self, data: bytes, filename: str) -> str:
        try:
            import fitz
        except ImportError:
            raise RuntimeError("pymupdf not installed")

        pages_text: list[str] = []
        with fitz.open(stream=data, filetype="pdf") as doc:
            for page in doc:
                pages_text.append(page.get_text().strip())

        total_chars = sum(len(t) for t in pages_text)

        if total_chars >= self.TEXT_PDF_THRESHOLD:
            logger.info("Text-based PDF (%d chars). Using pymupdf.", total_chars)
            return self._pages_to_markdown(pages_text)

        logger.info("Scanned PDF (%d chars). Falling back to Tesseract.", total_chars)
        return self._ocr_pdf_with_tesseract(data)

    def _ocr_pdf_with_tesseract(self, data: bytes) -> str:
        try:
            from pdf2image import convert_from_bytes
        except ImportError as e:
            raise RuntimeError("pdf2image not installed") from e

        images = convert_from_bytes(data, dpi=300)
        pages_text = [self._process_image_obj(img) for img in images]
        return self._pages_to_markdown(pages_text)

    def _process_image(self, data: bytes, filename: str) -> str:
        from PIL import Image
        img = Image.open(io.BytesIO(data))
        return self._process_image_obj(img, raw_bytes=data)

    def _process_image_obj(self, img, raw_bytes: bytes | None = None) -> str:
        table_md = self._extract_tables(img, raw_bytes)
        if table_md:
            return table_md
        text = self._tesseract_image(img)
        return self._to_markdown(text)

    def _extract_tables(self, img, raw_bytes: bytes | None = None) -> str:
        try:
            from img2table.ocr import TesseractOCR
            from img2table.document import Image as Img2Image
        except ImportError:
            return ""

        try:
            ocr_engine = TesseractOCR(lang="eng")
        except OSError:
            return ""

        try:
            src = raw_bytes if raw_bytes is not None else self._pil_to_bytes(img)
            doc = Img2Image(src=io.BytesIO(src))
            extracted = doc.extract_tables(ocr=ocr_engine, implicit_rows=True, borderless_tables=False)
        except Exception:
            return ""

        if not extracted:
            return ""

        parts = []
        for table in extracted:
            md = self._dataframe_to_markdown(table.df)
            if md:
                parts.append(md)

        return "\n\n".join(parts)

    def _dataframe_to_markdown(self, df) -> str:
        if df is None or df.empty:
            return ""

        df = df.fillna("")
        rows = df.values.tolist()
        if not rows:
            return ""

        header = [str(c).strip() for c in rows[0]]
        body = rows[1:]

        def fmt_row(cells):
            return "| " + " | ".join(str(c).strip().replace("\n", " ") for c in cells) + " |"

        lines = [fmt_row(header), "| " + " | ".join("---" for _ in header) + " |"]
        for row in body:
            lines.append(fmt_row(row))

        return "\n".join(lines)

    @staticmethod
    def _pil_to_bytes(img) -> bytes:
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    def _tesseract_image(self, img) -> str:
        import pytesseract
        try:
            osd = pytesseract.image_to_osd(img)
            angle = int(re.search(r'Rotate: (\d+)', osd).group(1))
            if angle != 0:
                img = img.rotate(-angle, expand=True)
        except Exception:
            pass

        config = "--psm 3 --oem 1"
        return pytesseract.image_to_string(img, config=config, lang="eng+hrv").strip()

    def _pages_to_markdown(self, pages: list[str]) -> str:
        if len(pages) == 1:
            return self._to_markdown(pages[0])

        parts = []
        for i, page_text in enumerate(pages, start=1):
            parts.append(f"## Page {i}\n\n{self._to_markdown(page_text)}")
        return "\n\n---\n\n".join(parts)

    def _to_markdown(self, raw: str) -> str:
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

            bullet_match = re.match(r'^[\-\*\•]\s+(.+)', stripped)
            if bullet_match:
                out.append(f"- {bullet_match.group(1)}")
                prev_blank = False
                continue

            num_match = re.match(r'^(\d+[\.\)]\s+)(.+)', stripped)
            if num_match:
                out.append(f"{num_match.group(1)}{num_match.group(2)}")
                prev_blank = False
                continue

            out.append(stripped)
            prev_blank = False

        return "\n".join(out).strip()
