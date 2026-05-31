"""
HTTP sloj (router) za OCR endpoint.

Ovdje je samo ono što se tiče HTTP-a: prihvat datoteke, validacija ulaza i
mapiranje grešaka na statusne kodove. Sva stvarna OCR logika je u OCRService-u
kako bi router ostao tanak i lako testabilan.
"""
from pathlib import Path

from fastapi import APIRouter, File, UploadFile, HTTPException

from app.services.ocr_service import OCRService
from app.models.response import OCRResponse

router = APIRouter(tags=["OCR"])

# Dopuštene ekstenzije; provjeravamo ekstenziju (a ne samo content-type) jer je
# pouzdanija — klijenti znaju slati netočan ili prazan MIME tip.
ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".pdf"}


@router.post("/ocr", response_model=OCRResponse, summary="Extract text from image or PDF")
async def extract_text(file: UploadFile = File(...)):
    """
    Prima .png, .jpg, .jpeg ili .pdf datoteku i vraća prepoznati tekst u Markdownu.
    """
    # Ekstenziju izvlačimo iz imena datoteke i normaliziramo na mala slova.
    suffix = ""
    if file.filename:
        suffix = Path(file.filename).suffix.lower()

    # 400 -> klijentova greška: nepodržan format.
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix}'. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    content = await file.read()
    # Prazna datoteka nema smisla slati u OCR -> rana, jasna greška.
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    service = OCRService()
    try:
        result = service.process(content, suffix, filename=file.filename or "upload")
    except Exception as exc:
        # Neočekivani problem u obradi -> 500, uz poruku za lakši debug.
        raise HTTPException(status_code=500, detail=f"OCR processing failed: {exc}") from exc

    return OCRResponse(filename=file.filename or "upload", markdown=result)
