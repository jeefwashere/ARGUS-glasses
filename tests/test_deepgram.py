import asyncio
from types import SimpleNamespace

import pytest

from app.services import deepgram_service
from app.services.deepgram_service import DeepgramSession


class FakeSocket:
    def __init__(self, messages=None, wait_forever=False):
        self.messages = list(messages or [])
        self.wait_forever = wait_forever
        self.sent_media = []
        self.close_stream_sent = False

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.messages:
            return self.messages.pop(0)

        if self.wait_forever:
            await asyncio.Future()

        raise StopAsyncIteration

    async def send_media(self, message):
        self.sent_media.append(message)

    async def send_close_stream(self):
        self.close_stream_sent = True


class FakeConnectionManager:
    def __init__(self, socket):
        self.socket = socket
        self.exited = False

    async def __aenter__(self):
        return self.socket

    async def __aexit__(self, exc_type, exc, traceback):
        self.exited = True


class FakeV2Client:
    def __init__(self, manager):
        self.manager = manager
        self.connect_kwargs = None

    def connect(self, **kwargs):
        self.connect_kwargs = kwargs
        return self.manager


class FakeDeepgramClient:
    instances = []

    def __init__(self, api_key):
        self.api_key = api_key
        self.socket = FakeSocket(wait_forever=True)
        self.manager = FakeConnectionManager(self.socket)
        self.v2 = FakeV2Client(self.manager)
        self.listen = SimpleNamespace(v2=self.v2)
        self.instances.append(self)


async def noop_callback(text):
    pass


def test_connect_requires_deepgram_api_key(monkeypatch):
    monkeypatch.delenv("DEEPGRAM_API_KEY", raising=False)
    session = DeepgramSession(on_final_transcript=noop_callback)

    with pytest.raises(RuntimeError, match="DEEPGRAM_API_KEY is not set"):
        asyncio.run(session.connect())


def test_connect_uses_flux_options_and_send_audio(monkeypatch):
    FakeDeepgramClient.instances = []
    monkeypatch.setenv("DEEPGRAM_API_KEY", "test-key")
    monkeypatch.setattr(deepgram_service, "AsyncDeepgramClient", FakeDeepgramClient)

    async def run_test():
        session = DeepgramSession(on_final_transcript=noop_callback)
        await session.connect()

        client = FakeDeepgramClient.instances[0]
        assert client.api_key == "test-key"
        assert client.v2.connect_kwargs == {
            "model": "flux-general-en",
            "eot_threshold": 0.7,
            "eot_timeout_ms": 5000,
            "encoding": "linear16",
            "sample_rate": 16000,
        }

        await session.send_audio(b"pcm bytes")
        assert client.socket.sent_media == [b"pcm bytes"]

        await session.close()
        assert client.socket.close_stream_sent is True
        assert client.manager.exited is True

    asyncio.run(run_test())


def test_send_audio_requires_connected_session():
    session = DeepgramSession(on_final_transcript=noop_callback)

    with pytest.raises(RuntimeError, match="Deepgram session is not connected"):
        asyncio.run(session.send_audio(b"pcm bytes"))


def test_listen_emits_final_transcript_on_end_of_turn():
    transcripts = []

    async def collect_transcript(text):
        transcripts.append(text)

    messages = [
        SimpleNamespace(type="Connected"),
        SimpleNamespace(type="TurnInfo", event="StartOfTurn", transcript=""),
        SimpleNamespace(type="TurnInfo", event="Update", transcript="What am"),
        SimpleNamespace(
            type="TurnInfo", event="EndOfTurn", transcript="What am I looking at?"
        ),
    ]

    async def run_test():
        session = DeepgramSession(on_final_transcript=collect_transcript)
        session._socket = FakeSocket(messages=messages)
        await session._listen()

    asyncio.run(run_test())

    assert transcripts == ["What am I looking at?"]


def test_listen_raises_on_deepgram_error_messages():
    messages = [
        SimpleNamespace(type="ConfigureFailure", reason="bad config"),
    ]

    async def run_test():
        session = DeepgramSession(on_final_transcript=noop_callback)
        session._socket = FakeSocket(messages=messages)
        await session._listen()

    with pytest.raises(RuntimeError, match="Deepgram configure failure"):
        asyncio.run(run_test())
