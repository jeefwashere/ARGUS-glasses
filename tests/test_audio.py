import io
import math
import struct
import wave

import pytest

from app.utils.audio import pcm16_mono_16k_to_stereo_44100, pcm16_to_wav


def make_mono_pcm(*, duration_seconds: float = 1.0) -> bytes:
    sample_count = int(16000 * duration_seconds)
    samples = (
        int(12000 * math.sin(2 * math.pi * 440 * index / 16000))
        for index in range(sample_count)
    )
    return b"".join(struct.pack("<h", sample) for sample in samples)


def test_bluetooth_conversion_preserves_duration():
    source_pcm = make_mono_pcm(duration_seconds=1.0)
    converted_pcm = pcm16_mono_16k_to_stereo_44100(source_pcm)

    source_duration = (len(source_pcm) // 2) / 16000
    converted_duration = (len(converted_pcm) // 4) / 44100

    assert converted_duration == pytest.approx(source_duration, abs=1 / 16000)


def test_bluetooth_conversion_duplicates_mono_into_stereo():
    converted_pcm = pcm16_mono_16k_to_stereo_44100(make_mono_pcm())
    stereo_frames = struct.iter_unpack("<hh", converted_pcm)

    assert all(left == right for left, right in stereo_frames)


def test_bluetooth_conversion_preserves_signed_little_endian_samples():
    source_pcm = struct.pack("<100h", *([-12345] * 100))
    converted_pcm = pcm16_mono_16k_to_stereo_44100(source_pcm)

    assert all(
        left == right == -12345
        for left, right in struct.iter_unpack("<hh", converted_pcm)
    )


def test_bluetooth_wav_has_correct_metadata_and_pcm():
    converted_pcm = pcm16_mono_16k_to_stereo_44100(make_mono_pcm())
    wav_bytes = pcm16_to_wav(converted_pcm, sample_rate=44100, channels=2)

    with wave.open(io.BytesIO(wav_bytes), "rb") as wav_file:
        assert wav_file.getframerate() == 44100
        assert wav_file.getnchannels() == 2
        assert wav_file.getsampwidth() == 2
        assert wav_file.getcomptype() == "NONE"
        assert wav_file.readframes(wav_file.getnframes()) == converted_pcm

    assert struct.unpack_from("<I", wav_bytes, 4)[0] == len(wav_bytes) - 8
    assert struct.unpack_from("<I", wav_bytes, 28)[0] == 44100 * 2 * 2
    assert struct.unpack_from("<H", wav_bytes, 32)[0] == 2 * 2
    assert struct.unpack_from("<I", wav_bytes, 40)[0] == len(converted_pcm)


def test_empty_pcm_converts_to_empty_pcm_and_valid_empty_wav():
    converted_pcm = pcm16_mono_16k_to_stereo_44100(b"")
    wav_bytes = pcm16_to_wav(converted_pcm, sample_rate=44100, channels=2)

    assert converted_pcm == b""
    with wave.open(io.BytesIO(wav_bytes), "rb") as wav_file:
        assert wav_file.getframerate() == 44100
        assert wav_file.getnchannels() == 2
        assert wav_file.getsampwidth() == 2
        assert wav_file.getnframes() == 0


def test_incomplete_pcm_sample_is_rejected():
    with pytest.raises(ValueError, match="complete 16-bit samples"):
        pcm16_mono_16k_to_stereo_44100(b"\x00")


def test_incomplete_stereo_frame_is_rejected_by_wav_wrapper():
    with pytest.raises(ValueError, match="complete audio frames"):
        pcm16_to_wav(b"\x00\x00", sample_rate=44100, channels=2)
