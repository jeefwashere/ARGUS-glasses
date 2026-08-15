import asyncio
import base64
import io
import json
import wave
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.routes import ask as ask_route
from app.services.backboard_service import BackboardDecision
from app.utils.audio import pcm16_mono_16k_to_stereo_44100, pcm16_to_wav

FAKE_PCM_AUDIO = b"\x00\x00\x00\x10\x00\x00\x00\xf0"


class FakeDeepgramSession:
    instances = []
    transcripts = []

    def __init__(self, on_final_transcript):
        self.on_final_transcript = on_final_transcript
        self.audio_chunks = []
        self.closed = False
        self.instances.append(self)

    async def connect(self):
        pass

    async def send_audio(self, chunk):
        self.audio_chunks.append(chunk)
        if self.transcripts:
            asyncio.create_task(self.on_final_transcript(self.transcripts.pop(0)))

    async def close(self):
        self.closed = True


class FakeBackboard:
    def __init__(self, responses=None):
        self.calls = []
        self.responses = list(responses or [])

    async def __call__(self, question_text, image=None, thread_id=None):
        path = Path(image) if image else None
        self.calls.append(
            {
                "question_text": question_text,
                "image": path,
                "image_bytes": path.read_bytes() if path else None,
                "thread_id": thread_id,
            }
        )
        if self.responses:
            return self.responses.pop(0)
        return {
            "content": f"answer for {question_text}",
            "thread_id": "thread-1",
            "assistant_id": "assistant-1",
        }


def setup_route_mocks(monkeypatch, *, transcripts=None, vision_questions=None):
    FakeDeepgramSession.instances = []
    FakeDeepgramSession.transcripts = list(transcripts or [])
    backboard = FakeBackboard()
    vision_questions = set(vision_questions or [])

    async def fake_decision(question_text, thread_id=None):
        result = await backboard(question_text, thread_id=thread_id)
        needs_image = question_text in vision_questions
        return BackboardDecision(
            needs_image=needs_image,
            response=None if needs_image else result["content"],
            thread_id=result["thread_id"],
            assistant_id=result["assistant_id"],
        )

    async def fake_tts(_text):
        return FAKE_PCM_AUDIO

    monkeypatch.setattr(ask_route, "DeepgramSession", FakeDeepgramSession)
    monkeypatch.setattr(ask_route, "call_backboard", backboard)
    monkeypatch.setattr(ask_route, "decide_image_requirement", fake_decision)
    monkeypatch.setattr(ask_route, "elevenlabs_tts", fake_tts)
    return backboard


def assert_browser_audio(websocket):
    message = websocket.receive_json()
    assert message["type"] == "audio"
    assert message["audio_mime_type"] == "audio/wav"
    assert message["audio_format"] == "wav_16000_mono"
    assert message["sample_rate"] == 16000
    assert message["channels"] == 1
    assert message["bits_per_sample"] == 16

    wav_bytes = base64.b64decode(message["audio_base64"])
    with wave.open(io.BytesIO(wav_bytes), "rb") as wav_file:
        assert wav_file.getnchannels() == 1
        assert wav_file.getsampwidth() == 2
        assert wav_file.getframerate() == 16000
        assert wav_file.readframes(wav_file.getnframes()) == FAKE_PCM_AUDIO


def assert_esp32_audio_frames(websocket):
    assert websocket.receive_json() == {
        "type": "audio_start",
        "audio_format": "wav_44100_stereo",
        "sample_rate": 44100,
        "channels": 2,
        "bits_per_sample": 16,
    }
    converted = pcm16_mono_16k_to_stereo_44100(FAKE_PCM_AUDIO)
    assert websocket.receive_bytes() == pcm16_to_wav(
        converted, sample_rate=44100, channels=2
    )
    assert websocket.receive_json() == {"type": "audio_end"}


def test_text_only_question_preserves_audio_response(monkeypatch):
    monkeypatch.delenv("AUDIO_OUTPUT_MODE", raising=False)
    backboard = setup_route_mocks(
        monkeypatch, transcripts=["Hi Spider, What is five times eight?"]
    )
    with TestClient(app).websocket_connect("/ask") as browser:
        browser.send_bytes(b"microphone-pcm")
        assert browser.receive_json()["type"] == "transcript"
        assert browser.receive_json()["type"] == "answer"
        assert_browser_audio(browser)
        browser.send_text("close")
    assert FakeDeepgramSession.instances[-1].audio_chunks == [b"microphone-pcm"]
    assert backboard.calls[0]["image"] is None


def test_visual_question_uses_device_not_browser(monkeypatch):
    monkeypatch.setenv("AUDIO_OUTPUT_MODE", "browser")
    question = "What am I looking at?"
    backboard = setup_route_mocks(monkeypatch, vision_questions=[question])
    with TestClient(app) as client:
        with client.websocket_connect("/device?device_id=argus-1") as device:
            assert device.receive_json() == {
                "type": "device_connected",
                "device_id": "argus-1",
            }
            with client.websocket_connect("/ask") as browser:
                browser.send_text(json.dumps({"type": "question", "text": question}))
                assert browser.receive_json() == {"type": "transcript", "text": question}
                command = device.receive_json()
                request_id = command["request_id"]
                assert command == {"type": "take_picture", "request_id": request_id}
                device.send_text(
                    json.dumps(
                        {
                            "type": "image_start",
                            "request_id": request_id,
                            "content_type": "image/jpeg",
                            "size": 13,
                        }
                    )
                )
                assert device.receive_json()["type"] == "image_started"
                device.send_bytes(b"captured-jpeg")
                device.send_text(
                    json.dumps({"type": "image_end", "request_id": request_id})
                )
                assert device.receive_json()["type"] == "image_received"
                assert browser.receive_json()["type"] == "answer"
                assert_browser_audio(browser)
                browser.send_text("close")
            device.send_text("close")
    assert [call["question_text"] for call in backboard.calls] == [question, question]
    assert backboard.calls[1]["thread_id"] == "thread-1"
    assert backboard.calls[1]["image_bytes"] == b"captured-jpeg"
    assert not backboard.calls[1]["image"].exists()


def test_visual_question_fails_immediately_when_device_offline(monkeypatch):
    question = "Read this sign"
    setup_route_mocks(monkeypatch, vision_questions=[question])
    with TestClient(app).websocket_connect("/ask") as browser:
        browser.send_text(json.dumps({"type": "question", "text": question}))
        assert browser.receive_json()["type"] == "transcript"
        assert browser.receive_json() == {
            "type": "error",
            "message": "Camera device is not connected",
        }
        browser.send_text("close")


def test_image_error_is_returned_to_ask_client(monkeypatch):
    question = "Can you read this?"
    setup_route_mocks(monkeypatch, vision_questions=[question])
    with TestClient(app) as client:
        with client.websocket_connect("/device?device_id=argus-1") as device:
            device.receive_json()
            with client.websocket_connect("/ask") as browser:
                browser.send_text(json.dumps({"type": "question", "text": question}))
                browser.receive_json()
                request_id = device.receive_json()["request_id"]
                device.send_text(
                    json.dumps(
                        {
                            "type": "image_error",
                            "request_id": request_id,
                            "message": "Camera capture failed",
                        }
                    )
                )
                assert browser.receive_json() == {
                    "type": "error",
                    "message": "Camera capture failed",
                    "request_id": request_id,
                }
                browser.send_text("close")
            device.send_text("close")


def test_camera_timeout_returns_error(monkeypatch):
    question = "What color is this?"
    setup_route_mocks(monkeypatch, vision_questions=[question])
    monkeypatch.setattr(ask_route, "IMAGE_TIMEOUT_SECONDS", 0.01)
    with TestClient(app) as client:
        with client.websocket_connect("/device?device_id=argus-1") as device:
            device.receive_json()
            with client.websocket_connect("/ask") as browser:
                browser.send_text(json.dumps({"type": "question", "text": question}))
                browser.receive_json()
                request_id = device.receive_json()["request_id"]
                assert browser.receive_json() == {
                    "type": "error",
                    "message": "Camera image timed out",
                    "request_id": request_id,
                }
                browser.send_text("close")
            device.send_text("close")


def test_device_requires_explicit_identity():
    with TestClient(app).websocket_connect("/device") as device:
        assert device.receive_json()["message"] == "device_id query parameter is required"


def test_browser_mode_returns_audio_without_bluetooth_conversion(monkeypatch):
    setup_route_mocks(monkeypatch)
    monkeypatch.setenv("AUDIO_OUTPUT_MODE", "browser")

    def unexpected_bluetooth_conversion(_audio):
        raise AssertionError("Browser mode must not enter the ESP32 audio path")

    monkeypatch.setattr(
        ask_route,
        "pcm16_mono_16k_to_stereo_44100",
        unexpected_bluetooth_conversion,
    )
    with TestClient(app).websocket_connect("/ask") as browser:
        browser.send_text(json.dumps({"type": "question", "text": "hello"}))
        browser.receive_json()
        browser.receive_json()
        assert_browser_audio(browser)
        browser.send_text("close")


def test_esp32_bluetooth_mode_preserves_existing_audio_route(monkeypatch):
    setup_route_mocks(monkeypatch)
    monkeypatch.setenv("AUDIO_OUTPUT_MODE", "esp32_bluetooth")

    with TestClient(app).websocket_connect("/ask") as browser:
        browser.send_text(json.dumps({"type": "question", "text": "hello"}))
        browser.receive_json()
        browser.receive_json()
        assert_esp32_audio_frames(browser)
        browser.send_text("close")


def test_bluetooth_conversion_failure_is_graceful(monkeypatch):
    setup_route_mocks(monkeypatch)
    monkeypatch.setenv("AUDIO_OUTPUT_MODE", "esp32_bluetooth")

    def fail_conversion(_audio):
        raise ValueError("bad PCM")

    monkeypatch.setattr(ask_route, "pcm16_mono_16k_to_stereo_44100", fail_conversion)
    with TestClient(app).websocket_connect("/ask") as browser:
        browser.send_text(json.dumps({"type": "question", "text": "hello"}))
        browser.receive_json()
        browser.receive_json()
        assert browser.receive_json() == {
            "type": "audio_error",
            "message": "Speech generation failed.",
        }
        browser.send_text("close")
