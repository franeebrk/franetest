# OCR REST API

Zadatak je kreirati REST API koji zaprima sliku ili PDF dokument, provodi OCR i vraća prepoznati
tekst u Markdown formatu. Izgrađen je s FastAPI-jem i self-hosted OCR enginom
(Tesseract).

Podržani formati: `.png`, `.jpg`, `.jpeg`, `.pdf`.

---

## Pokretanje

### Docker (preporučeno, najviše istestirano)

Jedini preduvjet je instaliran Docker. Sve ostalo (Python, Tesseract, jezični
paketi i biblioteke) gradi se automatski iz `Dockerfile`-a.

```bash
docker compose up --build
```

API je nakon toga dostupan na `http://localhost:8000`.

### Bez Dockera (lokalno)

Ako Docker nije dostupan, aplikacija se može pokrenuti i lokalno. U tom slučaju
Tesseract treba instalirati ručno.

1. Instalacija Tesseracta (s hrvatskim i engleskim jezikom):

   ```bash
   # macOS
   brew install tesseract tesseract-lang

   # Ubuntu / Debian
   sudo apt-get install tesseract-ocr tesseract-ocr-hrv tesseract-ocr-eng
   ```

2. Instalacija Python ovisnosti:

   ```bash
   python -m venv .venv
   source .venv/bin/activate        # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. Pokretanje servera:

   ```bash
   uvicorn app.main:app --reload
   ```

---

## Korištenje

Ova aplikacija nudi tri načina korištenja:

- **Web sučelje** — `http://localhost:8000` (jednostavan upload obrazac za demo)
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

### Izbor OCR enginea

Prvotno sam želio koristiti **PaddleOCR**. PaddleOCR daje bolje rezultate na
složenim rasporedima (layout), ima ugrađenu klasifikaciju orijentacije teksta,
bolju detekciju regija i općenito veću točnost na fotografijama iz stvarnog
svijeta. Problem je u resursima: PaddleOCR povlači velike modele i znatno više
memorije. Na računalu s 8 GB RAM-a engine se nije uspio stabilno pokrenuti.

Zbog toga sam odabrao **Tesseract**. Tesseract je zreo, lagan i jednostavan za
postavljanje, ne traži GPU i ima dobru podršku za latinično pismo i hrvatski
jezik (`eng+hrv`). Budući da je Tesseract slabiji na "prljavim" ulazima od
PaddleOCR-a, slabosti sam pokrio ručno kroz preprocessing, korekciju rotacije i
zasebno čitanje digitalnih PDF-ova (opisano niže).

### Strategija za PDF — odluka po stranici

Posebnu pažnju posvetio sam obradi računalno generiranih (digitalnih) PDF-ova.

Za svaku stranicu zasebno provjeravam ima li već tekstualni sloj:

- **Digitalna stranica** — tekst čitam izravno PyMuPDF-om, bez OCR-a. Brže je,
  preciznije i ne gubi formatiranje.
- **Skenirana stranica** — stranicu rasteriziram u sliku (PyMuPDF, 300 DPI) i
  šaljem na Tesseract.

Odluka se donosi **po stranici, a ne za cijeli dokument**. To je važno za
mješovite PDF-ove (npr. digitalni ugovor sa skeniranim prilogom): da odluku
donosim globalno, skenirane stranice bi se izgubile jer digitalne stranice same
"napune" ukupan broj znakova iznad praga.

Rasterizaciju radi sam PyMuPDF, pa nisu potrebne dodatne sistemske ovisnosti
(npr. Poppler).

### Detekcija tablica

Tablice se lako "spljošte" u nečitljiv niz teksta. Za digitalne PDF-ove tablice
vadim PyMuPDF-ovom funkcijom `find_tables()` i slažem ih s ostatkom teksta po
y-koordinati, tako da završe na svom mjestu u dokumentu. Za slike koristim
`img2table`, koji prepoznaje tablice s vidljivim linijama i vraća ih kao
strukturirane Markdown tablice.

### Preprocessing i korekcija rotacije

Prije OCR-a slike pripremam OpenCV-om: pretvorba u sive tonove, uklanjanje šuma
i binarizacija (Otsu). Time rubovi slova postaju oštriji, što diže točnost na
fotografijama i slabijim skenovima. Rotaciju rješavam Tesseractovim OSD-om
(Orientation and Script Detection): ako je stranica zakrenuta (90/180/270°),
ispravljam je prije OCR-a.

### Markdown konverzija

Konverzija je namjerno konzervativna. Ne pokušavam pogađati naslove ni
rekonstruirati složen raspored, jer to brzo proizvede krive rezultate.
Normaliziram prazne retke i prepoznajem liste (`-`, `*`, `•`, numerirane), a
višestranični dokumenti dobivaju `## Page N` zaglavlja.

---

## Organizacija projekta

Projekt je podijeljen u tri sloja: HTTP (router), poslovna logika (servis) i
modeli. Servis je odvojen od routera kako bi se mogao testirati neovisno i kako
bi se OCR engine mogao zamijeniti bez diranja API sloja.

```
app/
  main.py                  # FastAPI aplikacija, CORS, statički sadržaj
  routers/
    ocr.py                 # HTTP endpoint, validacija ulaza, mapiranje grešaka
  services/
    ocr_service.py         # Sva OCR logika (PDF, slike, tablice, Markdown)
  models/
    response.py            # Pydantic model odgovora
  static/
    index.html             # Web sučelje za upload
tests/
  test_api.py              # Automatizirani testovi
test_folders/              # Primjeri dokumenata za ručno testiranje
```

Tok obrade jednog zahtjeva:

```
upload  ->  router (validacija formata i praznog ulaza)
        ->  OCRService.process()
              ├─ PDF  -> po stranici: digitalni (PyMuPDF) ili skenirani (OCR)
              └─ slika -> tablice (img2table) ili Tesseract OCR
        ->  Markdown odgovor (filename + markdown)
```

---

## Testiranje

Testiranje je podijeljeno na dvije razine.

### Automatizirani testovi

Pokreću se s:

```bash
pytest
```

Testovi pokrivaju validaciju ulaza (odbijanje nepodržanog formata i prazne datoteke), konverziju teksta u Markdown te logiku spajanja stranica. Poseban
test provjerava mješoviti PDF: gradi dokument s jednom digitalnom i jednom
skeniranom stranicom te potvrđuje da digitalna ide kroz PyMuPDF, a skenirana
kroz OCR. Tesseract je u tom testu zamijenjen mockom, pa testovi rade brzo i ne
ovise o instaliranom enginu.

### Ručno testiranje (`test_folders/`)

U mapi `test_folders/` nalaze se primjeri dokumenata, svaki odabran da pokrije
određeni slučaj:

| Datoteka | Što provjerava |
| --- | --- |
| `tekstpjesme.pdf` | Digitalni PDF — čitanje tekstualnog sloja bez OCR-a |
| `digitalni.pdf` | Digitalni PDF s formatiranim sadržajem |
| `plovidbeni_red.pdf` | Tablica (red plovidbe) — detekcija i Markdown tablice |
| `mjesoviti.pdf` | Mješoviti PDF — digitalne i skenirane stranice u istom dokumentu |
| `skenirani.pdf` | Potpuno skenirani PDF — OCR po svim stranicama |
| `rotacija.pdf` | Zakrenuta stranica — korekcija rotacije (OSD) |
| `slika.jpg` | Fotografirani račun — OCR na slici iz stvarnog svijeta |
| `slika2.jpg` | Slika s netipičnim bojama (svijetli tekst na tamnoj podlozi) |

Primjer:

```bash
curl -X POST http://localhost:8000/api/v1/ocr \
     -F "file=@test_folders/mjesoviti.pdf" | python -m json.tool
```

---

## Moguća poboljšanja

Trenutno rješenje pokriva digitalne i skenirane PDF-ove, mješovite dokumente,
tablice, korekciju rotacije i osnovni preprocessing slike. U sljedećoj iteraciji
posebno bih obradio teže ulaze:

- **Mutne i ukošene slike** — deskew i procjena oštrine prije OCR-a
- **Slike s puno netekstualnih elemenata** — segmentacija teksta od grafike
- **Rukopis** — zaseban model jer ga Tesseract slabo prepoznaje
- **Bolje izdvajanje strukture** — pouzdanije prepoznavanje naslova i odlomaka
- **Performanse i skalabilnost** — asinkrona obrada velikih PDF-ova (queue) i
  caching rezultata po hashu datoteke
