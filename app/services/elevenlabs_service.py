import os

from elevenlabs.client import AsyncElevenLabs


async def elevenlabs_tts(response_text: str) -> bytes:
    if not response_text:
        raise ValueError("Response from LLM required to generate speech audio")

    api_key = os.getenv("ELEVENLABS_API_KEY")
    voice_id = os.getenv("ELEVENLABS_VOICE_ID")

    if not api_key:
        raise ValueError("ELEVENLABS_API_KEY is not set")

    if not voice_id:
        raise ValueError("ELEVENLABS_VOICE_ID is not set")

    client = AsyncElevenLabs(
        api_key=api_key,
    )

    audio = client.text_to_speech.convert(
        text=response_text,
        voice_id=voice_id,
        model_id="eleven_flash_v2_5",
        output_format="pcm_16000",
    )

    return b"".join([chunk async for chunk in audio])
