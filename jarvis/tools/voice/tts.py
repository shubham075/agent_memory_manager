"""
TTS — Text-to-Speech (Multi-language)
=======================================
Language routing:
  English   → edge-tts  en-GB-RyanNeural   (British male, movie JARVIS style)
  Hindi     → edge-tts  hi-IN-MadhurNeural (Devanagari script detection)
  Hinglish  → HuggingFace Aaryan39/hinglish-tts-3b-ft-synthetic
              (Roman-script Hindi mixed with English — detected by keyword list)

Language detection priority:
  1. Devanagari Unicode chars → "hi"
  2. Hinglish Roman keyword match → "hinglish"
  3. Default → "en"

Playback (edge-tts path):
  edge-tts saves MP3 to temp file → playsound3 plays via Windows MCI.

Playback (Hinglish model path):
  transformers pipeline → numpy audio array → sounddevice.play()
  Falls back to edge-tts English if model unavailable or inference fails.

Why playsound3 instead of pygame?
  pygame 2.6.x fails to compile on Python 3.14 (distutils.msvccompiler removed).
  playsound3 uses Windows built-in MCI — no compilation, no SDL, no extra deps.
"""
import asyncio
import tempfile
import threading
from pathlib import Path
from typing import Literal

import edge_tts

# ── Voice config (edge-tts) ────────────────────────────────────────────────────
VOICES = {
    "en": "en-GB-RyanNeural",
    "hi": "hi-IN-MadhurNeural",
}

# ── Hinglish TTS model ─────────────────────────────────────────────────────────
HINGLISH_MODEL_ID = "Aaryan39/hinglish-tts-3b-ft-synthetic"
_hinglish_pipe = None
_hinglish_pipe_lock = threading.Lock()

# Common Hinglish words in Roman script (used for detection)
# Covers the most frequent Hindi words written in English letters
_HINGLISH_MARKERS: set[str] = {
    "kya", "hai", "hain", "main", "mein", "mujhe", "aap", "tum",
    "hum", "yeh", "woh", "kar", "karo", "raha", "rahi", "ho",
    "tha", "thi", "the", "nahi", "nahin", "kuch", "bahut", "accha",
    "theek", "bhai", "yaar", "bolo", "batao", "dekho", "suno",
    "haan", "nah", "kal", "abhi", "phir", "aur", "lekin", "toh",
    "kyun", "kaise", "kahaan", "kab", "kitna", "zaroor", "bilkul",
    "samajh", "pata", "matlab", "lagta", "chahiye", "jarvis",
}


# ── Language detection ─────────────────────────────────────────────────────────

def detect_language(text: str) -> Literal["en", "hi", "hinglish"]:
    """
    Detect the language of the text.

    Priority:
      1. Any Devanagari character → "hi"  (pure Hindi script)
      2. Roman-script Hinglish keywords found → "hinglish"
      3. Default → "en"
    """
    # Check Devanagari block U+0900–U+097F
    if any("\u0900" <= ch <= "\u097F" for ch in text):
        return "hi"
    # Check Roman Hinglish by word-level marker matching
    words = set(text.lower().split())
    if words & _HINGLISH_MARKERS:
        return "hinglish"
    return "en"


# ── Hinglish TTS pipeline (lazy singleton) ─────────────────────────────────────

def _get_hinglish_pipe():
    """Lazy-load the Hinglish TTS pipeline. Thread-safe singleton."""
    global _hinglish_pipe
    if _hinglish_pipe is None:
        with _hinglish_pipe_lock:
            if _hinglish_pipe is None:
                from transformers import pipeline as hf_pipeline
                print(f"[voice/tts] Loading Hinglish TTS model '{HINGLISH_MODEL_ID}'...")
                print("[voice/tts] First load may take a moment — model cached after first run.")
                _hinglish_pipe = hf_pipeline(
                    "text-to-speech",
                    model=HINGLISH_MODEL_ID,
                )
                print("[voice/tts] Hinglish TTS model ready.")
    return _hinglish_pipe


def _speak_hinglish(text: str) -> None:
    """
    Speak Hinglish text using Aaryan39/hinglish-tts-3b-ft-synthetic.
    Plays audio directly via sounddevice (no temp file needed).
    Falls back to edge-tts English voice if the model fails.
    """
    import numpy as np
    import sounddevice as sd

    try:
        pipe = _get_hinglish_pipe()
        result = pipe(text)

        audio = np.array(result["audio"])
        if audio.ndim > 1:
            audio = audio.squeeze()  # (1, N) → (N,)

        sd.play(audio.astype(np.float32), result["sampling_rate"])
        sd.wait()

    except Exception as e:
        print(f"[voice/tts] Hinglish model error (falling back to edge-tts): {e}")
        # Fallback: speak with English neural voice
        _speak_edge_tts(text, VOICES["en"])


# ── edge-tts helpers ──────────────────────────────────────────────────────────

async def _save_to_tempfile(text: str, voice: str) -> str:
    """Generate TTS audio via edge-tts and save to a temp MP3. Returns file path."""
    communicate = edge_tts.Communicate(text, voice)
    tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
    tmp_path = tmp.name
    tmp.close()
    await communicate.save(tmp_path)
    return tmp_path


def _speak_edge_tts(text: str, voice: str) -> None:
    """Play text via edge-tts + playsound3. Used for 'en' and 'hi'."""
    tmp_path = None
    try:
        loop = asyncio.new_event_loop()
        try:
            tmp_path = loop.run_until_complete(_save_to_tempfile(text, voice))
        finally:
            loop.close()

        from playsound3 import playsound
        playsound(tmp_path, block=True)

    except Exception as e:
        print(f"[voice/tts] edge-tts playback error: {e}")
    finally:
        if tmp_path:
            Path(tmp_path).unlink(missing_ok=True)


# ── Playback control ─────────────────────────────────────────────────────────
_stop_event: threading.Event = threading.Event()


def speak(text: str, lang: str | None = None) -> None:
    """
    Convert text to speech and play through speakers.

    lang: "en" | "hi" | "hinglish" | None (auto-detect)

    Routing:
      "hi"       → edge-tts hi-IN-MadhurNeural
      "hinglish" → Aaryan39/hinglish-tts-3b-ft-synthetic (HuggingFace)
      "en"       → edge-tts en-GB-RyanNeural
    """
    if not text.strip():
        return
    if _stop_event.is_set():
        _stop_event.clear()  # reset for next call
        return

    language = lang or detect_language(text)

    # ── Route to correct TTS engine ───────────────────────────────────────────
    if language == "hinglish":
        _speak_hinglish(text)
    else:
        voice = VOICES.get(language, VOICES["en"])
        _speak_edge_tts(text, voice)


def stop_speaking() -> None:
    """
    Signal that the current TTS playback should be interrupted.
    Sets a threading.Event that speak() checks before starting.

    Note: playsound3 / sounddevice are blocking — an in-progress clip cannot
    be interrupted mid-sentence. This prevents the NEXT queued speak() call.
    Full mid-sentence interruption requires a daemon playback thread (future work).
    """
    _stop_event.set()
