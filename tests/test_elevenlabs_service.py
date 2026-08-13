import importlib

import pytest


class FakeAsyncAudio:
    def __init__(self, chunks=None, error=None):
        self.chunks = list(chunks or [])
        self.error = error

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.error is not None:
            raise self.error

        if not self.chunks:
            raise StopAsyncIteration

        return self.chunks.pop(0)


class FakeTextToSpeech:
    def __init__(self, audio):
        self.audio = audio
        self.calls = []

    def convert(self, **kwargs):
        self.calls.append(kwargs)
        return self.audio


class FakeAsyncElevenLabs:
    instances = []

    def __init__(self, api_key):
        self.api_key = api_key
        self.text_to_speech = None
        self.instances.append(self)


@pytest.fixture
def elevenlabs_service(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-api-key")
    monkeypatch.setenv("ELEVENLABS_VOICE_ID", "test-voice-id")

    from app.services import elevenlabs_service

    return importlib.reload(elevenlabs_service)


def mock_elevenlabs_client(monkeypatch, elevenlabs_service, text_to_speech):
    FakeAsyncElevenLabs.instances = []

    def create_client(api_key):
        client = FakeAsyncElevenLabs(api_key)
        client.text_to_speech = text_to_speech
        return client

    monkeypatch.setattr(elevenlabs_service, "AsyncElevenLabs", create_client)


@pytest.mark.asyncio
async def test_elevenlabs_tts_joins_audio_chunks(elevenlabs_service, monkeypatch):
    text_to_speech = FakeTextToSpeech(FakeAsyncAudio([b"abc", b"def", b"ghi"]))
    mock_elevenlabs_client(monkeypatch, elevenlabs_service, text_to_speech)

    audio = await elevenlabs_service.elevenlabs_tts("hello")

    assert audio == b"abcdefghi"


@pytest.mark.asyncio
async def test_elevenlabs_tts_calls_convert_with_expected_options(
    elevenlabs_service, monkeypatch
):
    text_to_speech = FakeTextToSpeech(FakeAsyncAudio([b"audio"]))
    mock_elevenlabs_client(monkeypatch, elevenlabs_service, text_to_speech)

    await elevenlabs_service.elevenlabs_tts("hello")

    assert FakeAsyncElevenLabs.instances[0].api_key == "test-api-key"
    assert text_to_speech.calls == [
        {
            "text": "hello",
            "voice_id": "test-voice-id",
            "model_id": "eleven_flash_v2_5",
            "output_format": "pcm_16000",
        }
    ]


@pytest.mark.asyncio
async def test_elevenlabs_tts_empty_text_raises_value_error(elevenlabs_service):
    with pytest.raises(ValueError, match="Response from LLM required"):
        await elevenlabs_service.elevenlabs_tts("")


@pytest.mark.asyncio
async def test_elevenlabs_tts_none_text_raises_value_error(elevenlabs_service):
    with pytest.raises(ValueError, match="Response from LLM required"):
        await elevenlabs_service.elevenlabs_tts(None)


@pytest.mark.asyncio
async def test_elevenlabs_tts_propagates_audio_iterator_exception(
    elevenlabs_service, monkeypatch
):
    expected_error = RuntimeError("tts stream failed")
    text_to_speech = FakeTextToSpeech(FakeAsyncAudio(error=expected_error))
    mock_elevenlabs_client(monkeypatch, elevenlabs_service, text_to_speech)

    with pytest.raises(RuntimeError, match="tts stream failed"):
        await elevenlabs_service.elevenlabs_tts("hello")
