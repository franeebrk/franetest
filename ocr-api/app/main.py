"""
Ulazna točka aplikacije: kreira FastAPI instancu, registrira middleware,
router i statičke datoteke (jednostavno web sučelje za demo).
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

from app.routers import ocr

app = FastAPI(
    title="OCR REST API",
    description="REST API for OCR processing of images and PDF documents",
    version="1.0.0",
)

# CORS je otvoren ("*") jer je ovo demo/zadatak — frontend i API mogu biti na
# različitim portovima. U produkciji bi se ovdje ograničilo na konkretne domene.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Verzioniran prefiks (/api/v1) ostavlja prostor za buduće promjene API-ja
# bez rušenja postojećih klijenata.
app.include_router(ocr.router, prefix="/api/v1")

# Statičke datoteke (CSS/JS/HTML); putanju gradimo relativno na ovaj file da
# radi neovisno o tome odakle je proces pokrenut.
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")


@app.get("/health")
def health_check():
    """Jednostavan health-check za provjeru da aplikacija radi (npr. u Dockeru)."""
    return {"status": "ok"}


@app.get("/")
def index():
    """Posljužuje demo web sučelje za upload datoteka."""
    return FileResponse(os.path.join(os.path.dirname(__file__), "static", "index.html"))
