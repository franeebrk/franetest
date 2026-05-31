"""Pydantic modeli za API odgovore."""
from pydantic import BaseModel


class OCRResponse(BaseModel):
    """
    Oblik odgovora OCR endpointa.

    filename - ime ulazne datoteke (radi lakšeg snalaženja na strani klijenta)
    markdown - prepoznati tekst u Markdown formatu

    json_schema_extra dodaje primjer koji se prikazuje u /docs (Swagger UI).
    """
    filename: str
    markdown: str

    model_config = {"json_schema_extra": {
        "example": {
            "filename": "invoice.pdf",
            "markdown": "## Invoice\n\nDate: 2024-01-15\n\nTotal: $1,200.00",
        }
    }}
