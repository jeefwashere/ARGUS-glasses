from fastapi import FastAPI

from app.routes.ask import router as ask_router

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
