"""
OCR servis
----------
Središnja poslovna logika. Odvojena je od HTTP sloja (routera) namjerno:
ovako se može testirati neovisno i lako zamijeniti drugi OCR engine bez
diranja API-ja.

Strategija obrade ovisi o tipu ulaza:
  - PDF (tekstualni / digitalni)  -> PyMuPDF (čita tekst + detektira tablice)
  - PDF (skenirani)               -> PyMuPDF rasterizira stranicu -> Tesseract
  - Slika                         -> detekcija tablica (img2table), inače Tesseract

Odluka digitalno/skenirano donosi se PO STRANICI, pa hibridni PDF (dio
stranica digitalan, dio skeniran) radi ispravno.
"""
from __future__ import annotations

import io
import re
import logging

logger = logging.getLogger(__name__)


class OCRService:
    # Prag (broj znakova) za razlikovanje digitalnog od skeniranog PDF-a.
    # Ako PyMuPDF iz cijelog dokumenta izvuče manje od ovoga, znači da u PDF-u
    # nema pravog teksta (samo slike) pa ga tretiramo kao skenirani i šaljemo
    # na OCR. 50 je namjerno nizak prag: digitalni PDF ima stotine/tisuće
    # znakova, a čisti sken ima 0, pa je granica vrlo "široka" i sigurna.
    TEXT_PDF_THRESHOLD = 50

    def process(self, data: bytes, suffix: str, filename: str = "file") -> str:
        """Ulazna točka servisa: prema ekstenziji bira PDF ili slikovni put."""
        if suffix == ".pdf":
            return self._process_pdf(data, filename)
        return self._process_image(data, filename)

    def _process_pdf(self, data: bytes, filename: str) -> str:
        """
        Dvoslojna strategija za PDF — glavni naglasak rješenja.

        Prvo PyMuPDF-om pokušamo izvući tekst iz cijelog dokumenta. Po količini
        teksta odlučujemo je li PDF digitalni ili skenirani i biramo put. Time
        skupi OCR pokrećemo samo kad je stvarno nužan, a za digitalne PDF-ove
        (računi, cjenici, ugovori) dobivamo i brži i precizniji rezultat.
        """
        try:
            import fitz  # PyMuPDF
        except ImportError:
            raise RuntimeError("pymupdf not installed")

        with fitz.open(stream=data, filetype="pdf") as doc:
            pages_md = [self._pdf_page_to_markdown_or_ocr(page) for page in doc]

        return self._join_pages(pages_md)

    def _pdf_page_to_markdown_or_ocr(self, page) -> str:
        """
        Odlučuje PER-STRANICU je li digitalna ili skenirana, a ne za cijeli
        dokument. To je ključno za hibridne PDF-ove (npr. digitalni ugovor +
        skenirani prilog s potpisom): kad bismo odluku donosili globalno, na
        digitalnim stranicama bi bilo dovoljno teksta da cijeli PDF proglasimo
        digitalnim, pa bi skenirane stranice tiho nestale iz rezultata jer na
        njima PyMuPDF ne vidi nikakav tekst.
        """
        text = page.get_text().strip()
        if len(text) >= self.TEXT_PDF_THRESHOLD:
            # Digitalna stranica -> čitamo izravno (tekst + tablice), bez OCR-a.
            logger.info("Stranica %d: digitalna (%d znakova).", page.number + 1, len(text))
            return self._pdf_page_to_markdown(page)

        # Skenirana stranica -> rasteriziramo JU u sliku i puštamo kroz isti
        # slikovni OCR put kao obične slike. Rasterizaciju radi sam PyMuPDF
        # (pixmap, 300 DPI) pa ne trebamo zaseban poppler/pdf2image.
        logger.info("Stranica %d: skenirana (%d znakova) -> OCR.", page.number + 1, len(text))
        from PIL import Image
        pix = page.get_pixmap(dpi=300)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        return self._process_image_obj(img)

    def _pdf_page_to_markdown(self, page) -> str:
        """
        Pretvara jednu stranicu digitalnog PDF-a u Markdown.

        Problem: PyMuPDF-ov običan get_text() čita linearno pa tablice "spljošti"
        u nečitljiv niz. Rješenje: tablice vadimo zasebno (find_tables) kao
        Markdown tablice, a ostali tekst kao blokove. Oboje nosi svoju y-koordinatu
        pa ih na kraju složimo redom kako stvarno stoje na stranici — tako tablica
        završi na svom mjestu, a ne nalijepljena na kraj.
        """
        import fitz

        tables = page.find_tables().tables
        table_rects = [fitz.Rect(t.bbox) for t in tables]

        # Skupljamo (y, markdown) parove; y nam služi za kasnije sortiranje po stranici.
        elements: list[tuple[float, str]] = []

        # 1) Tablice -> Markdown, zapamti gornji rub (y0) za redoslijed.
        for table, rect in zip(tables, table_rects):
            elements.append((rect.y0, table.to_markdown().strip()))

        # 2) Tekstualni blokovi izvan tablica.
        for block in page.get_text("blocks"):
            x0, y0, x1, y1, text = block[0], block[1], block[2], block[3], block[4]
            if not text.strip():
                continue
            rect = fitz.Rect(x0, y0, x1, y1)
            # Blok koji >50% površine leži unutar neke tablice preskačemo da se
            # isti sadržaj ne pojavi dvaput (jednom kao tekst, jednom kao tablica).
            inside_table = any(
                (rect & tr).get_area() > 0.5 * rect.get_area()
                for tr in table_rects
            )
            if inside_table:
                continue
            elements.append((y0, self._to_markdown(text.strip())))

        # Posloži sve odozgo prema dolje -> vjeran redoslijed originalne stranice.
        elements.sort(key=lambda e: e[0])
        return "\n\n".join(content for _, content in elements if content)

    def _join_pages(self, pages_md: list[str]) -> str:
        """
        Spaja već pripremljene Markdown stranice. Jednostranični dokument vraćamo
        bez "## Page" zaglavlja; višestranični dobiva naslov i '---' razdjelnik
        po stranici radi preglednosti.
        """
        if len(pages_md) == 1:
            return pages_md[0].strip()
        parts = [f"## Page {i}\n\n{md.strip()}" for i, md in enumerate(pages_md, start=1)]
        return "\n\n---\n\n".join(parts)

    def _process_image(self, data: bytes, filename: str) -> str:
        """Učita bajtove slike u PIL objekt i proslijedi na zajedničku obradu."""
        from PIL import Image
        img = Image.open(io.BytesIO(data))
        # raw_bytes prosljeđujemo jer img2table radi izravno na originalnim
        # bajtovima (izbjegava gubitak kvalitete kroz ponovno enkodiranje).
        return self._process_image_obj(img, raw_bytes=data)

    def _process_image_obj(self, img, raw_bytes: bytes | None = None) -> str:
        """
        Obrada jedne slike. Prvo pokušamo detektirati tablicu; ako je ima,
        vratimo strukturiranu Markdown tablicu. Ako ne, padamo na klasični
        Tesseract OCR cijele slike.
        """
        table_md = self._extract_tables(img, raw_bytes)
        if table_md:
            return table_md
        text = self._tesseract_image(img)
        return self._to_markdown(text)

    def _extract_tables(self, img, raw_bytes: bytes | None = None) -> str:
        """
        Detekcija tablica na slici pomoću img2table.

        Cijela metoda je "best effort": img2table i njegove ovisnosti su opcionalne,
        a detekcija može i ne uspjeti. Zato svaki korak hvatamo i u slučaju problema
        vraćamo prazan string -> pozivatelj tada jednostavno koristi obični OCR.
        """
        try:
            from img2table.ocr import TesseractOCR
            from img2table.document import Image as Img2Image
        except ImportError:
            return ""

        try:
            ocr_engine = TesseractOCR(lang="eng")
        except OSError:
            # Tesseract binarni nije dostupan -> nema smisla nastavljati.
            return ""

        try:
            src = raw_bytes if raw_bytes is not None else self._pil_to_bytes(img)
            doc = Img2Image(src=io.BytesIO(src))
            # implicit_rows=True hvata retke odvojene samo razmakom;
            # borderless_tables=False -> tražimo tablice s vidljivim linijama
            # (pouzdanije; uključivanje borderless često lažno proglasi obični
            # tekst tablicom).
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
        """Pretvara pandas DataFrame (rezultat img2table) u Markdown tablicu."""
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
        """Serijalizira PIL sliku u PNG bajtove (kad nemamo originalne bajtove)."""
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    def _preprocess(self, img):
        """
        Priprema slike prije OCR-a radi bolje točnosti Tesseracta.

        Koraci:
          1. grayscale  - boja ne nosi informaciju za OCR, samo smeta
          2. denoising  - uklanja zrnatost s lošijih fotografija/skenova
          3. Otsu prag  - automatski binarizira (crni tekst / bijela pozadina),
                          čime rubovi slova postaju oštri

        Sve je u try/except: ako OpenCV nije dostupan ili nešto pukne, vraćamo
        originalnu sliku (degradacija umjesto pada cijelog zahtjeva).
        """
        try:
            import cv2
            import numpy as np
            arr = np.array(img.convert("RGB"))
            gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
            gray = cv2.fastNlMeansDenoising(gray, h=30)
            _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            from PIL import Image as PILImage
            return PILImage.fromarray(binary)
        except Exception:
            return img

    def _tesseract_image(self, img) -> str:
        """Pokreće Tesseract nad slikom uz automatsku korekciju rotacije i preprocessing."""
        import pytesseract
        # OSD (Orientation and Script Detection) prepozna je li stranica
        # zarotirana (90/180/270) i ispravlja je prije OCR-a. Slike snimljene
        # mobitelom su često zakrenute pa ovo bitno diže točnost.
        try:
            osd = pytesseract.image_to_osd(img)
            angle = int(re.search(r'Rotate: (\d+)', osd).group(1))
            if angle != 0:
                img = img.rotate(-angle, expand=True)
        except Exception:
            # OSD zna pasti na slikama s malo teksta -> samo nastavimo bez rotacije.
            pass

        img = self._preprocess(img)
        # --psm 3: automatska segmentacija stranice (zadano, za pun dokument)
        # --oem 1: LSTM engine (noviji, točniji od starog Tesseract enginea)
        # lang="eng+hrv": kombiniramo engleski i hrvatski rječnik (dijakritika).
        config = "--psm 3 --oem 1"
        return pytesseract.image_to_string(img, config=config, lang="eng+hrv").strip()

    def _to_markdown(self, raw: str) -> str:
        """
        Lagana ("light-touch") pretvorba sirovog teksta u Markdown.

        Namjerno konzervativno: ne pokušavamo pogađati naslove ni rekonstruirati
        složen layout (to brzo proizvede krive rezultate). Samo normaliziramo
        prazne retke i prepoznajemo liste, jer su to siguran i predvidljiv dobitak.
        """
        if not raw:
            return ""

        lines = raw.splitlines()
        out: list[str] = []
        prev_blank = True  # počinjemo kao da je prethodni red prazan -> bez vodećih praznina

        for line in lines:
            stripped = line.strip()

            # Prazne retke sažimamo: najviše jedan uzastopni razmak između odlomaka.
            if not stripped:
                if not prev_blank:
                    out.append("")
                prev_blank = True
                continue

            # Natuknice s raznim znakovima (-, *, •) svodimo na standardni "- ".
            bullet_match = re.match(r'^[\-\*\•]\s+(.+)', stripped)
            if bullet_match:
                out.append(f"- {bullet_match.group(1)}")
                prev_blank = False
                continue

            # Numerirane liste ("1.", "2)") zadržavamo kakve jesu (već su valjan Markdown).
            num_match = re.match(r'^(\d+[\.\)]\s+)(.+)', stripped)
            if num_match:
                out.append(f"{num_match.group(1)}{num_match.group(2)}")
                prev_blank = False
                continue

            out.append(stripped)
            prev_blank = False

        return "\n".join(out).strip()
