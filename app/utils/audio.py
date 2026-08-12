from io import BytesIO
from pydub import AudioSegment


def convert_to_16khz_wav(audio_bytes: bytes) -> bytes:
    audio = AudioSegment.from_file(BytesIO(audio_bytes))

    audio = audio.set_channels(1)
    audio = audio.set_frame_rate(16000)
    audio = audio.set_sample_width(2)  # 16-bit PCM

    output = BytesIO()
    audio.export(output, format="wav")

    return output.getvalue()
