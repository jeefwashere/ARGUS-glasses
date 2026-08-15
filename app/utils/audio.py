from io import BytesIO
import wave

from pydub import AudioSegment


def convert_to_16khz_wav(audio_bytes: bytes) -> bytes:
    audio = AudioSegment.from_file(BytesIO(audio_bytes))

    audio = audio.set_channels(1)
    audio = audio.set_frame_rate(16000)
    audio = audio.set_sample_width(2)  # 16-bit PCM

    output = BytesIO()
    audio.export(output, format="wav")

    return output.getvalue()


def pcm16_to_wav(pcm_bytes: bytes, sample_rate: int = 16000) -> bytes:
    output = BytesIO()
    with wave.open(output, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_bytes)
    return output.getvalue()
