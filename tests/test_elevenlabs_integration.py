import importlib
import os

import pytest
from dotenv import load_dotenv


@pytest.mark.integration
@pytest.mark.asyncio
async def test_elevenlabs_tts_real_api_call_returns_audio_bytes():
    load_dotenv()

    if not os.getenv("ELEVENLABS_API_KEY") or not os.getenv("ELEVENLABS_VOICE_ID"):
        pytest.skip("ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID are required")

    from app.services import elevenlabs_service

    service = importlib.reload(elevenlabs_service)

    audio = await service.elevenlabs_tts("Test")

    assert isinstance(audio, bytes)
    assert len(audio) > 0
