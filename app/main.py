from fastapi import FastAPI

app = FastAPI(
    title="Glasses API",
    version="0.1.0",
)


@app.get("/")
def root():
    return {"message": "Glasses API is running"}


@app.get("/health")
def health():
    return {"status": "ok"}
