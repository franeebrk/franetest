from pydantic import BaseModel


class OCRResponse(BaseModel):
    filename: str
    markdown: str

    model_config = {"json_schema_extra": {
        "example": {
            "filename": "invoice.pdf",
            "markdown": "## Invoice\n\nDate: 2024-01-15\n\nTotal: $1,200.00",
        }
    }}
