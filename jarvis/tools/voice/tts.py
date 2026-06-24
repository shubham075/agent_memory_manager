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


def speak(text: str, lang: str | None = None) -> None:
    """
    Convert text to speech and play through speakers.
    Blocks until audio finishes playing.

    lang: "en" | "hi" | None (auto-detect from text content)
    """
    if not text.strip():
        return

    language = lang or detect_language(text)
    voice    = VOICES.get(language, VOICES["en"])
    tmp_path = None

    try:
        # Generate audio and save to temp MP3
        tmp_path = asyncio.run(_save_to_tempfile(text, voice))

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
    Interrupt current TTS playback.
    playsound3 is blocking, so interruption is only possible from another thread.
    This sets a flag — actual interruption requires playing thread to be daemonized.
    """
    # Future: use threading.Event for interruptible playback
    pass
