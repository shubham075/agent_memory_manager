"""
Node 3 — memory_update_node
=============================
Runs AFTER chatbot_node. Performs two memory write-back operations:

1. Tier 1 Update (Semantic): Uses a lightweight LLM call to extract any new
   facts the user revealed in this turn (e.g., "my name is X", "I work at Y").
   Extracted facts are written to SQLite.

2. Tier 2 Update (Episodic): Summarizes the last exchange (human + AI) and
   stores it as a new episode in Qdrant so future turns can retrieve it.

Graph topology: START → context_manager → chatbot → memory_update → END

Without this node, the system can only READ memory — never LEARN from it.
This is what makes JARVIS smarter over time.
"""
import re
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from core.memory.semantic import write_fact
from core.memory.episodic import store_episode
from core.state import JarvisState


# ── Fact extraction patterns (lightweight, no extra LLM call needed) ──────────
# These regex patterns catch common self-disclosure statements.
# Future upgrade: replace with a dedicated extraction LLM call for higher recall.
_FACT_PATTERNS: list[tuple[str, str, str]] = [
    # (regex, fact_key, category)
    (r"my name is ([A-Za-z ]+)",          "preferred_name",  "identity"),
    (r"i(?:'m| am) ([A-Za-z ]+) years old", "age",           "identity"),
    (r"i live in ([A-Za-z ,]+)",           "location",        "identity"),
    (r"i work (?:at|for) ([A-Za-z0-9 .]+)","workplace",       "work"),
    (r"i(?:'m| am) a ([A-Za-z ]+)",        "profession",      "work"),
    (r"i(?:'m| am) working on ([^.!?]+)",  "current_project", "work"),
    (r"i prefer ([^.!?]+)",                "preference",      "preferences"),
    (r"i like ([^.!?]+)",                  "likes",           "preferences"),
    (r"i (?:don't|do not) like ([^.!?]+)", "dislikes",        "preferences"),
    (r"call me ([A-Za-z ]+)",              "preferred_name",  "identity"),
    (r"my (?:email|mail) is ([^\s]+)",     "email",           "identity"),
    (r"my (?:phone|number) is ([^\s]+)",   "phone",           "identity"),
]


def memory_update_node(state: JarvisState) -> dict:
    """
    Pure function — reads the latest exchange, updates memory, returns empty diff.
    No LangGraph state fields are modified here (memory is side-effect storage).
    """
    messages = state["messages"]

    # Get latest human → AI exchange
    latest_human = next(
        (m for m in reversed(messages) if isinstance(m, HumanMessage)), None
    )
    latest_ai = next(
        (m for m in reversed(messages) if isinstance(m, AIMessage)), None
    )

    if not latest_human or not latest_ai:
        return {}

    user_text = latest_human.content
    ai_text   = latest_ai.content

    # Guard: skip memory writes if AI response is empty or failed
    if not ai_text or not ai_text.strip():
        return {}

    # ── Tier 1 Update: Extract and persist new facts ───────────────────────────
    _extract_and_store_facts(user_text)

    # ── Tier 2 Update: Persist episode for future RAG retrieval ───────────────
    # Format: compact Q&A summary so future retrievals are meaningful
    episode_text = (
        f"User asked: {user_text[:300]}\n"
        f"JARVIS responded: {ai_text[:400]}"
    )
    store_episode(
        content=episode_text,
        topic=_infer_topic(user_text),
        metadata={"turn_llm_calls": state.get("llm_calls", 0)},
    )

    return {}   # No state fields updated — memory writes are direct to storage


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_and_store_facts(text: str) -> None:
    """Apply regex patterns to detect and store self-disclosed user facts."""
    text_lower = text.lower()
    for pattern, key, category in _FACT_PATTERNS:
        match = re.search(pattern, text_lower)
        if match:
            value = match.group(1).strip().title()
            if value:
                write_fact(key, value, category)


def _infer_topic(text: str) -> str:
    """Cheaply infer a topic label from the user's message for Qdrant payload."""
    keywords = {
        "code":    ["code", "function", "error", "bug", "python", "script", "api"],
        "work":    ["project", "task", "meeting", "deadline", "work", "client"],
        "weather": ["weather", "rain", "temperature", "forecast"],
        "news":    ["news", "article", "headline", "latest"],
        "general": [],
    }
    text_lower = text.lower()
    for topic, words in keywords.items():
        if any(w in text_lower for w in words):
            return topic
    return "general"
