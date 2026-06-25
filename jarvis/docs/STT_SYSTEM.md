# JARVIS — Speech-to-Text (STT) System

> **File:** `jarvis/tools/voice/stt.py`  
> **Library:** `faster-whisper` (OpenAI Whisper, CTranslate2 backend)  
> **Audio Input:** `sounddevice` (PortAudio wrapper)  
> **Mode:** 100% local — no API key, no cloud, no internet required

---

## Overview

JARVIS uses **faster-whisper** — a reimplementation of OpenAI's Whisper model using
[CTranslate2](https://github.com/OpenNMT/CTranslate2), which is 4× faster than the original
Whisper and uses 50-70% less memory via INT8 quantization.

Two separate Whisper model sizes are loaded depending on the task:

| Model | Size | Use Case | Accuracy | Speed |
|-------|------|----------|----------|-------|
| `tiny` | ~75 MB | Wake word scanning (every 2s loop) | Low | Very fast |
| `small` | ~244 MB | Actual user query transcription | High | Moderate |

---

## Architecture Diagram

```
Microphone (sounddevice / PortAudio)
         │
         ▼
  ┌──────────────────────────────────────┐
  │  WakeWordDetector (daemon thread)     │
  │                                      │
  │  loop every 2s:                      │
  │    record_chunk(2.0s)                │
  │         │                            │
  │         ▼                            │
  │    transcribe_wake()                 │  ← tiny model (fast, low CPU)
  │         │                            │
  │    _is_wake_word(text)?              │
  │         │                            │
  │    YES ─┘                            │
  │         │                            │
  │    speak("Yes, sir?") [TTS]          │
  │         │                            │
  │    record_until_silence()            │  ← VAD-based recording
  │         │                            │
  │    transcribe_query()                │  ← small model (accurate)
  │         │                            │
  │    voice_query_queue.put(text)       │
  └──────────────────────────────────────┘
         │
         ▼
  REPL loop picks up from queue
  → LangGraph invoked with voice query
  → Response spoken back via TTS
```

---

## Component 1: Audio Recording (`record_chunk`)

```python
def record_chunk(duration: float = 2.0) -> np.ndarray:
```

**How it works:**
- Uses `sounddevice.rec()` to capture a **fixed-duration** audio chunk
- Audio format: `float32`, 1 channel (mono), 16,000 Hz sample rate
- `sd.wait()` blocks until the chunk is fully recorded
- Returns a flat 1D NumPy array of audio samples

**Why 16 kHz?**  
Whisper was trained on 16kHz mono audio. Any other sample rate would cause degraded
transcription quality or errors.

```
2 seconds × 16,000 samples/sec = 32,000 float32 samples ≈ 125 KB per chunk
```

This chunk is used only for **wake word scanning** — it's cheap and fast.

---

## Component 2: VAD Recording (`record_until_silence`)

```python
def record_until_silence(
    silence_threshold: float = 0.015,
    silence_duration: float = 1.5,
    max_duration: float = 30.0,
) -> np.ndarray:
```

**How it works:**  
Used AFTER the wake word is detected to capture the actual user query.

Instead of recording a fixed duration, it uses **Voice Activity Detection (VAD)**:

1. Opens a live audio `InputStream` via `sounddevice`
2. Reads audio in **100ms chunks** continuously
3. For each chunk, computes **RMS energy** (Root Mean Square — a measure of loudness):
   ```python
   rms = float(np.sqrt(np.mean(chunk ** 2)))
   ```
4. If `rms > silence_threshold` → speech detected, reset silence counter
5. If silence counter exceeds `silence_duration / 0.1` chunks → user stopped talking → stop recording
6. Hard cap: stops after `max_duration` seconds regardless

**Parameters:**

| Parameter | Default | Meaning |
|-----------|---------|---------|
| `silence_threshold` | `0.015` | RMS below this = silence |
| `silence_duration` | `1.5s` | 1.5 seconds of silence = end of query |
| `max_duration` | `30s` | Hard cap to prevent infinite recording |

**Example flow:**
```
[silence...] → speech started → "What is the weather today?" → [1.5s silence] → STOP
```

---

## Component 3: Transcription Pipeline

### Step 1 — Save to Temp WAV

```python
wav.write(tmp_path, SAMPLE_RATE, audio.astype(np.float32))
```

faster-whisper does NOT accept raw NumPy arrays directly. The audio must be saved
as a `.wav` file to a temp location, then passed to the model.

### Step 2 — Run Whisper Inference

```python
segments, _ = model.transcribe(
    tmp_path,
    language=None,    # auto-detect (handles Hindi + English)
    beam_size=1,      # greedy decoding — faster, sufficient for voice commands
    vad_filter=True,  # skip silent audio segments
)
```

**Key settings:**

| Setting | Value | Why |
|---------|-------|-----|
| `language=None` | Auto | Handles Hindi, English, Hinglish automatically |
| `beam_size=1` | Greedy | 3× faster than beam_size=5, acceptable quality for voice |
| `vad_filter=True` | ON | Whisper's built-in Silero VAD — skips silent parts |
| `compute_type` | `int8` | INT8 quantization — 50% memory reduction, ~same quality |

### Step 3 — Join Segments

```python
return " ".join(seg.text.strip() for seg in segments).lower()
```

Whisper returns multiple `TranscriptionSegment` objects (one per sentence/phrase).
These are joined into a single lowercase string.

---

## Component 4: Dual Model Strategy

```python
# Lazy singleton pattern — model loads once, reused for all calls
_wake_model  = None   # tiny  → wake word detection
_query_model = None   # small → query transcription
_model_lock  = threading.Lock()  # thread-safe initialization
```

### Why two models?

| Concern | Wake Word | Query |
|---------|-----------|-------|
| Called every | 2 seconds | Once per activation |
| Text needed | "jarvis wake up" only | Full sentence accuracy |
| Latency budget | < 500ms | 1-3 seconds OK |
| Model | tiny (39M params) | small (244M params) |
| Accuracy | Low, but enough | High |

Using `small` for the 2-second loop would cause 100% CPU usage continuously.
`tiny` is fast enough to detect "jarvis wake up" reliably.

---

## Component 5: Wake Word Detection Logic

**File:** `jarvis/tools/voice/wake_word.py`

```python
WAKE_PHRASES = [
    "jarvis wake up",
    "jarvis, wake up",
    "hey jarvis",        # fallback alias
    "jarvis wakeup",     # common mis-transcription by Whisper
]

def _is_wake_word(text: str) -> bool:
    text_lower = text.lower().strip()
    return any(phrase in text_lower for phrase in WAKE_PHRASES)
```

Simple substring match — not regex. Works because Whisper output is clean lowercase text.

### CPU Guard

```python
cpu = psutil.cpu_percent(interval=0.5)
if cpu > CPU_THRESHOLD:   # 75%
    time.sleep(CPU_SLEEP_SEC)  # 30 seconds
    continue
```

If system CPU > 75%, the wake word loop sleeps 30s before resuming.
This prevents JARVIS from interfering with heavy tasks (model training, compiling, etc.).

---

## Full Voice Flow (End-to-End)

```
1. python main.py --voice
         │
         ▼
2. VoiceManager() created
   WakeWordDetector daemon thread started (background)
         │
         ▼
3. [REPL loop] — user types OR voice_queue has data
         │
   ┌─────┴──────────────────────────────────┐
   │        Background daemon thread         │
   │                                         │
   │  record_chunk(2s)                       │
   │  → transcribe_wake() [tiny model]       │
   │  → "jarvis wake up" detected!           │
   │  → TTS: speak("Yes, sir?")              │
   │  → record_until_silence() [VAD]         │
   │  → transcribe_query() [small model]     │
   │  → voice_query_queue.put("query text")  │
   └─────────────────────────────────────────┘
         │
         ▼ (REPL picks up from queue)
4. voice_manager.get_pending_query() → "query text"
         │
         ▼
5. graph.invoke({messages: [HumanMessage("query text")]})
         │
         ▼
6. [context_manager_node] → Tier 1 + Tier 2 + Tier 3 context assembled
   [chatbot_node] → Groq LLaMA 3.3 70B generates response
   [memory_update_node] → episode stored in Qdrant
         │
         ▼
7. voice_manager.speak_response(ai_response)
   → First 3 sentences spoken via edge-tts (en-GB-RyanNeural)
   → Full response shown on screen
```

---

## Dependencies

```
faster-whisper     # Whisper inference (CTranslate2 backend)
sounddevice        # PortAudio microphone access
scipy              # scipy.io.wavfile — save audio to WAV
numpy              # Audio array manipulation
psutil             # CPU usage monitoring
```

Install (if not present):
```powershell
uv add faster-whisper sounddevice scipy psutil
```

---

## Limitations & Known Issues

| Issue | Status | Notes |
|-------|--------|-------|
| Tiny model misses "jarvis wake up" in noisy environments | Known | Increase `CHUNK_DURATION` to 3s or switch to `base` model |
| Whisper doesn't stream — saves full clip before transcribing | By design | 30s max clip prevents memory issues |
| `stop_speaking()` in tts.py is a no-op | Bug (P3) | Interrupting TTS mid-sentence not yet implemented |
| VAD threshold `0.015` may cut off soft-spoken users | Tunable | Adjust `silence_threshold` in `wake_word.py` |
| Only Hindi (Devanagari script) detected; Hinglish treated as English | Limitation | Whisper handles Hinglish in transcription but TTS uses English voice |
| Whisper models download on first run (~75MB + ~244MB) | First-run UX | Cached in `~/.cache/huggingface/hub/` after first download |

---

## Configuration Tuning

To adjust wake word sensitivity, edit `wake_word.py`:

```python
CPU_THRESHOLD   = 75     # Lower to give more headroom (e.g. 60)
CPU_SLEEP_SEC   = 30     # How long to pause when CPU is high
CHUNK_DURATION  = 2.0    # Increase to 3.0 for noisier environments
```

To adjust query recording sensitivity, edit `stt.py` calls in `wake_word.py`:

```python
audio = record_until_silence(
    silence_threshold=0.015,   # Lower = more sensitive (catches quiet speech)
    silence_duration=1.5,      # Lower = stops sooner (snappier responses)
    max_duration=30.0,         # Increase for long monologues
)
```

---

## Why faster-whisper over other options?

| Option | Pros | Cons |
|--------|------|------|
| **faster-whisper** ✅ | Local, free, multilingual, INT8 | First-run download, CPU-only on no-GPU systems |
| Google Speech-to-Text | Very fast, accurate | API key, costs money, requires internet |
| Vosk | Very lightweight (~50MB) | English-only quality, no Hindi |
| SpeechRecognition (CMU Sphinx) | Offline | Very poor accuracy, outdated |
| Deepgram / AssemblyAI | Streaming, very accurate | Cloud-only, costs money |

**Bottom line:** faster-whisper is the best local, free, multilingual option for a 
personal assistant running on commodity hardware.
