import audioop
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


def pcm16_mono_16k_to_stereo_44100(pcm_bytes: bytes) -> bytes:
    """Convert little-endian 16 kHz mono PCM16 to 44.1 kHz stereo PCM16."""
    if len(pcm_bytes) % 2:
        raise ValueError("PCM16 data must contain complete 16-bit samples")
    if not pcm_bytes:
        return b""

    resampled_mono, _ = audioop.ratecv(
        pcm_bytes,
        2,
        1,
        16000,
        44100,
        None,
    )
    return audioop.tostereo(resampled_mono, 2, 1.0, 1.0)


def pcm16_to_wav(
    pcm_bytes: bytes,
    sample_rate: int = 16000,
    channels: int = 1,
) -> bytes:
    if sample_rate <= 0:
        raise ValueError("sample_rate must be positive")
    if channels <= 0:
        raise ValueError("channels must be positive")
    if len(pcm_bytes) % (2 * channels):
        raise ValueError("PCM16 data must contain complete audio frames")

    output = BytesIO()
    with wave.open(output, "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_bytes)
    return output.getvalue()
