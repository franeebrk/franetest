"""
Generira hibridni PDF za testiranje: stranica 1 je digitalna (pravi tekst),
stranica 2 je "skenirana" (slika teksta bez tekstualnog sloja).

Pokretanje:  python tests/make_hybrid_pdf.py
Izlaz:       tests/data/hybrid.pdf
"""
import io
import os

import fitz  # PyMuPDF
from PIL import Image, ImageDraw, ImageFont


def _make_scanned_image(text: str, size=(1240, 1754)) -> bytes:
    """Renderira tekst u PNG (300 DPI A4) -> ovo glumi skeniranu stranicu."""
    img = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 40)
    except OSError:
        font = ImageFont.load_default()
    y = 120
    for line in text.splitlines():
        draw.text((120, y), line, fill="black", font=font)
        y += 60
    buf = io.BytesIO()
    img.save(buf, format="PNG", dpi=(300, 300))
    return buf.getvalue()


def main():
    out_dir = os.path.join(os.path.dirname(__file__), "data")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "hybrid.pdf")

    doc = fitz.open()

    # Stranica 1 — DIGITALNA: pravi tekstualni sloj koji PyMuPDF cita direktno.
    p1 = doc.new_page()
    p1.insert_text(
        (72, 100),
        "Stranica 1 - DIGITALNA\n\n"
        "Ovo je racunalno generiran tekst.\n"
        "PyMuPDF ga cita direktno, bez OCR-a.\n\n"
        "Datum: 2024-01-15\nUkupno: 1.200,00 EUR",
        fontsize=14,
    )

    # Stranica 2 — SKENIRANA: samo slika preko cijele stranice, nula teksta.
    p2 = doc.new_page()
    png = _make_scanned_image(
        "Stranica 2 - SKENIRANA\n\n"
        "Ovaj tekst postoji samo kao slika.\n"
        "PyMuPDF ovdje vraca prazno -\n"
        "treba ga Tesseract OCR procitati.\n\n"
        "Broj racuna: 998877"
    )
    p2.insert_image(p2.rect, stream=png)

    doc.save(out_path)
    doc.close()

    # Brza provjera: koliko teksta PyMuPDF vidi po stranici.
    check = fitz.open(out_path)
    for i, page in enumerate(check, 1):
        n = len(page.get_text().strip())
        kind = "digitalna" if n > 50 else "skenirana (PyMuPDF ne vidi tekst)"
        print(f"Stranica {i}: {n} znakova -> {kind}")
    check.close()
    print(f"\nSpremljeno: {out_path}")


if __name__ == "__main__":
    main()
