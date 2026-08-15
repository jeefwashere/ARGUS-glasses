import base64

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.services.backboard_service import call_backboard
from app.services.deepgram_service import transcribe_recording
from app.services.elevenlabs_service import elevenlabs_tts
from app.utils.audio import convert_to_16khz_wav, pcm16_to_wav
from app.utils.wake_word import WAKE_PHRASE, extract_wake_question

router = APIRouter()

MAX_RECORDING_BYTES = 15 * 1024 * 1024


@router.post("/voice")
async def voice(
    audio: UploadFile = File(...),
    thread_id: str | None = Form(default=None),
):
    recording = await audio.read(MAX_RECORDING_BYTES + 1)
    if not recording:
        raise HTTPException(status_code=400, detail="The audio recording is empty")
    if len(recording) > MAX_RECORDING_BYTES:
        raise HTTPException(status_code=413, detail="The audio recording is too large")

    try:
        normalized_audio = convert_to_16khz_wav(recording)
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail="The uploaded file is not a supported audio recording",
        ) from exc

    try:
        transcript = await transcribe_recording(normalized_audio)
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Speech recognition failed") from exc

    if not transcript:
        return {
            "activated": False,
            "wake_phrase": WAKE_PHRASE,
            "transcript": "",
            "reason": "no_speech",
        }

    activated, question = extract_wake_question(transcript)
    if not activated:
        return {
            "activated": False,
            "wake_phrase": WAKE_PHRASE,
            "transcript": transcript,
            "reason": "wake_phrase_missing",
        }

    if not question:
        return {
            "activated": True,
            "wake_phrase": WAKE_PHRASE,
            "transcript": transcript,
            "question": "",
            "reply_generated": False,
            "reason": "question_missing",
        }

    try:
        result = await call_backboard(
            question_text=question,
            thread_id=thread_id or None,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Failed to process the question") from exc

    response = {
        "activated": True,
        "wake_phrase": WAKE_PHRASE,
        "transcript": transcript,
        "question": question,
        "reply_generated": True,
        "answer": result["content"],
        "thread_id": result["thread_id"],
        "audio_format": None,
        "audio_data_url": None,
    }

    try:
        pcm_audio = await elevenlabs_tts(result["content"])
        wav_audio = pcm16_to_wav(pcm_audio)
        response["audio_format"] = "wav_16000_mono"
        response["audio_data_url"] = (
            "data:audio/wav;base64," + base64.b64encode(wav_audio).decode("ascii")
        )
    except Exception:
        response["audio_error"] = "Speech generation failed"

    return response
