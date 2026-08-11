import asyncio
import os
from collections.abc import Awaitable, Callable
from typing import Any

from deepgram import AsyncDeepgramClient

FinalTranscriptCallback = Callable[[str], Awaitable[None]]


class DeepgramFluxSession:
    """Small wrapper around Deepgram Flux's async streaming websocket."""

    def __init__(self, on_final_transcript: FinalTranscriptCallback):
        self._on_final_transcript = on_final_transcript
        self._client: AsyncDeepgramClient | None = None
        self._connection_manager: Any | None = None
        self._socket: Any | None = None
        self._listener_task: asyncio.Task[None] | None = None

    async def connect(self) -> None:
        api_key = os.getenv("DEEPGRAM_API_KEY")
        if not api_key:
            raise RuntimeError("DEEPGRAM_API_KEY is not set")

        self._client = AsyncDeepgramClient(api_key=api_key)
        self._connection_manager = self._client.listen.v2.connect(
            model="flux-general-en",
            eot_threshold=0.7,
            eot_timeout_ms=5000,
            encoding="linear16",
            sample_rate=16000,
        )
        self._socket = await self._connection_manager.__aenter__()
        self._listener_task = asyncio.create_task(self._listen())

    async def send_audio(self, pcm_chunk: bytes) -> None:
        if self._socket is None:
            raise RuntimeError("Deepgram session is not connected")

        self._raise_if_listener_failed()
        await self._socket.send_media(pcm_chunk)

    async def close(self) -> None:
        if self._socket is not None:
            try:
                await self._socket.send_close_stream()
            except Exception as exc:
                print(f"Deepgram close stream failed: {exc}")

        if self._listener_task is not None:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass

        if self._connection_manager is not None:
            await self._connection_manager.__aexit__(None, None, None)

        self._socket = None
        self._connection_manager = None
        self._listener_task = None

    async def _listen(self) -> None:
        async for message in self._socket:
            message_type = getattr(message, "type", None)

            if message_type == "Connected":
                print("Deepgram Flux connection opened")
                continue

            if message_type == "ConfigureFailure":
                raise RuntimeError(f"Deepgram configure failure: {message}")

            if message_type == "FatalError":
                raise RuntimeError(f"Deepgram fatal error: {message}")

            if message_type != "TurnInfo":
                continue

            event = getattr(message, "event", None)
            transcript = (getattr(message, "transcript", "") or "").strip()

            if event == "StartOfTurn":
                print("Deepgram StartOfTurn")
            elif event == "Update" and transcript:
                print(f"Deepgram transcript update: {transcript}")
            elif event == "EndOfTurn":
                print(f"Deepgram EndOfTurn: {transcript}")
                if transcript:
                    await self._on_final_transcript(transcript)

    def _raise_if_listener_failed(self) -> None:
        if self._listener_task is None or not self._listener_task.done():
            return

        exc = self._listener_task.exception()
        if exc is not None:
            raise RuntimeError("Deepgram listener stopped unexpectedly") from exc
