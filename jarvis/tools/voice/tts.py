"""
TTS — Text-to-Speech using edge-tts
=====================================
Voices:
  English → en-GB-RyanNeural   (British male, closest to movie JARVIS)
  Hindi   → hi-IN-MadhurNeural (male Hindi neural voice)

Language detection: Devanagari Unicode range (no extra library).
Playback: edge-tts saves MP3 to temp file → playsound3 plays it via Windows MCI.

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

# ── Voice config ──────────────────────────────────────────────────────────────
VOICES = {
    "en": "en-GB-RyanNeural",
    "hi": "hi-IN-MadhurNeural",
}


def detect_language(text: str) -> Literal["en", "hi"]:
    """
    Detect if text is Hindi (Devanagari script) or English.
    Checks Unicode Devanagari block U+0900–U+097F.
    """
    if any("\u0900" <= ch <= "\u097F" for ch in text):
        return "hi"
    return "en"


async def _save_to_tempfile(text: str, voice: str) -> str:
    """Generate TTS audio and save to a temp MP3 file. Returns file path."""
    communicate = edge_tts.Communicate(text, voice)
    tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
    tmp_path = tmp.name
    tmp.close()
    await communicate.save(tmp_path)
    return tmp_path


# ── Playback control ─────────────────────────────────────────────────────────
_stop_event: threading.Event = threading.Event()


def speak(text: str, lang: str | None = None) -> None:
    """
    Convert text to speech and play through speakers.
    Blocks until audio finishes playing.

    lang: "en" | "hi" | None (auto-detect from text content)

    Uses a fresh event loop per call to avoid RuntimeError when speak() is
    called from inside an already-running asyncio event loop (e.g. FastAPI).
    """
    if not text.strip():
        return
    if _stop_event.is_set():
        _stop_event.clear()   # reset for next call
        return

    language = lang or detect_language(text)
    voice    = VOICES.get(language, VOICES["en"])
    tmp_path = None

    try:
        # Create a fresh event loop — avoids RuntimeError if one is already running
        loop = asyncio.new_event_loop()
        try:
            tmp_path = loop.run_until_complete(_save_to_tempfile(text, voice))
        finally:
            loop.close()

        # Play MP3 using playsound3 (uses Windows MCI — no compilation needed)
        from playsound3 import playsound
        playsound(tmp_path, block=True)   # block=True waits for playback to finish

    except Exception as e:
        # TTS failure should never crash JARVIS — degrade gracefully to text-only
        print(f"[voice/tts] Playback error: {e}")
    finally:
        # Clean up temp file
        if tmp_path:
            Path(tmp_path).unlink(missing_ok=True)


def stop_speaking() -> None:
    """
    Signal that the current TTS playback should be interrupted.
    Sets a threading.Event that speak() checks before starting playback.

    Note: playsound3 is blocking so an in-progress clip cannot be interrupted
    mid-sentence. This prevents the NEXT queued speak() call from playing,
    which effectively mutes JARVIS for the current turn.
    Full mid-sentence interruption requires running playsound in a daemon thread
    (planned for a future voice upgrade).
    """
    _stop_event.set()
