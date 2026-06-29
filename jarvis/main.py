"""
JARVIS Entry Point
===================
Usage:
    python main.py                  # Text mode  — keyboard input only
    python main.py --voice          # Voice mode — wake word + STT only (no keyboard)
    python main.py --setup          # Run profile setup wizard (first time)
    python main.py --session <id>   # Resume a previous session by ID

Modes are STRICT — voice mode has zero keyboard input, text mode has zero voice.
In voice mode: say 'JARVIS wake up' to activate, press Ctrl+C to exit.
"""
import sys
import os

# Add jarvis/ to path so all imports resolve correctly
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.memory.semantic import init_semantic_db, read_facts
from graph.jarvis_graph import build_graph
from cli.repl import run_repl


def main() -> None:
    args = sys.argv[1:]

    # ── Setup wizard mode ─────────────────────────────────────────────────────
    if "--setup" in args:
        from setup_wizard import run_wizard
        run_wizard()
        return

    # ── Resume session mode ───────────────────────────────────────────────────
    session_id = None
    if "--session" in args:
        idx = args.index("--session")
        if idx + 1 < len(args):
            session_id = args[idx + 1]

    # ── First-run check ───────────────────────────────────────────────────────
    init_semantic_db()
    if not read_facts():
        print("\n[JARVIS] No user profile found.")
        print("Run: python main.py --setup   to set up your profile first.\n")
        answer = input("Start anyway without a profile? [y/N]: ").strip().lower()
        if answer != "y":
            sys.exit(0)

    # ── Voice mode setup ──────────────────────────────────────────────────────
    voice_manager = None
    if "--voice" in args:
        try:
            from tools.voice.voice_manager import VoiceManager
            voice_manager = VoiceManager()
            voice_manager.start_listening()
            print("[JARVIS] Voice mode started. Say 'JARVIS wake up' to activate.")
        except ImportError as e:
            print(f"[JARVIS] Voice dependencies missing: {e}")
            print("[JARVIS] Run: uv add faster-whisper edge-tts sounddevice playsound3 psutil scipy")
            print("[JARVIS] NOTE: Use playsound3 NOT pygame — pygame fails on Python 3.14")
            print("[JARVIS] Starting in text-only mode.")

    # ── Build graph and start REPL ────────────────────────────────────────────
    # build_graph() is a context manager — keeps SQLite connection open for session
    with build_graph() as graph:
        run_repl(graph, thread_id=session_id, voice_manager=voice_manager)


if __name__ == "__main__":
    main()
