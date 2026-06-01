from pathlib import Path

from fastapi import APIRouter, File, UploadFile, HTTPException

from app.services.ocr_service import OCRService
from app.models.response import OCRResponse

router = APIRouter(tags=["OCR"])

ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".pdf"}


@router.post("/ocr", response_model=OCRResponse, summary="Extract text from image or PDF")
async def extract_text(file: UploadFile = File(...)):
    suffix = Path(file.filename).suffix.lower() if file.filename else ""
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix}'. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    try:
        result = OCRService().process(content, suffix, filename=file.filename or "upload")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"OCR processing failed: {exc}") from exc

    return OCRResponse(filename=file.filename or "upload", markdown=result)
