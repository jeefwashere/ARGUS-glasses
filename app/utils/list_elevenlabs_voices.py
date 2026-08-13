import os

from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs

load_dotenv()

client = ElevenLabs(
    api_key=os.getenv("ELEVENLABS_API_KEY"),
)

response = client.voices.search()

for voice in response.voices:
    print(voice.name, voice.voice_id, voice.category)
