from fastapi import FastAPI, File, UploadFile

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

    """Serves as the endpoint from which user question and image (if applicable) gets processed converted into response

    Returns:
        object: audio file and response
    """


@app.get("/ask")
async def ask(
    question_audio: UploadFile = File(...),
    context_image: UploadFile | None = File(None),
):
    # Convert audio file into bytes
    audio_bytes = await question_audio.read()

    image_bytes = await context_image.read() if context_image else None

    return {"message": "Test data"}
