from fastapi import APIRouter, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse

from app.services.ocr_service import OCRService
from app.models.response import OCRResponse

router = APIRouter(tags=["OCR"])

ALLOWED_CONTENT_TYPES = {
    "image/png",
    "image/jpeg",
    "application/pdf",
}

ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".pdf"}


@router.post("/ocr", response_model=OCRResponse, summary="Extract text from image or PDF")
async def extract_text(file: UploadFile = File(...)):
    """
    Upload a .png, .jpg, .jpeg, or .pdf file and receive extracted text in Markdown format.
    """
    # Validate file type
    suffix = ""
    if file.filename:
        from pathlib import Path
        suffix = Path(file.filename).suffix.lower()

    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix}'. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    service = OCRService()
    try:
        result = service.process(content, suffix, filename=file.filename or "upload")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"OCR processing failed: {exc}") from exc

    return OCRResponse(filename=file.filename or "upload", markdown=result)
