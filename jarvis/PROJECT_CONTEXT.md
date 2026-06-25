# JARVIS Project Context — Complete Resume Document
> **Purpose:** Paste this file to any AI assistant on any machine to instantly resume work without re-analysis.  
> **Last updated:** 2026-06-25 (Post bug-fix session)  
> **Status:** ✅ Fully working — voice mode confirmed operational

---

## What Is This Project

A personal AI assistant (JARVIS) built with LangGraph + Groq LLaMA 3.3 70B.  
Uses a 3-tier memory architecture for persistent, context-aware conversations.  
Supports both **text mode** (default) and **voice mode** (wake word + STT + TTS).

**Location (current machine):** `d:\MODELS\MEMORY_MANAGEMENT\jarvis\`  
**Git repo:** `d:\MODELS\MEMORY_MANAGEMENT` (root of the git repo)  
**Run:**
```powershell
cd d:\MODELS\MEMORY_MANAGEMENT\jarvis
.\.venv\Scripts\activate        # ALWAYS use .venv — NOT the old "jarvis" venv
python main.py                  # text mode
python main.py --voice          # voice mode (wake word: "JARVIS wake up")
python main.py --setup          # first-run profile setup
python main.py --session <uuid> # resume a specific session
```

---

## Tech Stack

| Component | Choice | Version (confirmed) |
|-----------|--------|---------------------|
| LLM | Groq LLaMA 3.3 70B | `llama-3.3-70b-versatile` |
| LLM swap path | Set `LLM_PROVIDER=openai` in `.env` | Built-in factory in `core/nodes/chatbot.py` |
| Orchestration | LangGraph | `langgraph==1.2.6` |
| Tier 1 Memory | SQLite (`jarvis_memory.db`) | Permanent user facts |
| Tier 2 Memory | Qdrant local + sentence-transformers | Real RAG, no server needed |
| Tier 2 Embeddings | `all-MiniLM-L6-v2` (384-dim) | `sentence-transformers==5.6.0` |
| Tier 3 Memory | LangGraph SqliteSaver (`jarvis_checkpoints.db`) | Cross-session chat persistence |
| Token counting | `tiktoken` cl100k_base | Approximation for LLaMA |
| CLI | `rich` + `pyfiglet` | Beautiful REPL + token budget display |
| STT | `faster-whisper==1.2.1` | Local Whisper (tiny=wake word, small=query) |
| TTS | `edge-tts==7.2.8` | Microsoft Neural Voices (en-GB-RyanNeural) |
| Audio input | `sounddevice==0.5.5` | PortAudio microphone capture |
| Audio output | `playsound3==3.3.1` | Windows MCI playback (NOT pygame — fails Python 3.14) |
| Wake word | `psutil==7.2.2` + `faster-whisper` | CPU-guarded daemon thread |
| Package manager | `uv` | Manages `.venv` — always use `.venv`, never the old `jarvis` venv |
| Python | 3.14.2 (CPython) | Confirmed working |

---

## ⚠️ Critical: Virtual Environment

```powershell
# CORRECT — uv-managed:
.\.venv\Scripts\activate

# WRONG — old legacy venv (missing voice packages):
.\jarvis\Scripts\activate   ← DO NOT USE
```

`uv sync` and `uv add` ALWAYS install into `.venv`. Running python from the `jarvis`
venv will cause `ModuleNotFoundError` for all recently added packages (edge_tts, faster_whisper, etc.).

---

## Project File Structure

```
d:\MODELS\MEMORY_MANAGEMENT\
├── .env                           # GROQ_API_KEY (lives here on current machine)
├── .git/
├── jarvis/                        # ← Main project (cd here to run)
│   ├── main.py                    # Entry point. Flags: --setup, --session <id>, --voice
│   ├── setup_wizard.py            # First-run profile setup (populates Tier 1)
│   ├── pyproject.toml             # uv dependencies (all deps including voice)
│   ├── requirements.txt           # pip-compatible alternative (includes voice section)
│   ├── .env.example               # Copy to .env, add GROQ_API_KEY
│   ├── .venv/                     # ← uv virtual environment (use this one)
│   ├── data/
│   │   ├── jarvis_memory.db       # SQLite: Tier 1 user facts
│   │   ├── jarvis_checkpoints.db  # SQLite: LangGraph session state
│   │   └── qdrant_storage/        # Qdrant: Tier 2 episode vectors
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py              # All constants, paths, token budgets, dotenv fallback chain
│   │   ├── state.py               # JarvisState TypedDict
│   │   ├── tokenizer.py           # count_tokens(), count_message_tokens()
│   │   ├── exceptions.py          # ContextBudgetError, MemoryWriteError, EpisodicStoreError
│   │   ├── memory/
│   │   │   ├── __init__.py
│   │   │   ├── semantic.py        # Tier 1: SQLite read/write (facts_as_text, write_fact)
│   │   │   └── episodic.py        # Tier 2: Qdrant RAG (store_episode, retrieve_episodes)
│   │   └── nodes/
│   │       ├── __init__.py
│   │       ├── context_manager.py # Node 1: Token budgeting + rollover logic
│   │       ├── chatbot.py         # Node 2: LLM call (Groq/OpenAI factory + retry)
│   │       └── memory_updater.py  # Node 3: Regex fact extraction + episode storage
│   ├── graph/
│   │   ├── __init__.py
│   │   └── jarvis_graph.py        # LangGraph definition + SqliteSaver context manager
│   ├── cli/
│   │   ├── __init__.py
│   │   └── repl.py                # Rich REPL, /memory /episodes /budget /help commands
│   ├── tools/
│   │   ├── __init__.py
│   │   └── voice/
│   │       ├── __init__.py
│   │       ├── stt.py             # STT: faster-whisper, dual model (tiny/small), VAD recording
│   │       ├── tts.py             # TTS: edge-tts, playsound3, threading.Event stop control
│   │       ├── wake_word.py       # Wake word daemon: CPU-guarded, "jarvis wake up" detection
│   │       └── voice_manager.py   # Orchestrator: bridges wake_word → REPL via queue
│   └── docs/
│       └── STT_SYSTEM.md          # Full STT architecture documentation
```

---

## 3-Tier Memory Architecture

```
User Message (text or voice)
     │
     ▼
[context_manager_node]
     ├── Tier 1: read SQLite facts → inject into system prompt (1,600t budget)
     ├── Tier 2: embed query → Qdrant client.count() check → query_points() → MMR filter → inject (3,200t budget)
     │          Flex-space: unused RAG tokens roll over to Tier 3 budget
     └── Tier 3: trim chat history to (1,600t + rollover) budget [O(n) algorithm]
     │
     ▼
[chatbot_node] → Groq LLM call (max_tokens=1600 output, separate from input)
                 Retry: up to 3 attempts, exponential backoff (1s → 2s → 4s)
     │
     ▼
[memory_update_node]
     ├── Guard: skip if AI response is empty (prevents Qdrant pollution)
     ├── Tier 1 write: regex extract new facts from user message → SQLite
     └── Tier 2 write: store Q+A summary as episode in Qdrant
```

### Token Budget (8,000 total input tokens)
| Slot | Tokens | % |
|------|--------|---|
| System Prompt + Facts (Tier 1) | 1,600 | 20% |
| RAG Episodes (Tier 2) | 3,200 | 40% |
| Chat History (Tier 3) | 1,600 | 20% |
| Flex-Space (rolls to Tier 3) | 1,600 | 20% |
| Output (`max_tokens` on API) | 1,600 | separate |

**Important:** RAG tokens are embedded inside `system_tokens` via `_SYSTEM_TEMPLATE`.  
`total_tokens = system_tokens + history_tokens` (NOT + rag_used — that was a double-count bug, now fixed).

---

## LangGraph Graph Topology

```
START → context_manager_node → chatbot_node → memory_update_node → END
```

- **Checkpointer:** `SqliteSaver(conn)` used as context manager in `build_graph()`
- **Session resume:** `python main.py --session <uuid>` (uuid printed at startup)
- **State:** `JarvisState` TypedDict with fields:
  - `messages` — Annotated[list[AnyMessage], operator.add] (LangGraph appends)
  - `user_facts` — dict (in-memory cache per turn)
  - `rag_chunks` — list[dict] (retrieved this turn)
  - `budgeted_messages` — list[AnyMessage] (LLM-ready after trimming)
  - `budget_report` — dict (token usage, printed after each response)
  - `llm_calls` — int (session counter)

---

## Voice Mode Architecture

```
python main.py --voice
      │
      ▼
VoiceManager()
      │
      ├── WakeWordDetector (daemon thread) ─────────────────────────────────────┐
      │         loop every 2s:                                                  │
      │         CPU check (psutil) → if > 75%: sleep 30s                       │
      │         record_chunk(2s) → sounddevice.rec()                           │
      │         transcribe_wake(audio) → faster-whisper tiny model             │
      │         _is_wake_word() → checks ["jarvis wake up", "hey jarvis", ...]  │
      │         ON MATCH:                                                       │
      │           TTS speak("Yes, sir?") via edge-tts + playsound3             │
      │           record_until_silence() → VAD (RMS < 0.015 for 1.5s)         │
      │           transcribe_query(audio) → faster-whisper small model         │
      │           voice_query_queue.put(query_text)                            │
      └──────────────────────────────────────────────────────────────────────┘
      │
      ▼ (REPL loop polls queue non-blocking)
voice_manager.get_pending_query() → text
      │
      ▼
graph.invoke({messages: [HumanMessage(text)]})
      │
      ▼
AI response → voice_manager.speak_response(text)
   → VoiceManager: truncates to first 3 sentences
   → TTS speaks, full text shown on screen
```

**Wake phrases:** "jarvis wake up", "jarvis, wake up", "hey jarvis", "jarvis wakeup"  
**TTS voices:** English → `en-GB-RyanNeural`, Hindi (Devanagari) → `hi-IN-MadhurNeural`  
**Audio format:** 16kHz, mono, float32 (Whisper requirement)

---

## REPL Commands

| Command | Action |
|---------|--------|
| `/memory` | Show all Tier 1 SQLite facts |
| `/episodes` | Show Qdrant episode count |
| `/budget` | Show last token usage report |
| `/clear` | Clear screen |
| `/help` | Show command list |
| `quit` / `exit` | End session |

---

## Configuration (`core/config.py`)

### Dotenv Resolution (fallback chain):
```
1. jarvis/.env          ← preferred (for portability)
2. MEMORY_MANAGEMENT/.env ← current machine layout (where .env actually lives now)
3. load_dotenv()        ← auto-search upward from cwd
```

### All Config Constants:
```python
TOTAL_INPUT_BUDGET   = 8_000
SYSTEM_PROMPT_BUDGET = 1_600
RAG_BUDGET           = 3_200
SHORT_TERM_BUDGET    = 1_600
SYSTEM_PROMPT_MIN    = 800         # hard floor — never truncate below

LLM_PROVIDER   = "groq"            # or "openai"
LLM_MODEL      = "llama-3.3-70b-versatile"
LLM_TEMPERATURE = 0
LLM_MAX_TOKENS  = 1_600

EMBEDDING_MODEL      = "all-MiniLM-L6-v2"
EMBEDDING_DIM        = 384
RAG_SCORE_THRESHOLD  = 0.40
RAG_TOP_K            = 5

SQLITE_DB_PATH     = "data/jarvis_memory.db"
CHECKPOINT_DB_PATH = "data/jarvis_checkpoints.db"
QDRANT_PATH        = "data/qdrant_storage"
QDRANT_COLLECTION  = "jarvis_episodes"
TIKTOKEN_ENCODING  = "cl100k_base"
```

---

## User Profile (Tier 1 — stored in SQLite)

- **Name:** Shubham Prakash (preferred: Shubham)
- **Age:** 26, **Location:** Bhopal, India
- **Email:** prakashshubham075@gmail.com
- **Profession:** Intern at MpOnline
- **Skills:** Python, ML, AI, LangChain, LangGraph, Node.js, HTML, CSS, FastAPI, SQL, REST API
- **Current Projects:** JARVIS AI Assistance + Flow Desk portal (B2B Corporate SaaS)
- **Preferred Language:** Python
- **Goals:** Build JARVIS AI Assistance at full scale

---

## Dependencies (All Installed as of 2026-06-25)

### Core (in `pyproject.toml` `[project.dependencies]`):
```
langgraph==1.2.6
langchain==1.3.11
langchain-groq==1.1.3
langchain-core==1.4.8
tiktoken==0.13.0
groq==0.37.1
qdrant-client==1.18.0
sentence-transformers==5.6.0
langgraph-checkpoint-sqlite==3.1.0
python-dotenv==1.2.2
rich==15.0.0
pyfiglet==1.0.4
```

### Voice (in `[project.optional-dependencies].voice`):
```
faster-whisper==1.2.1    # STT: Whisper on CTranslate2
edge-tts==7.2.8          # TTS: Microsoft Neural Voices
sounddevice==0.5.5       # Microphone via PortAudio
playsound3==3.3.1        # MP3 playback via Windows MCI (NOT pygame)
psutil==7.2.2            # CPU monitoring
scipy==1.18.0            # scipy.io.wavfile for audio format conversion
```

> **pygame is NOT used** — pygame 2.6.x fails to compile on Python 3.14 (distutils removed).

---

## Setup on a New Machine

```powershell
# 1. Clone / copy the project
cd d:\path\to\new\location

# 2. Install uv if not present
pip install uv

# 3. Create venv + install ALL dependencies (core + voice)
cd jarvis\
uv venv
uv sync

# 4. Copy .env.example → .env, add your GROQ_API_KEY
copy .env.example .env
# Edit .env: GROQ_API_KEY="gsk_..."

# 5. CRITICAL: Always activate .venv (NOT any other venv)
.\.venv\Scripts\activate

# 6. First-run: populate user profile
python main.py --setup

# 7. Run JARVIS
python main.py              # text mode
python main.py --voice      # voice mode

# 8. Resume a specific session by ID (shown at startup)
python main.py --session <uuid>
```

> ⚠️ **Copy `data/` folder too** — it contains SQLite + Qdrant memory.  
> Without it, JARVIS starts fresh with no memory of past conversations.

---

## Bugs Fixed (2026-06-25 Session)

| # | Bug | File | Fix |
|---|-----|------|-----|
| BUG 3 | 🔴 Double-counted RAG tokens in `total_tokens` | `context_manager.py:136` | `total_tokens = system_tokens + history_tokens` (rag is inside system_tokens) |
| BUG 6 | 🔴 `points_count` returns `None` in Qdrant ≥ 1.9 → false-empty RAG | `episodic.py:126` | Replaced with `client.count(exact=False)` |
| BUG 5 | 🟡 Episodes stored in Qdrant even for empty AI responses | `memory_updater.py:67` | Guard: `if not ai_text.strip(): return {}` |
| BUG 7 | 🟢 `asyncio.run()` fails inside existing event loop | `tts.py:63` | `asyncio.new_event_loop()` + `loop.run_until_complete()` |
| BUG 8 | 🟢 O(n²) `_trim_to_budget` via `list.remove()` | `context_manager.py:172` | Rewritten to O(n) index-based pop |
| ISSUE 1 | 🟡 Hardcoded single `.env` path → breaks on move | `config.py:10` | Fallback chain: `jarvis/.env` → `parent/.env` → auto-search |
| ISSUE 2 | 🟡 `pyproject.toml` was skeleton (no deps) → `uv sync` installed 0 packages | `pyproject.toml` | Full deps + voice extras group added |
| ISSUE 3 | 🟢 `stop_speaking()` was a no-op | `tts.py:80` | Implemented with `threading.Event` |
| ISSUE 5 | 🟢 No retry on Groq API failures | `chatbot.py:45` | Exponential backoff: 3 attempts (1s → 2s → 4s) |

---

## Known Issues (Still Open)

| Issue | File | Notes |
|-------|------|-------|
| `stop_speaking()` only prevents next TTS call — can't interrupt mid-sentence | `tts.py` | Requires daemon thread for playsound; planned for future |
| Tiny Whisper model may miss wake word in noisy environments | `wake_word.py` | Increase `CHUNK_DURATION=3.0` or switch to `base` model |
| Regex fact extraction misses uppercase sentences | `memory_updater.py` | Lowercases before regex match — works for typical speech |
| Hinglish treated as English for TTS voice selection | `tts.py` | Only Devanagari script → Hindi voice; Hinglish uses English voice |
| `__del__ ImportError` on exit (Python 3.14) | `episodic.py` | `atexit.register(_close_client)` already mitigates this |

---

## Phase 2 Roadmap (Not Yet Built)

Tools to add in `tools/` directory:

| Tool | Priority | Notes |
|------|----------|-------|
| Google Calendar integration | High | Read/write events, reminders |
| Gmail reader | High | Read inbox, draft replies |
| Web search + news aggregation | High | Grounding JARVIS in real-time info |
| WhatsApp message handling | Medium | Via WhatsApp Business API |
| Google Drive / Docs / Sheets | Medium | File access + editing |
| Voice: interrupt mid-sentence (daemon thread) | Medium | Current stop_speaking() only gates next call |
| Multilingual support (Hindi, Hinglish) | Medium | Improved language detection beyond Devanagari |
| Notifications manager | Low | Desktop push notifications |
| Wake word upgrade (Picovoice / OpenWakeWord) | Low | More accurate than Whisper tiny for keyword detection |

---

## Key Design Decisions

| Decision | Reason |
|----------|--------|
| `SqliteSaver` as context manager | Keeps SQLite connection open for full REPL session |
| `atexit.register(_close_client)` in episodic.py | Prevents Qdrant `__del__ ImportError` on Python 3.14 shutdown |
| `query_points()` not `search()` | qdrant-client 1.18 removed `.search()` |
| `client.count()` for empty check | `points_count` returns None during Qdrant optimization |
| WAL mode on SQLite | Thread-safe concurrent reads for future multi-agent upgrade |
| Regex fact extraction (not LLM) | Zero extra API calls for memory updates |
| `all-MiniLM-L6-v2` embeddings | 384-dim, runs fully local, no API key needed |
| `LLM_PROVIDER` env var | One-line swap from Groq → OpenAI GPT-4o |
| `playsound3` not `pygame` | pygame 2.6.x fails to compile on Python 3.14 |
| Dual Whisper model (tiny + small) | tiny for 2s wake-word loop (low CPU), small for accurate query transcription |
| `asyncio.new_event_loop()` in TTS | Prevents RuntimeError if called inside existing event loop (e.g. FastAPI) |
| Exponential backoff retry in chatbot_node | Handles Groq rate limits / transient API failures gracefully |

---

## Session Example (Text Mode)

```
You ❯ what is my current project?

╭─ JARVIS ─────────────────────────────────────────────────────╮
│ Your current project is JARVIS AI Assistance, sir. You are   │
│ also working on the Flow Desk portal, a B2B Corporate SaaS.  │
╰──────────────────────────────────────────────────────────────╯

📊 Token Budget
  System Prompt        487 tokens
  RAG Context (Tier 2)  92 tokens  (2 chunks)
  RAG → Short-term     +3,108 tokens
  Chat History (Tier 3)  12 tokens
  ──────────────────── ──────────
  Total Input          591 / 8,000 tokens (7.4%)
  Budget Remaining     7,409 tokens
```

---

## Session Example (Voice Mode)

```
[You say: "JARVIS wake up"]
[JARVIS says: "Yes, sir?"]
[You say: "What's the weather in Bhopal today?"]
[JARVIS responds with text + speaks first 3 sentences aloud]
```

---

## Files to Backup / Sync

```
jarvis/data/jarvis_memory.db       # Tier 1: all your user facts
jarvis/data/jarvis_checkpoints.db  # Tier 3: all session histories
jarvis/data/qdrant_storage/        # Tier 2: all episodic memories (vectors)
.env                               # your API key
```

> Without these files, JARVIS has no memory of past conversations or your profile.
