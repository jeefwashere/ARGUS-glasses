import asyncio
import json
import tempfile
import threading
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
    wait_for_release = False
    release_event = threading.Event()

    def __init__(self, on_final_transcript):
        self.on_final_transcript = on_final_transcript
        self.audio_chunks = []
        self.connected = False
        self.closed = False
        self.instances.append(self)

    async def connect(self):
        self.connected = True

    async def send_audio(self, pcm_chunk):
        self.audio_chunks.append(pcm_chunk)
        if not self.transcripts:
            return

        transcript = self.transcripts.pop(0)
        asyncio.create_task(self._emit_transcript(transcript))

    async def close(self):
        self.closed = True

    async def _emit_transcript(self, transcript):
        if self.wait_for_release:
            await asyncio.to_thread(self.release_event.wait)
        await self.on_final_transcript(transcript)


class FakeBackboard:
    def __init__(self, responses=None, error=None):
        self.calls = []
        self.responses = list(responses or [])
        self.error = error

    async def __call__(self, question_text, image=None, thread_id=None):
        image_path = Path(image) if image else None
        image_bytes = image_path.read_bytes() if image_path else None
        self.calls.append(
            {
                "question_text": question_text,
                "image": image_path,
                "image_exists": image_path.exists() if image_path else None,
                "image_bytes": image_bytes,
                "thread_id": thread_id,
            }
        )

        if self.error and image_path is not None:
            raise self.error

        if self.responses:
            return self.responses.pop(0)

        return {
            "content": f"answer for {question_text}",
            "thread_id": "thread-1",
            "assistant_id": "assistant-1",
        }


def setup_route_mocks(
    monkeypatch, backboard=None, transcripts=None, needs_image_questions=None
):
    FakeDeepgramSession.instances = []
    FakeDeepgramSession.transcripts = list(transcripts or [])
    FakeDeepgramSession.wait_for_release = False
    FakeDeepgramSession.release_event = threading.Event()

    backboard = backboard or FakeBackboard()
    needs_image_questions = set(needs_image_questions or [])

    async def fake_decide_image_requirement(question_text, thread_id=None):
        result = await backboard(question_text, thread_id=thread_id)
        needs_image = question_text in needs_image_questions
        return BackboardDecision(
            needs_image=needs_image,
            response=None if needs_image else result["content"],
            thread_id=result["thread_id"],
            assistant_id=result["assistant_id"],
        )

    async def fake_elevenlabs_tts(response_text):
        return FAKE_PCM_AUDIO

    monkeypatch.setattr(ask_route, "DeepgramSession", FakeDeepgramSession)
    monkeypatch.setattr(ask_route, "call_backboard", backboard)
    monkeypatch.setattr(
        ask_route, "decide_image_requirement", fake_decide_image_requirement
    )
    monkeypatch.setattr(ask_route, "elevenlabs_tts", fake_elevenlabs_tts)

    return backboard


def assert_audio_frames(websocket):
    assert websocket.receive_json() == {
        "type": "audio_start",
        "audio_format": "wav_44100_stereo",
        "sample_rate": 44100,
        "channels": 2,
        "bits_per_sample": 16,
    }
    bluetooth_pcm = pcm16_mono_16k_to_stereo_44100(FAKE_PCM_AUDIO)
    assert websocket.receive_bytes() == pcm16_to_wav(
        bluetooth_pcm,
        sample_rate=44100,
        channels=2,
    )
    assert websocket.receive_json() == {"type": "audio_end"}


def test_first_question_speech_only(monkeypatch):
    backboard = setup_route_mocks(
        monkeypatch, transcripts=["Hi Spider, What am I looking at?"]
    )

    with TestClient(app).websocket_connect("/ask") as websocket:
        websocket.send_bytes(b"audio")

        assert websocket.receive_json() == {
            "type": "transcript",
            "text": "What am I looking at?",
        }
        assert websocket.receive_json() == {
            "type": "answer",
            "text": "answer for What am I looking at?",
            "thread_id": "thread-1",
        }
        assert_audio_frames(websocket)
        websocket.send_text("close")

    assert backboard.calls == [
        {
            "question_text": "What am I looking at?",
            "image": None,
            "image_exists": None,
            "image_bytes": None,
            "thread_id": None,
        }
    ]


def test_follow_up_speech_only_reuses_thread_id(monkeypatch):
    backboard = setup_route_mocks(
        monkeypatch,
        backboard=FakeBackboard(
            responses=[
                {"content": "first answer", "thread_id": "thread-123", "assistant_id": "a"},
                {"content": "second answer", "thread_id": "thread-123", "assistant_id": "a"},
            ]
        ),
        transcripts=["Hi Spider, first question", "Hi Spider, second question"],
    )

    with TestClient(app).websocket_connect("/ask") as websocket:
        websocket.send_bytes(b"audio-1")
        websocket.receive_json()
        assert websocket.receive_json()["thread_id"] == "thread-123"
        assert_audio_frames(websocket)

        websocket.send_bytes(b"audio-2")
        websocket.receive_json()
        assert websocket.receive_json()["text"] == "second answer"
        assert_audio_frames(websocket)
        websocket.send_text("close")

    assert backboard.calls[0]["thread_id"] is None
    assert backboard.calls[1]["thread_id"] == "thread-123"


def test_first_question_speech_with_chunked_image(monkeypatch):
    image_bytes = b"jpeg-part-1-jpeg-part-2"
    backboard = setup_route_mocks(monkeypatch, transcripts=["Hi Spider, describe this"])

    with TestClient(app).websocket_connect("/ask") as websocket:
        websocket.send_text(
            json.dumps({"type": "image_start", "content_type": "image/jpeg"})
        )
        assert websocket.receive_json() == {"type": "image_started"}
        websocket.send_bytes(b"jpeg-part-1-")
        websocket.send_bytes(b"jpeg-part-2")
        websocket.send_text(json.dumps({"type": "image_end"}))
        assert websocket.receive_json() == {"type": "image_received"}

        websocket.send_bytes(b"audio")
        assert websocket.receive_json()["type"] == "transcript"
        assert websocket.receive_json()["type"] == "answer"
        assert_audio_frames(websocket)
        websocket.send_text("close")

    assert len(backboard.calls) == 2
    call = backboard.calls[1]
    assert call["question_text"] == "describe this"
    assert call["thread_id"] == "thread-1"
    assert call["image_exists"] is True
    assert call["image_bytes"] == image_bytes
    assert not call["image"].exists()


def test_follow_up_speech_with_image_reuses_thread_id(monkeypatch):
    backboard = setup_route_mocks(
        monkeypatch,
        backboard=FakeBackboard(
            responses=[
                {"content": "first", "thread_id": "thread-abc", "assistant_id": "a"},
                {"content": "second", "thread_id": "thread-abc", "assistant_id": "a"},
            ]
        ),
        transcripts=["Hi Spider, first", "Hi Spider, second with image"],
    )

    with TestClient(app).websocket_connect("/ask") as websocket:
        websocket.send_bytes(b"audio-1")
        websocket.receive_json()
        websocket.receive_json()
        assert_audio_frames(websocket)

        websocket.send_text(
            json.dumps({"type": "image_start", "content_type": "image/jpeg"})
        )
        websocket.receive_json()
        websocket.send_bytes(b"image")
        websocket.send_text(json.dumps({"type": "image_end"}))
        websocket.receive_json()
        websocket.send_bytes(b"audio-2")
        websocket.receive_json()
        websocket.receive_json()
        assert_audio_frames(websocket)
        websocket.send_text("close")

    assert backboard.calls[2]["question_text"] == "second with image"
    assert backboard.calls[2]["thread_id"] == "thread-abc"
    assert backboard.calls[2]["image_bytes"] == b"image"


def test_transcript_arrives_before_image_end_waits(monkeypatch):
    FakeDeepgramSession.wait_for_release = True
    backboard = setup_route_mocks(
        monkeypatch, transcripts=["Hi Spider, question with pending image"]
    )
    FakeDeepgramSession.wait_for_release = True

    with TestClient(app).websocket_connect("/ask") as websocket:
        websocket.send_bytes(b"audio")
        websocket.send_text(
            json.dumps({"type": "image_start", "content_type": "image/jpeg"})
        )
        assert websocket.receive_json() == {"type": "image_started"}

        FakeDeepgramSession.release_event.set()
        assert websocket.receive_json()["type"] == "transcript"
        assert len(backboard.calls) == 1
        assert backboard.calls[0]["image"] is None

        websocket.send_bytes(b"image")
        websocket.send_text(json.dumps({"type": "image_end"}))
        assert websocket.receive_json() == {"type": "image_received"}
        assert websocket.receive_json()["type"] == "answer"
        assert_audio_frames(websocket)
        websocket.send_text("close")

    assert len(backboard.calls) == 2
    assert backboard.calls[1]["image_bytes"] == b"image"


def test_image_finishes_before_transcript_waits(monkeypatch):
    backboard = setup_route_mocks(
        monkeypatch, transcripts=["Hi Spider, late transcript"]
    )

    with TestClient(app).websocket_connect("/ask") as websocket:
        websocket.send_text(
            json.dumps({"type": "image_start", "content_type": "image/jpeg"})
        )
        websocket.receive_json()
        websocket.send_bytes(b"image")
        websocket.send_text(json.dumps({"type": "image_end"}))
        assert websocket.receive_json() == {"type": "image_received"}
        assert backboard.calls == []

        websocket.send_bytes(b"audio")
        assert websocket.receive_json()["type"] == "transcript"
        assert websocket.receive_json()["type"] == "answer"
        assert_audio_frames(websocket)
        websocket.send_text("close")

    assert len(backboard.calls) == 2


def test_normal_speech_only_submits_immediately(monkeypatch):
    backboard = setup_route_mocks(monkeypatch, transcripts=["Hi Spider, speech only"])

    with TestClient(app).websocket_connect("/ask") as websocket:
        websocket.send_bytes(b"audio")
        assert websocket.receive_json()["type"] == "transcript"
        assert websocket.receive_json()["type"] == "answer"
        assert_audio_frames(websocket)
        websocket.send_text("close")

    assert len(backboard.calls) == 1
    assert backboard.calls[0]["image"] is None


def test_speech_without_wake_phrase_is_ignored(monkeypatch):
    backboard = setup_route_mocks(
        monkeypatch, transcripts=["this should not trigger a reply"]
    )

    with TestClient(app).websocket_connect("/ask") as websocket:
        websocket.send_bytes(b"audio")
        assert websocket.receive_json() == {
            "type": "wake_ignored",
            "text": "this should not trigger a reply",
            "wake_phrase": "Hi Spider",
        }
        websocket.send_text("close")

    assert backboard.calls == []


def test_wake_phrase_alone_arms_the_next_utterance(monkeypatch):
    backboard = setup_route_mocks(
        monkeypatch, transcripts=["Hi Spider", "what am I looking at?"]
    )

    with TestClient(app).websocket_connect("/ask") as websocket:
        websocket.send_bytes(b"wake-audio")
        assert websocket.receive_json() == {
            "type": "wake_detected",
            "text": "Hi Spider",
            "wake_phrase": "Hi Spider",
            "window_seconds": 10,
        }

        websocket.send_bytes(b"question-audio")
        assert websocket.receive_json() == {
            "type": "transcript",
            "text": "what am I looking at?",
        }
        assert websocket.receive_json()["type"] == "answer"
        assert_audio_frames(websocket)
        websocket.send_text("close")

    assert len(backboard.calls) == 1
    assert backboard.calls[0]["question_text"] == "what am I looking at?"


def test_unsupported_image_type_returns_error(monkeypatch):
    backboard = setup_route_mocks(monkeypatch)

    with TestClient(app).websocket_connect("/ask") as websocket:
        websocket.send_text(
            json.dumps({"type": "image_start", "content_type": "application/pdf"})
        )
        response = websocket.receive_json()
        websocket.send_text("close")

    assert response["type"] == "error"
    assert "Unsupported image type" in response["message"]
    assert backboard.calls == []


def test_duplicate_image_start_does_not_overwrite_upload(monkeypatch):
    backboard = setup_route_mocks(monkeypatch, transcripts=["Hi Spider, question"])

    with TestClient(app).websocket_connect("/ask") as websocket:
        websocket.send_text(
            json.dumps({"type": "image_start", "content_type": "image/jpeg"})
        )
        websocket.receive_json()
        websocket.send_bytes(b"original")
        websocket.send_text(
            json.dumps({"type": "image_start", "content_type": "image/png"})
        )
        response = websocket.receive_json()

        websocket.send_text(json.dumps({"type": "image_end"}))
        websocket.receive_json()
        websocket.send_bytes(b"audio")
        websocket.receive_json()
        websocket.receive_json()
        assert_audio_frames(websocket)
        websocket.send_text("close")

    assert response["type"] == "error"
    assert "already in progress" in response["message"]
    assert backboard.calls[1]["image_bytes"] == b"original"


def test_image_end_without_image_start_returns_error(monkeypatch):
    backboard = setup_route_mocks(monkeypatch)

    with TestClient(app).websocket_connect("/ask") as websocket:
        websocket.send_text(json.dumps({"type": "image_end"}))
        response = websocket.receive_json()
        websocket.send_text("close")

    assert response["type"] == "error"
    assert "No image upload" in response["message"]
    assert backboard.calls == []


def test_backboard_failure_sends_safe_error_and_deletes_image(monkeypatch):
    backboard = setup_route_mocks(
        monkeypatch,
        backboard=FakeBackboard(error=RuntimeError("secret backend detail")),
        transcripts=["Hi Spider, question"],
    )

    with TestClient(app).websocket_connect("/ask") as websocket:
        websocket.send_text(
            json.dumps({"type": "image_start", "content_type": "image/jpeg"})
        )
        websocket.receive_json()
        websocket.send_bytes(b"image")
        websocket.send_text(json.dumps({"type": "image_end"}))
        websocket.receive_json()
        websocket.send_bytes(b"audio")
        assert websocket.receive_json()["type"] == "transcript"
        error = websocket.receive_json()
        websocket.send_text("close")

    assert error == {"type": "error", "message": "Failed to process the question"}
    assert len(backboard.calls) == 2
    assert not backboard.calls[1]["image"].exists()


def test_disconnect_during_image_upload_deletes_temp_file(monkeypatch, tmp_path):
    paths = []
    real_named_temporary_file = tempfile.NamedTemporaryFile

    def named_temporary_file(*, delete, suffix):
        file = real_named_temporary_file(delete=delete, suffix=suffix, dir=tmp_path)
        paths.append(Path(file.name))
        return file

    setup_route_mocks(monkeypatch)
    monkeypatch.setattr(ask_route.tempfile, "NamedTemporaryFile", named_temporary_file)

    with TestClient(app).websocket_connect("/ask") as websocket:
        websocket.send_text(
            json.dumps({"type": "image_start", "content_type": "image/jpeg"})
        )
        websocket.receive_json()
        websocket.send_bytes(b"partial")

    assert paths
    assert all(not path.exists() for path in paths)


def test_set_thread_uses_existing_thread_id(monkeypatch):
    backboard = setup_route_mocks(monkeypatch, transcripts=["Hi Spider, question"])

    with TestClient(app).websocket_connect("/ask") as websocket:
        websocket.send_text(json.dumps({"type": "set_thread", "thread_id": "existing-id"}))
        assert websocket.receive_json() == {
            "type": "thread_set",
            "thread_id": "existing-id",
        }
        websocket.send_bytes(b"audio")
        websocket.receive_json()
        websocket.receive_json()
        assert_audio_frames(websocket)
        websocket.send_text("close")

    assert backboard.calls[0]["thread_id"] == "existing-id"


def test_close_messages_close_cleanly(monkeypatch):
    for close_message in ["close", json.dumps({"type": "close"})]:
        setup_route_mocks(monkeypatch)
        with TestClient(app).websocket_connect("/ask") as websocket:
            websocket.send_text(close_message)

        assert FakeDeepgramSession.instances[-1].closed is True


def test_invalid_json_control_message_keeps_connection_usable(monkeypatch):
    backboard = setup_route_mocks(monkeypatch, transcripts=["Hi Spider, still works"])

    with TestClient(app).websocket_connect("/ask") as websocket:
        websocket.send_text("{not-json")
        response = websocket.receive_json()
        websocket.send_bytes(b"audio")
        assert websocket.receive_json()["type"] == "transcript"
        assert websocket.receive_json()["type"] == "answer"
        assert_audio_frames(websocket)
        websocket.send_text("close")

    assert response["type"] == "error"
    assert len(backboard.calls) == 1


def test_backboard_requests_correlated_camera_image(monkeypatch):
    question = "What am I looking at?"
    backboard = setup_route_mocks(
        monkeypatch,
        transcripts=[f"Hi Spider, {question}"],
        needs_image_questions=[question],
    )

    with TestClient(app).websocket_connect("/ask") as websocket:
        websocket.send_bytes(b"audio")
        assert websocket.receive_json() == {"type": "transcript", "text": question}

        camera_request = websocket.receive_json()
        assert camera_request["type"] == "take_picture"
        request_id = camera_request["request_id"]

        websocket.send_text(
            json.dumps(
                {
                    "type": "image_start",
                    "request_id": request_id,
                    "content_type": "image/jpeg",
                }
            )
        )
        assert websocket.receive_json() == {
            "type": "image_started",
            "request_id": request_id,
        }
        websocket.send_bytes(b"captured-jpeg")
        websocket.send_text(
            json.dumps({"type": "image_end", "request_id": request_id})
        )
        assert websocket.receive_json() == {
            "type": "image_received",
            "request_id": request_id,
        }
        assert websocket.receive_json()["type"] == "answer"
        assert_audio_frames(websocket)
        websocket.send_text("close")

    assert len(backboard.calls) == 2
    assert backboard.calls[0]["question_text"] == question
    assert backboard.calls[0]["image"] is None
    assert backboard.calls[1]["question_text"] == question
    assert backboard.calls[1]["thread_id"] == "thread-1"
    assert backboard.calls[1]["image_bytes"] == b"captured-jpeg"


def test_wrong_camera_request_id_is_rejected_without_stealing_image(monkeypatch):
    question = "Read this sign"
    backboard = setup_route_mocks(
        monkeypatch,
        needs_image_questions=[question],
    )

    with TestClient(app).websocket_connect("/ask") as websocket:
        websocket.send_text(json.dumps({"type": "question", "text": question}))
        assert websocket.receive_json()["type"] == "transcript"
        request = websocket.receive_json()
        request_id = request["request_id"]

        websocket.send_text(
            json.dumps(
                {
                    "type": "image_start",
                    "request_id": "wrong-id",
                    "content_type": "image/jpeg",
                }
            )
        )
        error = websocket.receive_json()
        assert error["type"] == "error"
        assert error["request_id"] == "wrong-id"

        websocket.send_text(
            json.dumps(
                {
                    "type": "image_start",
                    "request_id": request_id,
                    "content_type": "image/jpeg",
                }
            )
        )
        websocket.receive_json()
        websocket.send_bytes(b"right-image")
        websocket.send_text(
            json.dumps({"type": "image_end", "request_id": request_id})
        )
        websocket.receive_json()
        websocket.receive_json()
        assert_audio_frames(websocket)
        websocket.send_text("close")

    assert backboard.calls[1]["image_bytes"] == b"right-image"


def test_second_question_queues_while_first_waits_for_camera(monkeypatch):
    first = "What is this object?"
    second = "What is five times eight?"
    backboard = setup_route_mocks(
        monkeypatch,
        needs_image_questions=[first],
    )

    with TestClient(app).websocket_connect("/ask") as websocket:
        websocket.send_text(json.dumps({"type": "question", "text": first}))
        assert websocket.receive_json()["text"] == first
        request_id = websocket.receive_json()["request_id"]

        websocket.send_text(json.dumps({"type": "question", "text": second}))
        assert websocket.receive_json() == {"type": "transcript", "text": second}

        websocket.send_text(
            json.dumps(
                {
                    "type": "image_start",
                    "request_id": request_id,
                    "content_type": "image/jpeg",
                }
            )
        )
        websocket.receive_json()
        websocket.send_bytes(b"first-image")
        websocket.send_text(
            json.dumps({"type": "image_end", "request_id": request_id})
        )
        websocket.receive_json()

        assert websocket.receive_json()["text"] == f"answer for {first}"
        assert_audio_frames(websocket)
        assert websocket.receive_json()["text"] == f"answer for {second}"
        assert_audio_frames(websocket)
        websocket.send_text("close")

    assert [call["question_text"] for call in backboard.calls] == [
        first,
        first,
        second,
    ]
    assert backboard.calls[1]["image_bytes"] == b"first-image"
    assert backboard.calls[2]["image"] is None


def test_camera_failure_returns_error_without_tts(monkeypatch):
    question = "Can you read this?"
    setup_route_mocks(monkeypatch, needs_image_questions=[question])

    with TestClient(app).websocket_connect("/ask") as websocket:
        websocket.send_text(json.dumps({"type": "question", "text": question}))
        websocket.receive_json()
        request_id = websocket.receive_json()["request_id"]
        websocket.send_text(
            json.dumps(
                {
                    "type": "image_error",
                    "request_id": request_id,
                    "message": "Camera unavailable",
                }
            )
        )
        assert websocket.receive_json() == {
            "type": "error",
            "message": "Camera unavailable",
            "request_id": request_id,
        }
        websocket.send_text("close")


def test_camera_timeout_returns_error_instead_of_hanging(monkeypatch):
    question = "What color is this?"
    setup_route_mocks(monkeypatch, needs_image_questions=[question])
    monkeypatch.setattr(ask_route, "IMAGE_TIMEOUT_SECONDS", 0.01)

    with TestClient(app).websocket_connect("/ask") as websocket:
        websocket.send_text(json.dumps({"type": "question", "text": question}))
        websocket.receive_json()
        request = websocket.receive_json()
        error = websocket.receive_json()
        websocket.send_text("close")

    assert error == {
        "type": "error",
        "message": "Camera image timed out",
        "request_id": request["request_id"],
    }


def test_bluetooth_audio_conversion_failure_is_graceful(monkeypatch):
    setup_route_mocks(monkeypatch)

    def fail_conversion(_pcm_audio):
        raise ValueError("invalid PCM from test")

    monkeypatch.setattr(
        ask_route,
        "pcm16_mono_16k_to_stereo_44100",
        fail_conversion,
    )

    with TestClient(app).websocket_connect("/ask") as websocket:
        websocket.send_text(json.dumps({"type": "question", "text": "hello"}))
        assert websocket.receive_json()["type"] == "transcript"
        assert websocket.receive_json()["type"] == "answer"
        assert websocket.receive_json() == {
            "type": "audio_error",
            "message": "Speech generation failed.",
        }
        websocket.send_text("close")
