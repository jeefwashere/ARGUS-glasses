import base64
import io
import wave

from fastapi.testclient import TestClient

from app.main import app
from app.routes import voice as voice_route

client = TestClient(app)


def configure_audio_mocks(monkeypatch, transcript):
    monkeypatch.setattr(
        voice_route,
        "convert_to_16khz_wav",
        lambda recording: b"normalized-wav",
    )

    async def fake_transcribe_recording(audio_bytes):
        assert audio_bytes == b"normalized-wav"
        return transcript

    monkeypatch.setattr(
        voice_route,
        "transcribe_recording",
        fake_transcribe_recording,
    )


def test_voice_ignores_recording_without_wake_phrase(monkeypatch):
    configure_audio_mocks(monkeypatch, "What am I looking at?")

    async def unexpected_backboard_call(**kwargs):
        raise AssertionError("Backboard must not run without the wake phrase")

    monkeypatch.setattr(voice_route, "call_backboard", unexpected_backboard_call)

    response = client.post(
        "/voice",
        files={"audio": ("recording.webm", b"browser-audio", "audio/webm")},
    )

    assert response.status_code == 200
    assert response.json() == {
        "activated": False,
        "wake_phrase": "Hi Spider",
        "transcript": "What am I looking at?",
        "reason": "wake_phrase_missing",
    }


def test_voice_requires_a_question_after_wake_phrase(monkeypatch):
    configure_audio_mocks(monkeypatch, "Hi Spider.")

    response = client.post(
        "/voice",
        files={"audio": ("recording.webm", b"browser-audio", "audio/webm")},
    )

    assert response.status_code == 200
    assert response.json()["reply_generated"] is False
    assert response.json()["reason"] == "question_missing"


def test_voice_returns_answer_and_browser_playable_wav(monkeypatch):
    configure_audio_mocks(monkeypatch, "Hi Spider, describe this room.")
    backboard_calls = []

    async def fake_call_backboard(question_text, thread_id=None):
        backboard_calls.append((question_text, thread_id))
        return {
            "content": "This is a test answer.",
            "thread_id": "thread-new",
            "assistant_id": "assistant-1",
        }

    async def fake_elevenlabs_tts(text):
        assert text == "This is a test answer."
        return b"\x00\x00\x01\x00"

    monkeypatch.setattr(voice_route, "call_backboard", fake_call_backboard)
    monkeypatch.setattr(voice_route, "elevenlabs_tts", fake_elevenlabs_tts)

    response = client.post(
        "/voice",
        data={"thread_id": "thread-existing"},
        files={"audio": ("recording.webm", b"browser-audio", "audio/webm")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["activated"] is True
    assert payload["question"] == "describe this room."
    assert payload["answer"] == "This is a test answer."
    assert payload["thread_id"] == "thread-new"
    assert payload["audio_format"] == "wav_16000_mono"
    assert payload["audio_data_url"].startswith("data:audio/wav;base64,")
    assert backboard_calls == [("describe this room.", "thread-existing")]

    wav_bytes = base64.b64decode(payload["audio_data_url"].split(",", 1)[1])
    with wave.open(io.BytesIO(wav_bytes), "rb") as wav_file:
        assert wav_file.getnchannels() == 1
        assert wav_file.getsampwidth() == 2
        assert wav_file.getframerate() == 16000
        assert wav_file.readframes(wav_file.getnframes()) == b"\x00\x00\x01\x00"


def test_voice_rejects_empty_recording():
    response = client.post(
        "/voice",
        files={"audio": ("recording.webm", b"", "audio/webm")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "The audio recording is empty"


def test_voice_allows_cross_origin_framer_request():
    response = client.options(
        "/voice",
        headers={
            "Origin": "https://example.framer.website",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "*"
