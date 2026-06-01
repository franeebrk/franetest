"""
kod s glavnom logikom, ostavljam komentare.
namjerno odvojeno od rutera da se moze testirati i mijenjati bez api-ja.


Princip rada:
PDF ide odluka po stranici, ako je digitalna automatski se čita sa PyMuPDF, a skenirana ide na OCR obradu
Kod slike se prvo provjerava ima li tablica, a zatim Tesseract OCR
"""
from __future__ import annotations

import io
import re


class OCRService:
    # Prag broja znakova koji će razlikovati digitalni i skenirani PDF. Ovo je prvotna logika, svakako će provjera
    # ići po stranici

    TEXT_PDF_THRESHOLD = 50

    def process(self, data: bytes, suffix: str, filename: str = "file") -> str:
        """Ulazna točka: prema ekstenziji bira PDF ili slikovni put."""
        if suffix == ".pdf":
            return self._process_pdf(data)
        return self._process_image(data)

    def _process_pdf(self, data: bytes) -> str:
        # fitz mi treba zbog PyMuPDF-a, uvozim lokalno
        import fitz

        with fitz.open(stream=data, filetype="pdf") as doc:
            # Svaka stranica zasebno
            pages_md = [self._page_to_markdown(page) for page in doc]
        return self._join_pages(pages_md)

    def _page_to_markdown(self, page) -> str:
        # digitalno ili skenirano po stranici da mi produ i mjesoviti PDF-ovi
        if len(page.get_text().strip()) >= self.TEXT_PDF_THRESHOLD:
            return self._digital_page(page)

        # Skeniranu stranicu PyMuPDF rasterizira u sliku, pa ide na OCR
        from PIL import Image
        pix = page.get_pixmap(dpi=300)
        return self._process_image_obj(Image.open(io.BytesIO(pix.tobytes("png"))))

    def _digital_page(self, page) -> str:
        """
       Tablice vadim posebno jer kad se skeniraju bez obrade u markdownu su rezultati loši
        """
        import fitz

        tables = page.find_tables().tables
        table_rects = [fitz.Rect(t.bbox) for t in tables]
        # idem po y
        elements: list[tuple[float, str]] = []

        
        for table, rect in zip(tables, table_rects):
            elements.append((rect.y0, table.to_markdown().strip()))

        # blok-tekst izvan tablica
        for block in page.get_text("blocks"):
            x0, y0, x1, y1, text = block[0], block[1], block[2], block[3], block[4]
            if not text.strip():
                continue
            rect = fitz.Rect(x0, y0, x1, y1)
            # Blok kojem više od pola povrsine leži unutar tablice preskačemo (inace bi se pojavio dvaput)
            if any((rect & tr).get_area() > 0.5 * rect.get_area() for tr in table_rects):
                continue
            elements.append((y0, self._to_markdown(text.strip())))

        # slažem odozgo
        elements.sort(key=lambda e: e[0])
        return "\n\n".join(content for _, content in elements if content)

    def _join_pages(self, pages_md: list[str]) -> str:
        # estetike radi: ako je dokument od jedne stranice ne stavljam ##Page
        if len(pages_md) == 1:
            return pages_md[0].strip()
        parts = [f"## Page {i}\n\n{md.strip()}" for i, md in enumerate(pages_md, start=1)]
        return "\n\n---\n\n".join(parts)

    def _process_image(self, data: bytes) -> str:
        from PIL import Image
        # img2table traži bajtove
        return self._process_image_obj(Image.open(io.BytesIO(data)), raw_bytes=data)

    def _process_image_obj(self, img, raw_bytes: bytes | None = None) -> str:
        # provjera tablice
        table_md = self._extract_tables(img, raw_bytes)
        if table_md:
            return table_md
        # inače OCR
        return self._to_markdown(self._tesseract_image(img))

    def _extract_tables(self, img, raw_bytes: bytes | None = None) -> str:
        # Detekcija tablica na slici s img2table
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
            # implicit_rows=True hvata retke odvojene samo razmakom;
            # borderless_tables=False -> tražimo tablice s vidljivim linijama
            # (uključivanje borderless često lažno proglasi obični tekst tablicom).
            extracted = doc.extract_tables(ocr=ocr_engine, implicit_rows=True, borderless_tables=False)
        except Exception:
            return ""

        parts = [self._dataframe_to_markdown(t.df) for t in extracted]
        return "\n\n".join(p for p in parts if p)

    def _dataframe_to_markdown(self, df) -> str:
        # Pretvara pandas DataFrame (rezultat koji imamo s img2table) u markdown tablicu
        if df is None or df.empty:
            return ""
        df = df.fillna("")
        rows = df.values.tolist()
        if not rows:
            return ""

        def fmt_row(cells):
            # Novi redovi unutar ćelije rušili bi Markdown tablicu pa idu u razmak
            return "| " + " | ".join(str(c).strip().replace("\n", " ") for c in cells) + " |"

        # Prvi red je zaglavlje, zatim obavezni red razdjelnika, pa tijelo
        lines = [fmt_row(rows[0]), "| " + " | ".join("---" for _ in rows[0]) + " |"]
        lines += [fmt_row(r) for r in rows[1:]]
        return "\n".join(lines)

    @staticmethod
    def _pil_to_bytes(img) -> bytes:
        #PNG bajtovi ako nemamo originalne
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    def _preprocess(self, img):
        # preprocess:
        # 1. grayscale - boja
        # 2. denoise - uklanja šum sa skenova ili mutnih slika
        # 3. Otsu prag - binarizacija (crni tekst/bijela pozadina)
        try:
            import cv2
            import numpy as np
            from PIL import Image as PILImage
            gray = cv2.cvtColor(np.array(img.convert("RGB")), cv2.COLOR_RGB2GRAY)
            gray = cv2.fastNlMeansDenoising(gray, h=30)
            _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            return PILImage.fromarray(binary)
        except Exception:
            return img

    def _tesseract_image(self, img) -> str:
        #finalno
        import pytesseract
        # OSD prepozna i ispravlja rotirane slike
        try:
            angle = int(re.search(r"Rotate: (\d+)", pytesseract.image_to_osd(img)).group(1))
            if angle:
                img = img.rotate(-angle, expand=True)
        except Exception:
            pass
        img = self._preprocess(img)
        # opcija eng+hrv radi
        return pytesseract.image_to_string(img, config="--psm 3 --oem 1", lang="eng+hrv").strip()

    def _to_markdown(self, raw: str) -> str:
        if not raw:
            return ""

        out: list[str] = []
        prev_blank = True
        for line in raw.splitlines():
            stripped = line.strip()

            if not stripped:
                if not prev_blank:
                    out.append("")
                prev_blank = True
                continue

            bullet = re.match(r"^[\-\*\•]\s+(.+)", stripped)
            num = re.match(r"^(\d+[\.\)]\s+)(.+)", stripped)
            if bullet:
                out.append(f"- {bullet.group(1)}")
            elif num:
                out.append(f"{num.group(1)}{num.group(2)}")
            else:
                out.append(stripped)
            prev_blank = False

        return "\n".join(out).strip()
