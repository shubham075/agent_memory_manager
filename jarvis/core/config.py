"""
JARVIS Configuration
All constants, paths, and environment settings in one place.
To swap LLM to GPT-4o: set LLM_PROVIDER=openai in .env.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent.parent.parent / ".env")

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR  = Path(__file__).parent.parent          # jarvis/
DATA_DIR  = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# ── LLM ───────────────────────────────────────────────────────────────────────
LLM_PROVIDER   = os.getenv("LLM_PROVIDER", "groq")      # "groq" | "openai"
GROQ_API_KEY   = os.getenv("GROQ_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
LLM_MODEL      = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0"))
LLM_MAX_TOKENS  = int(os.getenv("LLM_MAX_TOKENS", "1600"))

# ── Token Budget (Input Window = 8,000 tokens) ────────────────────────────────
# NOTE: For LLaMA production use, swap tiktoken for:
#   transformers.AutoTokenizer.from_pretrained("meta-llama/Meta-Llama-3-70B")
TOTAL_INPUT_BUDGET  = 8_000
SYSTEM_PROMPT_BUDGET = 1_600   # 20% — Tier 1: system prompt + user facts
RAG_BUDGET           = 3_200   # 40% — Tier 2: episodic context chunks
SHORT_TERM_BUDGET    = 1_600   # 20% — Tier 3: chat history
# Flex-space (remaining 20%) rolls over from unused RAG → short-term
SYSTEM_PROMPT_MIN    = 800     # Hard floor: never truncate below this

TIKTOKEN_ENCODING = "cl100k_base"

# ── Persistence ───────────────────────────────────────────────────────────────
SQLITE_DB_PATH     = str(DATA_DIR / "jarvis_memory.db")
CHECKPOINT_DB_PATH = str(DATA_DIR / "jarvis_checkpoints.db")
QDRANT_PATH        = str(DATA_DIR / "qdrant_storage")
QDRANT_COLLECTION  = "jarvis_episodes"

# ── Embeddings & RAG ──────────────────────────────────────────────────────────
EMBEDDING_MODEL    = "all-MiniLM-L6-v2"   # Free, local, 384-dim
EMBEDDING_DIM      = 384
RAG_SCORE_THRESHOLD = 0.40   # Cosine similarity threshold for retrieval
RAG_TOP_K          = 5       # Max episodes to inject per turn
