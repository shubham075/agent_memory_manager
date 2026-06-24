"""
STT — Speech-to-Text using faster-whisper
==========================================
Two model tiers:
  tiny  → used for continuous wake word scanning (fast, low CPU)
  small → used for actual user query transcription (accurate)

Both run fully locally. No API key needed.
"""
import io
import tempfile
import threading
from pathlib import Path
from typing import Optional

import numpy as np
import sounddevice as sd

# Lazy-loaded models (initialized once, reused)
_wake_model = None
_query_model = None
_model_lock = threading.Lock()

SAMPLE_RATE = 16_000   # Whisper requires 16kHz mono audio


def _get_wake_model():
    global _wake_model
    if _wake_model is None:
        with _model_lock:
            if _wake_model is None:
                from faster_whisper import WhisperModel
                # tiny model: 75MB, fast enough for 2s chunks every loop
                _wake_model = WhisperModel("tiny", device="cpu", compute_type="int8")
    return _wake_model


def _get_query_model():
    global _query_model
    if _query_model is None:
        with _model_lock:
            if _query_model is None:
                from faster_whisper import WhisperModel
                # small model: 244MB, much better accuracy for real queries
                _query_model = WhisperModel("small", device="cpu", compute_type="int8")
    return _query_model


def record_chunk(duration: float = 2.0) -> np.ndarray:
    """Record a fixed-duration audio chunk. Used for wake word scanning."""
    audio = sd.rec(
        int(duration * SAMPLE_RATE),
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="float32",
    )
    sd.wait()
    return audio.flatten()


def record_until_silence(
    silence_threshold: float = 0.015,
    silence_duration: float = 1.5,
    max_duration: float = 30.0,
) -> np.ndarray:
    """
    Record audio until silence is detected (Voice Activity Detection).
    Used for capturing the actual user query after wake word activation.

    silence_threshold: RMS energy below this = silence
    silence_duration:  seconds of continuous silence to stop recording
    max_duration:      hard cap in seconds
    """
    chunk_size = int(SAMPLE_RATE * 0.1)   # 100ms chunks
    silence_chunks_needed = int(silence_duration / 0.1)
    max_chunks = int(max_duration / 0.1)

    frames: list[np.ndarray] = []
    silence_count = 0
    speech_started = False

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32") as stream:
        for _ in range(max_chunks):
            chunk, _ = stream.read(chunk_size)
            rms = float(np.sqrt(np.mean(chunk ** 2)))
            frames.append(chunk.flatten())

            if rms > silence_threshold:
                speech_started = True
                silence_count = 0
            elif speech_started:
                silence_count += 1
                if silence_count >= silence_chunks_needed:
                    break   # Silence detected → stop recording

    return np.concatenate(frames) if frames else np.zeros(SAMPLE_RATE)


def transcribe_wake(audio: np.ndarray) -> str:
    """Fast transcription with tiny model for wake word detection."""
    return _transcribe(audio, _get_wake_model())


def transcribe_query(audio: np.ndarray) -> str:
    """Accurate transcription with small model for user queries."""
    return _transcribe(audio, _get_query_model())


def _transcribe(audio: np.ndarray, model) -> str:
    """Core transcription — saves audio to temp WAV and runs Whisper."""
    import scipy.io.wavfile as wav

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        tmp_path = f.name

    try:
        # faster-whisper expects float32 audio at 16kHz
        wav.write(tmp_path, SAMPLE_RATE, audio.astype(np.float32))
        segments, _ = model.transcribe(
            tmp_path,
            language=None,        # Auto-detect (handles Hindi + English)
            beam_size=1,          # Faster, sufficient for voice commands
            vad_filter=True,      # Skip silent segments
        )
        return " ".join(seg.text.strip() for seg in segments).lower()
    finally:
        Path(tmp_path).unlink(missing_ok=True)
