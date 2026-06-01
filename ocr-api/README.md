# OCR REST API

REST API koji zaprima sliku ili PDF dokument, provodi OCR i vraća prepoznati
tekst u Markdown formatu. Implementiran je u FastAPI-ju, s Tesseractom kao
OCR enginom.

Podržani formati: `.png`, `.jpg`, `.jpeg`, `.pdf`.

---

## Pokretanje

### Docker (preporučeno)

Potreban je samo Docker — Python, Tesseract i ostale ovisnosti grade se
automatski iz `Dockerfile`-a.

```bash
docker compose up --build
```

API je dostupan na `http://localhost:8000`.

### Bez Dockera (lokalno)

Lokalno je potrebno ručno instalirati Python (3.11+) i Tesseract. Tesseract je
sistemski program, a ne Python paket, pa se instalira zasebno.

1. Tesseract (s hrvatskim i engleskim jezikom):

   ```bash
   # macOS
   brew install tesseract tesseract-lang

   # Ubuntu / Debian
   sudo apt-get install tesseract-ocr tesseract-ocr-hrv tesseract-ocr-eng
   ```

   **Windows:** instalacija ide preko [UB-Mannheim installera](https://github.com/UB-Mannheim/tesseract/wiki).
   Pod *Additional language data* potrebno je odabrati Croatian i English, a
   putanju instalacije (npr. `C:\Program Files\Tesseract-OCR`) dodati u *Path*.
   Provjera: `tesseract --version`.

2. Python ovisnosti (naredbe se pokreću iz korijena projekta, gdje se nalazi
   `requirements.txt`):

   ```bash
   # macOS / Linux
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

   Na **Windowsu** se virtualno okruženje aktivira drukčije:

   ```powershell
   python -m venv .venv

   # PowerShell (ako je aktivacija blokirana zbog execution policyja):
   Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process
   .venv\Scripts\Activate.ps1
   # CMD: .venv\Scripts\activate.bat

   pip install -r requirements.txt
   ```

3. Pokretanje servera:

   ```bash
   uvicorn app.main:app --reload
   ```

---

## Korištenje

Aplikacija nudi tri načina korištenja:

- **Web sučelje** — `http://localhost:8000` (upload obrazac za demonstraciju)
- **Interaktivna dokumentacija** — `http://localhost:8000/docs` (Swagger UI)
- **Izravni poziv API-ja** — opisan u nastavku

### Endpoint

```
POST /api/v1/ocr
Content-Type: multipart/form-data
```

### Primjer poziva

```bash
curl -X POST http://localhost:8000/api/v1/ocr \
     -F "file=@test_folders/plovidbeni_red.pdf" | python -m json.tool
```

### Primjer odgovora

```json
{
  "filename": "plovidbeni_red.pdf",
  "markdown": "## Page 1\n\n| Polazak | Dolazak |\n| --- | --- |\n| 08:00 | 09:30 |"
}
```

---

## Tehničke odluke

### OCR engine

Prvotni izbor bio je **PaddleOCR** — nudi bolje rezultate na složenom rasporedu,
ima ugrađenu detekciju orijentacije i veću točnost na fotografijama. Međutim,
povlači velike modele i znatnu količinu memorije te se na 8 GB RAM-a nije
stabilno pokrenuo.

Stoga je odabran **Tesseract**: zreo, lagan, bez GPU zahtjeva, s dobrom podrškom
za hrvatski jezik (`eng+hrv`). Budući da je slabiji na ulazima niže kvalitete,
taj nedostatak nadoknađuju preprocessing, korekcija rotacije i izravno čitanje
digitalnih PDF-ova.

### PDF — odluka po stranici

Težište rješenja je na digitalnim PDF dokumentima. Za **svaku stranicu zasebno**
provjerava se postoji li tekstualni sloj:

- **digitalna stranica** — čita se izravno PyMuPDF-om (brže, preciznije, bez
  gubitka formatiranja)
- **skenirana stranica** — rasterizira se u sliku (300 DPI) i šalje na Tesseract

Odluka se donosi po stranici, a ne za cijeli dokument. U protivnom bi se kod
mješovitog PDF-a skenirane stranice izgubile, jer bi digitalne stranice
"napunile" broj znakova iznad praga. Rasterizaciju obavlja sam PyMuPDF, pa
Poppler nije potreban.

### Tablice

Standardna ekstrakcija pretvara tablicu u nečitljiv niz teksta. Kod digitalnih
PDF-ova tablice se izdvajaju funkcijom `find_tables()` i slažu s ostatkom teksta
po y-koordinati, čime ostaju na svom mjestu u dokumentu. Kod slika isti zadatak
obavlja `img2table`.

### Preprocessing i korekcija rotacije

Prije OCR-a slika prolazi obradu OpenCV-om: pretvorba u sive tonove, uklanjanje
šuma i Otsu binarizacija, čime rubovi slova postaju oštriji. Rotaciju
prepoznaje Tesseractov OSD i ispravlja zakrenutu stranicu (90/180/270°) prije
OCR-a.

### Markdown konverzija

Konverzija je namjerno minimalna — naslovi i složen raspored se ne pokušavaju
pogađati, jer to brzo proizvodi netočne rezultate. Sažimaju se prazni retci,
prepoznaju liste, a svaka stranica dobiva `## Page N` zaglavlje.

---

## Organizacija projekta

Projekt je podijeljen u tri sloja: HTTP (router), poslovna logika (servis) i
modeli. Servis je odvojen od routera kako bi se mogao testirati neovisno i kako
bi se OCR engine mogao zamijeniti bez izmjena API sloja.

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
  main.py                  # FastAPI aplikacija, CORS, statički sadržaj
  routers/ocr.py           # endpoint, validacija ulaza, mapiranje grešaka
  services/ocr_service.py  # sva OCR logika (PDF, slike, tablice, Markdown)
  models/response.py       # Pydantic model odgovora
  static/index.html        # web sučelje
tests/test_api.py          # automatizirani testovi
test_folders/              # primjeri dokumenata za ručno testiranje
```

Tok obrade jednog zahtjeva:

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

### Automatizirani testovi (`pytest`)

```bash
pytest
```

Testovi pokrivaju validaciju ulaza, Markdown konverziju i spajanje stranica.
Glavni test gradi mješoviti PDF (jedna digitalna i jedna skenirana stranica) i
provjerava da svaka stranica ide odgovarajućim putem. Tesseract je u testovima
zamijenjen mockom, pa su brzi i deterministički.

### Ručno testiranje (`test_folders/`)

Svaki primjer pokriva po jedan slučaj:

| Datoteka | Slučaj |
| --- | --- |
| `tekstpjesme.pdf` | digitalni PDF, bez OCR-a |
| `digitalni.pdf` | digitalni PDF s formatiranjem |
| `plovidbeni_red.pdf` | tablica → Markdown |
| `mjesoviti.pdf` | digitalne i skenirane stranice u istom PDF-u |
| `skenirani.pdf` | potpuni sken, OCR po svim stranicama |
| `rotacija.pdf` | zakrenuta stranica (OSD) |
| `slika.jpg` | fotografirani račun |
| `slika2.jpg` | netipične boje (svijetli tekst na tamnoj podlozi) |

```bash
curl -X POST http://localhost:8000/api/v1/ocr \
     -F "file=@test_folders/mjesoviti.pdf" | python -m json.tool
```

---

## Moguća poboljšanja

- **Mutne i ukošene slike** — deskew i procjena oštrine prije OCR-a
- **Slike s mnogo netekstualnih elemenata** — segmentacija teksta od grafike
- **Rukopis** — zaseban model, jer ga Tesseract slabo prepoznaje
- **Izdvajanje strukture** — pouzdanije prepoznavanje naslova i odlomaka
- **Performanse i skalabilnost** — asinkrona obrada velikih PDF-ova i caching
  rezultata po hashu datoteke
