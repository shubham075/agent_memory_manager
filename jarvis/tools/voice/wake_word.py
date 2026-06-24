"""
Wake Word Detector — Background Daemon Thread
=============================================
Continuously records 2-second audio chunks and checks for "JARVIS wake up".

CPU guard: If psutil reports CPU > CPU_THRESHOLD%, the loop sleeps 30s
           before trying again. This prevents JARVIS from slowing your system
           when it's under heavy load (compiling, training models, etc.).

When wake word detected:
  1. Speaks "Yes, sir?" via TTS
  2. Records the full user query (until silence)
  3. Transcribes with small Whisper model
  4. Puts transcribed text into voice_query_queue for the REPL to pick up
"""
import queue
import threading
import time

import psutil

from tools.voice.stt import record_chunk, record_until_silence, transcribe_wake, transcribe_query
from tools.voice.tts import speak

# ── Config ────────────────────────────────────────────────────────────────────
WAKE_PHRASES = [
    "jarvis wake up",
    "jarvis, wake up",
    "hey jarvis",           # fallback alias
    "jarvis wakeup",        # common mis-transcription
]
CPU_THRESHOLD   = 75    # % CPU — pause listening above this
CPU_SLEEP_SEC   = 30    # seconds to sleep when CPU is high
CHUNK_DURATION  = 2.0   # seconds per wake-word scan chunk


class WakeWordDetector:
    """
    Daemon thread that monitors the microphone for the JARVIS wake word.
    Put detected queries into `voice_query_queue` for the REPL to consume.
    """

    def __init__(self, voice_query_queue: queue.Queue) -> None:
        self._queue   = voice_query_queue
        self._stop    = threading.Event()
        self._thread  = threading.Thread(target=self._run, daemon=True, name="jarvis-wake")

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        """Main detection loop — runs in background daemon thread."""
        while not self._stop.is_set():
            # ── CPU guard ─────────────────────────────────────────────────────
            cpu = psutil.cpu_percent(interval=0.5)
            if cpu > CPU_THRESHOLD:
                time.sleep(CPU_SLEEP_SEC)
                continue

            try:
                # Record 2-second chunk and check for wake word
                audio = record_chunk(CHUNK_DURATION)
                text  = transcribe_wake(audio)

                if _is_wake_word(text):
                    self._handle_activation()

            except Exception as e:
                # Never crash the daemon — log and continue
                print(f"\n[wake] Error in detection loop: {e}")
                time.sleep(1)

    def _handle_activation(self) -> None:
        """Called when wake word is confirmed."""
        # Acknowledge activation
        speak("Yes, sir?", lang="en")

        try:
            # Record user's actual query (VAD-based silence detection)
            audio = record_until_silence(
                silence_threshold=0.015,
                silence_duration=1.5,
                max_duration=30.0,
            )
            query_text = transcribe_query(audio).strip()

            if query_text and len(query_text) > 2:
                self._queue.put(query_text)
            else:
                speak("I didn't catch that, sir. Please try again.", lang="en")

        except Exception as e:
            print(f"\n[wake] Error recording query: {e}")
            speak("There was an error processing your request, sir.", lang="en")


def _is_wake_word(text: str) -> bool:
    """Check if transcribed text contains any known wake phrase."""
    text_lower = text.lower().strip()
    return any(phrase in text_lower for phrase in WAKE_PHRASES)
