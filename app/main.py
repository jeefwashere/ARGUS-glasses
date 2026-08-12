# main.py

from fastapi import FastAPI
from dotenv import load_dotenv

from app.routes.ask import router as ask_router

load_dotenv()

app = FastAPI(
    title="Glasses API",
    version="0.1.0",
)

app.include_router(ask_router)


@app.get("/")
def root():
    return {"message": "Glasses API is running"}


@app.get("/health")
def health():
    return {"status": "ok"}
