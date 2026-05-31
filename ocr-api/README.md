# OCR REST API

REST API za OCR obradu slika i PDF dokumenata, izgrađen s **FastAPI** i **Tesseractom**.

## Brzi start (Docker)

```bash
docker compose up --build
```

API je dostupan na `http://localhost:8000`.  
Interaktivna dokumentacija: `http://localhost:8000/docs`

---

## Lokalno pokretanje (bez Dockera)

### 1. Instaliraj sistemske ovisnosti

**Ubuntu / Debian**
```bash
sudo apt-get install tesseract-ocr tesseract-ocr-eng tesseract-ocr-hrv poppler-utils
```

**macOS**
```bash
brew install tesseract poppler
```

### 2. Instaliraj Python pakete

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Pokreni server

```bash
uvicorn app.main:app --reload
```

---

## Korištenje

### Endpoint

```
POST /api/v1/ocr
Content-Type: multipart/form-data
```

**Podržani formati:** `.png`, `.jpg`, `.jpeg`, `.pdf`

### Primjer — cURL

```bash
curl -X POST http://localhost:8000/api/v1/ocr \
     -F "file=@dokument.pdf" | python -m json.tool
```

### Primjer odgovora

```json
{
  "filename": "racun.pdf",
  "markdown": "## RAČUN\n\nDatum: 2024-01-15\n\nUkupno: 1.200,00 €"
}
```

---

## Testovi

```bash
pytest -v
```

---

## Tehničke odluke

### OCR engine — Tesseract

Odabran je **Tesseract** kao self-hosted OCR engine zbog:
- zrelosti projekta (Google, aktivno održavan)
- dobre podrške za latinično pismo i hrvatski jezik
- jednostavne instalacije bez GPU zahtjeva

Alternativa bi bio **PaddleOCR** koji daje bolje rezultate na složenim layoutima, ali zahtijeva znatno veće sistemske resurse i duže inicijalizacijsko vrijeme.

### Dvoslojna strategija za PDF

Za PDF dokumente primjenjuju se dva pristupa:

1. **Tekstualni PDF** → `pdfplumber` direktno izvlači tekst bez OCR-a. Ovo je brže, preciznije i ne gubi formatiranje.
2. **Skenirani PDF** → `pdf2image` rasterizira stranice na 300 DPI, a Tesseract provodi OCR nad svakom stranicom.

Detekcija tipa vrši se pragom: ako `pdfplumber` izvuče manje od 50 znakova, pretpostavljamo skeniran dokument.

### Markdown konverzija

OCR izlaz se light-touch transformira u Markdown:
- Kratke ALL CAPS ili Title Case linije → `##` naslovi
- Bullet znakovi (`•`, `-`, `*`) → Markdown liste
- Stranice se razdvajaju `---` separatorom

### Organizacija projekta

```
app/
  main.py          # FastAPI aplikacija i middleware
  routers/ocr.py   # Endpoint, validacija ulaza
  services/ocr_service.py  # Poslovna logika (OCR + Markdown)
  models/response.py       # Pydantic response model
tests/
  test_api.py      # Endpoint + unit testovi
```

Servis je namjerno odvojen od routera kako bi ga se moglo testirati neovisno i zamijeniti drugi OCR engine bez promjene API sloja.

---

## Što bi se poboljšalo u sljedećoj iteraciji

- **Async obrada** — za veće PDF-ove isplati se dodati queue (Celery/ARQ) i polling endpoint umjesto blokirajućeg zahtjeva
- **Caching** — hash datoteke → cached rezultat (Redis) za izbjegavanje ponovnog OCR-a
- **Pre-processing slike** — binarizacija, deskew, denoising (OpenCV) za poboljšanje točnosti Tesseracta na slabijim skenovima
- **Strukturirani izlaz** — opcijsko vraćanje bounding boxova po riječima/linijama za downstream NLP zadatke
- **Autentikacija** — API key middleware za produkcijsku upotrebu
