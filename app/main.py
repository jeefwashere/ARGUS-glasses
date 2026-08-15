# main.py

from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

load_dotenv()

from app.routes.ask import router as ask_router
from app.routes.voice import router as voice_router

app = FastAPI(
    title="Glasses API",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ask_router)
app.include_router(voice_router)

STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def root():
    return {"message": "Glasses API is running"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/demo", include_in_schema=False)
def demo():
    return FileResponse(STATIC_DIR / "index.html")
