import subprocess
import tempfile
import os

from io import BytesIO
from pydub import AudioSegment


def audio_bytes_to_16khz_wav(audio_bytes: bytes, output_path: str) -> None:
    audio = AudioSegment.from_file(BytesIO(audio_bytes))

    audio = (
        audio.set_frame_rate(16000).set_channels(1).set_sample_width(2)  # 16-bit PCM
    )

    audio.export(output_path, format="wav")
