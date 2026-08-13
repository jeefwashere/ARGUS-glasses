import os

from elevenlabs.client import ElevenLabs

client = ElevenLabs(
    api_key=os.getenv("ELEVENLABS_API_KEY"),
)


async def elevenlabs_tts(response_text: str) -> bytes:

    if not response_text:
        raise ValueError("Response from LLM required to generate speech audio")

    audio = await client.text_to_speech.convert(
        text=response_text,
        voice_id=os.getenv("ELEVENLABS_VOICE_ID"),
        model_id="eleven_flash_v2_5",
        output_format="pcm_16000",
    )

    return b"".join(audio)
