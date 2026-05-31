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

**macOS**
```bash
brew install tesseract poppler
```

**Ubuntu / Debian**
```bash
sudo apt-get install tesseract-ocr tesseract-ocr-eng tesseract-ocr-hrv poppler-utils
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
  "markdown": "## Page 1\n\nDatum: 2024-01-15\n\nUkupno: 1.200,00 €"
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
- dobre podrške za latinično pismo i hrvatski jezik (`eng+hrv`)
- jednostavne instalacije bez GPU zahtjeva

Alternativa bi bio **PaddleOCR** koji daje bolje rezultate na složenim layoutima, ali zahtijeva znatno veće sistemske resurse i duže inicijalizacijsko vrijeme.

### Dvoslojna strategija za PDF

Posebna pažnja posvećena je **obradi računalno generiranih PDF dokumenata**. Za PDF dokumente primjenjuju se dva pristupa:

1. **Tekstualni PDF** → `PyMuPDF` direktno izvlači tekst bez OCR-a. Brže je, preciznije i ne gubi formatiranje.
2. **Skenirani PDF** → `pdf2image` rasterizira stranice na 300 DPI, a Tesseract provodi OCR nad svakom stranicom.

Detekcija tipa vrši se pragom: ako PyMuPDF izvuče manje od 50 znakova po dokumentu, pretpostavljamo skeniran dokument i padamo na Tesseract.

Ovaj pristup je važan jer aplikacija primjenjuje skupi OCR samo kad je zaista potreban — za računalno generirane PDF-ove (fakture, izvještaji, ugovori) rezultat je i brži i precizniji.

### Automatska korekcija rotacije

Za slike, Tesseract OSD (`image_to_osd`) detektira kut rotacije i ispravlja ga prije OCR-a. Poboljšava točnost na fotografijama dokumenata snimljenim pod kutom.

### Markdown konverzija

OCR izlaz se transformira u Markdown:
- Bullet znakovi (`•`, `-`, `*`) → Markdown liste
- Numerirane liste → Markdown numerirane liste
- Višestranični dokumenti → stranice razdvojene `---` separatorom s `## Page N` naslovima

### Organizacija projekta

```
app/
  main.py                   # FastAPI aplikacija i middleware
  routers/ocr.py            # Endpoint, validacija ulaza
  services/ocr_service.py   # Poslovna logika (OCR + Markdown)
  models/response.py        # Pydantic response model
  static/index.html         # Web sučelje
tests/
  test_api.py               # Endpoint + unit testovi
```

Servis je odvojen od routera kako bi ga se moglo testirati neovisno i zamijeniti drugi OCR engine bez promjene API sloja.

---

## Što bi se poboljšalo u sljedećoj iteraciji

- **Async obrada** — za veće PDF-ove isplati se dodati queue (Celery/ARQ) i polling endpoint umjesto blokirajućeg zahtjeva
- **Caching** — hash datoteke → cached rezultat (Redis) za izbjegavanje ponovnog OCR-a
- **Pre-processing slike** — binarizacija, deskew, denoising (OpenCV) za poboljšanje točnosti Tesseracta na slabijim skenovima
- **Detekcija tablica** — `img2table` biblioteka za strukturirani prikaz tablica u Markdownu
- **Autentikacija** — API key middleware za produkcijsku upotrebu
