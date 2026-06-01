# OCR REST API

REST API koji prima sliku ili PDF, provede OCR i vrati tekst u Markdownu.
Napravljen u FastAPI-ju s Tesseractom kao OCR enginom.

Podržani formati: `.png`, `.jpg`, `.jpeg`, `.pdf`.

---

## Pokretanje

### Docker (preporučeno)

Treba ti samo Docker — Python, Tesseract i sve ostalo gradi se iz `Dockerfile`-a.

```bash
docker compose up --build
```

API radi na `http://localhost:8000`.

### Bez Dockera (lokalno)

Treba ručno instalirati Python (3.11+) i Tesseract. Tesseract je sistemski
program, ne Python paket, pa ide zasebno.

1. Tesseract (s hrvatskim i engleskim):

   ```bash
   # macOS
   brew install tesseract tesseract-lang

   # Ubuntu / Debian
   sudo apt-get install tesseract-ocr tesseract-ocr-hrv tesseract-ocr-eng
   ```

   **Windows:** instaliraj preko [UB-Mannheim installera](https://github.com/UB-Mannheim/tesseract/wiki).
   Pod *Additional language data* odaberi Croatian i English, a putanju (npr.
   `C:\Program Files\Tesseract-OCR`) dodaj u *Path*. Provjeri s `tesseract --version`.

2. Python ovisnosti (iz korijena projekta, gdje je `requirements.txt`):

   ```bash
   # macOS / Linux
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

   Na **Windowsu** se okruženje aktivira drukčije:

   ```powershell
   python -m venv .venv

   # PowerShell (ako aktivacija bude blokirana):
   Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process
   .venv\Scripts\Activate.ps1
   # CMD: .venv\Scripts\activate.bat

   pip install -r requirements.txt
   ```

3. Server:

   ```bash
   uvicorn app.main:app --reload
   ```

---

## Korištenje

Tri načina:

- **Web sučelje** — `http://localhost:8000` (upload obrazac za demo)
- **Swagger** — `http://localhost:8000/docs`
- **Direktan poziv** — niže

### Endpoint

```
POST /api/v1/ocr
Content-Type: multipart/form-data
```

### Primjer

```bash
curl -X POST http://localhost:8000/api/v1/ocr \
     -F "file=@test_folders/plovidbeni_red.pdf" | python -m json.tool
```

```json
{
  "filename": "plovidbeni_red.pdf",
  "markdown": "## Page 1\n\n| Polazak | Dolazak |\n| --- | --- |\n| 08:00 | 09:30 |"
}
```

---

## Tehničke odluke

### OCR engine

Prvotni izbor bio je **PaddleOCR** — bolji na složenom layoutu, s ugrađenom
detekcijom orijentacije i većom točnošću na fotkama. No povlači velike modele i
puno memorije te se na 8 GB RAM-a nije stabilno pokrenuo.

Odabran je zato **Tesseract**: zreo, lagan, bez GPU-a, s dobrom podrškom za
hrvatski (`eng+hrv`). Slabiji je na "prljavim" ulazima, pa se to nadoknađuje
preprocessingom, korekcijom rotacije i izravnim čitanjem digitalnih PDF-ova.

### PDF — odluka po stranici

Težište je na digitalnim PDF-ovima. Za **svaku stranicu zasebno** provjerava se
ima li tekstualni sloj:

- **digitalna** → čita se izravno PyMuPDF-om (brže, preciznije, ne gubi format)
- **skenirana** → rasterizira se u sliku (300 DPI) i šalje na Tesseract

Odluka ide po stranici, ne po cijelom dokumentu — inače bi kod mješovitog PDF-a
skenirane stranice nestale jer digitalne "napune" broj znakova iznad praga.
Rasterizira sam PyMuPDF, pa ne treba Poppler.

### Tablice

Obična ekstrakcija pretvori tablicu u nečitljiv niz. Kod digitalnih PDF-ova
tablice se vade s `find_tables()` i slažu s tekstom po y-koordinati da ostanu na
mjestu. Kod slika isto radi `img2table`.

### Preprocessing i rotacija

Prije OCR-a slika prolazi OpenCV obradu: grayscale, uklanjanje šuma i Otsu
binarizacija — rubovi slova postanu oštriji. Rotaciju hvata Tesseractov OSD i
ispravlja zakrenutu stranicu (90/180/270°) prije OCR-a.

### Markdown

Konverzija je namjerno minimalna — naslovi i složen raspored se ne pogađaju jer
to brzo daje krive rezultate. Sažimaju se prazni retci, prepoznaju liste, a
svaka stranica dobiva `## Page N`.

---

## Organizacija

Tri sloja: HTTP (router), logika (servis), modeli. Servis je odvojen od routera
da se može testirati neovisno i da se engine može zamijeniti bez diranja API-ja.

```
┌─────────────────────────────────────────────┐
│  HTTP sloj        routers/ocr.py             │  validacija ulaza, status kodovi
├─────────────────────────────────────────────┤
│  Logika           services/ocr_service.py    │  PDF, slike, tablice, Markdown
├─────────────────────────────────────────────┤
│  Modeli           models/response.py         │  oblik odgovora (Pydantic)
└─────────────────────────────────────────────┘
```

Struktura datoteka:

```
app/
  main.py                  # FastAPI app, CORS, statika
  routers/ocr.py           # endpoint, validacija ulaza, greške
  services/ocr_service.py  # sva OCR logika (PDF, slike, tablice, Markdown)
  models/response.py       # Pydantic model odgovora
  static/index.html        # web sučelje
tests/test_api.py          # automatizirani testovi
test_folders/              # primjeri za ručno testiranje
```

Tok zahtjeva:

```
upload
  │
  ▼
router  ──►  validacija (format, prazan ulaz)
  │
  ▼
OCRService.process()
  │
  ├─ PDF ────►  po stranici:  digitalni (PyMuPDF)  │  skenirani (300 DPI → OCR)
  │
  └─ slika ──►  tablice (img2table)  │  Tesseract OCR
  │
  ▼
Markdown  { filename, markdown }
```

---

## Testiranje

### Automatizirani (`pytest`)

```bash
pytest
```

Pokrivaju validaciju ulaza, Markdown konverziju i spajanje stranica. Glavni test
gradi mješoviti PDF (jedna digitalna + jedna skenirana stranica) i provjerava da
svaka ide pravim putem. Tesseract je mockan, pa su testovi brzi i deterministički.

### Ručno (`test_folders/`)

Svaki primjer pokriva jedan slučaj:

| Datoteka | Slučaj |
| --- | --- |
| `tekstpjesme.pdf` | digitalni PDF, bez OCR-a |
| `digitalni.pdf` | digitalni PDF s formatiranjem |
| `plovidbeni_red.pdf` | tablica → Markdown |
| `mjesoviti.pdf` | digitalne + skenirane stranice u istom PDF-u |
| `skenirani.pdf` | potpuni sken, OCR svih stranica |
| `rotacija.pdf` | zakrenuta stranica (OSD) |
| `slika.jpg` | fotografirani račun |
| `slika2.jpg` | netipične boje (svijetli tekst na tamnom) |

```bash
curl -X POST http://localhost:8000/api/v1/ocr \
     -F "file=@test_folders/mjesoviti.pdf" | python -m json.tool
```

---

## Moguća poboljšanja

- **Mutne i ukošene slike** — deskew i procjena oštrine
- **Slike s puno grafike** — segmentacija teksta od ostatka
- **Rukopis** — zaseban model
- **Struktura** — pouzdanije prepoznavanje naslova i odlomaka
- **Skalabilnost** — asinkrona obrada velikih PDF-ova i caching po hashu
