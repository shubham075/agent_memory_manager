# JARVIS Project Context — Quick Resume Document

> **Purpose:** Paste this file to any AI assistant on any machine to instantly resume work without re-analysis.  
> **Last updated:** 2026-06-25

---

## What Is This Project

A personal AI assistant (JARVIS) built with LangGraph + Groq LLaMA 3.3 70B.  
Uses a 3-tier memory architecture for persistent, context-aware conversations.

**Location:** `d:\CODES\AGENTIC_AI\agent_memory_manager\jarvis\`  
**Run:** `.venv\Scripts\activate` → `python main.py`  
**Setup:** `python setup_wizard.py` (first run only)

---

## Stack

| Component | Choice | Reason |
|-----------|--------|--------|
| LLM | Groq LLaMA 3.3 70B (`llama-3.3-70b-versatile`) | Free, fastest inference, 128k context |
| LLM swap path | Set `LLM_PROVIDER=openai` in `.env` | Built-in factory in `core/nodes/chatbot.py` |
| Orchestration | LangGraph ≥ 0.2 | Graph-based flow control |
| Tier 1 Memory | SQLite (`jarvis_memory.db`) | Permanent user facts |
| Tier 2 Memory | Qdrant local (`qdrant_storage/`) + sentence-transformers | Real RAG, no server needed |
| Tier 2 Embeddings | `all-MiniLM-L6-v2` (384-dim, free, local) | Fast, good quality |
| Tier 3 Memory | LangGraph SqliteSaver (`jarvis_checkpoints.db`) | Cross-session chat persistence |
| Token counting | `tiktoken` cl100k_base | Approximation for LLaMA |
| CLI | `rich` + `pyfiglet` | Beautiful REPL with token budget display |
| Package manager | `uv` | Fast installs |
| Python | 3.14 (CPython) | Confirmed working |

---

## Project File Structure

```
jarvis/
├── main.py                        # Entry point. Flags: --setup, --session <id>
├── setup_wizard.py                # First-run profile setup (populates Tier 1)
├── pyproject.toml                 # uv dependencies
├── requirements.txt               # pip-compatible alternative
├── .env.example                   # Copy to .env, add GROQ_API_KEY
├── .venv/                         # Virtual environment (uv sync)
├── data/
│   ├── jarvis_memory.db           # SQLite: Tier 1 user facts
│   ├── jarvis_checkpoints.db      # SQLite: LangGraph session state
│   └── qdrant_storage/            # Qdrant: Tier 2 episode vectors
├── core/
│   ├── config.py                  # All constants, paths, token budgets
│   ├── state.py                   # JarvisState TypedDict
│   ├── tokenizer.py               # count_tokens(), count_message_tokens()
│   ├── exceptions.py              # ContextBudgetError, MemoryWriteError
│   ├── memory/
│   │   ├── semantic.py            # Tier 1: SQLite read/write (facts_as_text, write_fact)
│   │   └── episodic.py            # Tier 2: Qdrant RAG (store_episode, retrieve_episodes)
│   └── nodes/
│       ├── context_manager.py     # Node 1: Token budgeting + rollover logic
│       ├── chatbot.py             # Node 2: LLM call (Groq/OpenAI factory)
│       └── memory_updater.py      # Node 3: Regex fact extraction + episode storage
├── graph/
│   └── jarvis_graph.py            # LangGraph definition + SqliteSaver context manager
├── cli/
│   └── repl.py                    # Rich REPL, /memory /episodes /budget /help commands
└── tools/                         # Phase 2: Google, WhatsApp, voice, etc.
```

---

## 3-Tier Memory Architecture

```
User Message
     │
     ▼
[context_manager_node]
     ├── Tier 1: read SQLite facts → inject into system prompt (1,600t budget)
     ├── Tier 2: embed query → Qdrant query_points() → MMR filter → inject (3,200t budget)
     │          Flex-space: unused RAG tokens roll over to Tier 3 budget
     └── Tier 3: trim chat history to (1,600t + rollover) budget
     │
     ▼
[chatbot_node] → Groq LLM call (max_tokens=1600 output, separate from input)
     │
     ▼
[memory_update_node]
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

### What Happens at 100% Budget
1. Oldest chat messages dropped first (Tier 3 trim)
2. RAG section stripped from system prompt if needed
3. System prompt truncated to 800 token minimum floor
4. `ContextBudgetError` raised only if single message > 7,200 tokens (never in practice)

---

## LangGraph Graph Topology

```
START → context_manager_node → chatbot_node → memory_update_node → END
```

- Checkpointer: `SqliteSaver(conn)` used as context manager in `build_graph()`
- Session resume: `python main.py --session <uuid>` (uuid printed at startup)
- State: `JarvisState` TypedDict with `messages`, `user_facts`, `rag_chunks`, `budgeted_messages`, `budget_report`, `llm_calls`

---

## Key Design Decisions

| Decision | Reason |
|----------|--------|
| `SqliteSaver` as context manager | Keeps SQLite connection open for full REPL session; prevents mid-session close |
| `atexit.register(_close_client)` in episodic.py | Prevents Qdrant `__del__ ImportError` on Python shutdown |
| `query_points()` not `search()` | qdrant-client 1.18 removed `.search()` |
| WAL mode on SQLite | Thread-safe concurrent reads for future multi-agent upgrade |
| Regex fact extraction (not LLM) | Zero extra API calls for memory updates |
| `all-MiniLM-L6-v2` embeddings | 384-dim, runs fully local, no API key needed |
| `LLM_PROVIDER` env var | One-line swap from Groq → OpenAI GPT-4o |

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

## User Profile (Tier 1 — stored in SQLite)

- **Name:** Shubham Prakash (preferred: Shubham)
- **Age:** 26, **Location:** Bhopal, India
- **Email:** prakashshubham075@gmail.com
- **Profession:** Intern at MpOnline
- **Skills:** Python, ML, AI, LangChain, LangGraph, Node.js, HTML, CSS, FastAPI, SQL, REST API
- **Current Project:** JARVIS AI Assistance + Flow Desk portal
- **Preferred Language:** Python
- **Goals:** Build JARVIS AI Assistance at full scale

---

## Phase 2 Roadmap (Not Yet Built)

Tools to add in `tools/` directory:
- Google Calendar, Gmail, Drive, Maps, Sheets/Docs
- WhatsApp message handling
- Voice commands + wake word activation
- Web scraping + news aggregation
- Multilingual support (Hindi, English, Hinglish)
- Notifications manager
- Agent voice activation

---

## Known Issues Fixed

| Error | Fix Applied |
|-------|------------|
| `no such table: user_facts` | `init_semantic_db()` called before `read_facts()` in setup_wizard |
| `QdrantClient has no attribute 'search'` | Replaced with `query_points()` (qdrant-client 1.18 API) |
| `__del__ ImportError on exit` | `atexit.register(_close_client)` in episodic.py |
| `SqliteSaver` connection closing mid-session | `build_graph()` is now a `@contextmanager` |

---

## How to Resume on Another Machine

```powershell
# 1. Clone / copy the project folder
# 2. cd into jarvis/
cd d:\path\to\jarvis

# 3. Install uv if not present
pip install uv

# 4. Create venv + install all deps
uv venv
uv sync

# 5. Copy .env.example → .env, add your GROQ_API_KEY
copy .env.example .env
# Edit .env: GROQ_API_KEY="your_key_here"

# 6. Run (profile already in SQLite, just start)
.venv\Scripts\activate
python main.py

# 7. Or resume a specific session by ID
python main.py --session 821f8a08-e69c-4fc9-9f3a-da3e21eb2874
```

> ⚠️ `data/` folder (SQLite + Qdrant) must be copied too — it contains your memory.
> Add it to your backup or sync it via cloud storage.
