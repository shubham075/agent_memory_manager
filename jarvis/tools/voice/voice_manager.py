"""
VoiceManager — Orchestrates the full voice pipeline
====================================================
- Starts/stops the wake word detector daemon thread
- Provides process_voice_turn(): runs a voice query through the LangGraph graph
- Bridges the voice_query_queue to the REPL loop
"""
import queue

from tools.voice.tts import speak, detect_language
from tools.voice.wake_word import WakeWordDetector

# Shared queue: wake_word thread → REPL loop
voice_query_queue: queue.Queue = queue.Queue()


class VoiceManager:
    def __init__(self) -> None:
        self._detector = WakeWordDetector(voice_query_queue)
        self._active   = False

    def start_listening(self) -> None:
        """Start background wake word detection daemon."""
        self._detector.start()
        self._active = True

    def stop_listening(self) -> None:
        """Stop the background daemon cleanly."""
        self._detector.stop()
        self._active = False

    @property
    def is_active(self) -> bool:
        return self._active

    def has_pending_query(self) -> bool:
        """Non-blocking check if a voice query is waiting."""
        return not voice_query_queue.empty()

    def get_pending_query(self) -> str | None:
        """Get next voice query from queue (non-blocking)."""
        try:
            return voice_query_queue.get_nowait()
        except queue.Empty:
            return None

    def speak_response(self, text: str) -> None:
        """
        Speak the JARVIS response aloud.
        For long responses, speaks the first 3 sentences to avoid
        very long TTS playback that would block the next interaction.
        """
        if not text:
            return
        # Limit TTS to first 3 sentences for natural flow
        sentences = _split_sentences(text)
        tts_text  = " ".join(sentences[:3])
        if len(sentences) > 3:
            tts_text += "... [see full response on screen]"
        speak(tts_text)


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences for TTS truncation."""
    import re
    # Split on . ! ? while keeping the delimiter
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p for p in parts if p.strip()]
