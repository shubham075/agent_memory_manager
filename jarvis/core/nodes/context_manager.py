"""
Node 1 — context_manager_node
==============================
Assembles the final LLM-ready message list from all three memory tiers.

Token budget (8,000 total input tokens):
    ┌────────────────────────┬────────┬──────┐
    │ Slot                   │ Tokens │   %  │
    ├────────────────────────┼────────┼──────┤
    │ System Prompt (Tier 1) │  1,600 │  20% │
    │ RAG Context   (Tier 2) │  3,200 │  40% │
    │ Chat History  (Tier 3) │  1,600 │  20% │
    │ Flex-Space             │  1,600 │  20% │
    └────────────────────────┴────────┴──────┘

Flex-Space Rollover:
    rollover = RAG_BUDGET - rag_tokens_used
    effective_short_term = SHORT_TERM_BUDGET + rollover
    → Unused RAG budget is donated to chat history.

Output tokens are controlled via max_tokens on the LLM call itself —
they are NOT reserved inside the input window (that would waste context).
"""
from datetime import datetime
from langchain_core.messages import SystemMessage, HumanMessage

from core.config import (
    TOTAL_INPUT_BUDGET, SYSTEM_PROMPT_BUDGET, RAG_BUDGET,
    SHORT_TERM_BUDGET, SYSTEM_PROMPT_MIN,
)
from core.exceptions import ContextBudgetError
from core.memory.semantic import facts_as_text
from core.memory.episodic import retrieve_episodes
from core.tokenizer import count_tokens, count_message_tokens, count_messages_tokens
from core.state import JarvisState

# ── System Prompt Template ────────────────────────────────────────────────────
_SYSTEM_TEMPLATE = """\
You are JARVIS (Just A Rather Very Intelligent System), a highly sophisticated \
personal AI assistant modeled after the AI in the Iron Man films.

Behavioral directives:
  • Address the user as "sir" or by their preferred name.
  • Be concise, precise, and technically accurate.
  • Proactively surface relevant information when appropriate.
  • Never be verbose unless a detailed explanation is explicitly requested.
  • Maintain full continuity across sessions using your memory systems.
  • If uncertain, state your confidence level rather than guessing.

══ USER PROFILE (Tier 1 — Semantic Memory) ══
{user_facts}

══ RELEVANT PAST CONTEXT (Tier 2 — Episodic Memory) ══
{rag_context}

Current date/time: {datetime}
"""


def context_manager_node(state: JarvisState) -> dict:
    """
    Pure function — receives state, returns a state-update dict.
    Steps:
      1. Identify latest HumanMessage (used as RAG query + must-keep anchor)
      2. Retrieve Tier 2 episodes, pack into RAG_BUDGET, compute rollover
      3. Build system prompt from Tier 1 facts + retrieved RAG context
      4. Trim Tier 3 chat history to effective budget (SHORT_TERM + rollover)
      5. Assemble [SystemMessage] + trimmed_history → budgeted_messages
      6. Emit budget_report for observability
    """
    messages = state["messages"]

    # ── 1. Latest HumanMessage (RAG query anchor) ─────────────────────────────
    latest_human = next(
        (m for m in reversed(messages) if isinstance(m, HumanMessage)), None
    )
    latest_human_tokens = count_message_tokens(latest_human) if latest_human else 0

    # ── 2. Tier 2: Retrieve episodic context ──────────────────────────────────
    rag_chunks: list[dict] = []
    if latest_human:
        rag_chunks = retrieve_episodes(latest_human.content)

    # Pack RAG chunks into RAG_BUDGET
    rag_lines, rag_used = [], 0
    for chunk in rag_chunks:
        line = f"[Relevance {chunk['score']:.2f}] {chunk['content']}"
        line_tokens = count_tokens(line)
        if rag_used + line_tokens <= RAG_BUDGET:
            rag_lines.append(line)
            rag_used += line_tokens

    rag_context = "\n\n".join(rag_lines) if rag_lines else "No relevant past episodes found."
    # Flex-space: unused RAG budget rolls over to chat history
    rag_rollover = RAG_BUDGET - rag_used
    short_term_effective = SHORT_TERM_BUDGET + rag_rollover

    # ── 3. Tier 1: Build system prompt ────────────────────────────────────────
    system_content = _SYSTEM_TEMPLATE.format(
        user_facts=facts_as_text(),
        rag_context=rag_context,
        datetime=datetime.now().strftime("%A, %B %d %Y — %H:%M"),
    )
    system_tokens = count_tokens(system_content)

    # If system prompt exceeds budget, strip RAG section (keep facts)
    if system_tokens > SYSTEM_PROMPT_BUDGET:
        system_content = _SYSTEM_TEMPLATE.format(
            user_facts=facts_as_text(),
            rag_context="[RAG context omitted to fit token budget]",
            datetime=datetime.now().strftime("%A, %B %d %Y — %H:%M"),
        )
        system_tokens = count_tokens(system_content)

    # ── 4. Hard minimum safety check ──────────────────────────────────────────
    # Even with a bare-minimum system prompt, we need room for the user message.
    min_required = SYSTEM_PROMPT_MIN + latest_human_tokens
    if min_required > TOTAL_INPUT_BUDGET:
        raise ContextBudgetError(
            f"Minimum context ({min_required} tokens) exceeds total budget "
            f"({TOTAL_INPUT_BUDGET} tokens). "
            f"[system_min={SYSTEM_PROMPT_MIN}t, user_msg={latest_human_tokens}t]"
        )

    # ── 5. Tier 3: Trim chat history to effective budget ──────────────────────
    history = [m for m in messages if not isinstance(m, SystemMessage)]
    trimmed = _trim_to_budget(history, short_term_effective, must_keep=latest_human)
    history_tokens = count_messages_tokens(trimmed)

    # ── 6. Assemble final message list ────────────────────────────────────────
    budgeted_messages = [SystemMessage(content=system_content)] + trimmed

    total_tokens = system_tokens + rag_used + history_tokens

    budget_report = {
        "system_tokens":          system_tokens,
        "rag_tokens":             rag_used,
        "rag_chunks_injected":    len(rag_lines),
        "rag_rollover":           rag_rollover,
        "history_tokens":         history_tokens,
        "short_term_budget_used": short_term_effective,
        "total_input_tokens":     total_tokens,
        "budget_remaining":       TOTAL_INPUT_BUDGET - total_tokens,
        "utilization_pct":        round(total_tokens / TOTAL_INPUT_BUDGET * 100, 1),
    }

    return {
        "budgeted_messages": budgeted_messages,
        "rag_chunks":        rag_chunks,
        "budget_report":     budget_report,
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _trim_to_budget(history: list, budget: int, must_keep) -> list:
    """
    Drop oldest messages first until total tokens <= budget.
    The must_keep message (latest HumanMessage) is NEVER dropped.
    """
    total = count_messages_tokens(history)
    if total <= budget:
        return history

    result = list(history)
    for msg in history:
        if msg is must_keep:
            continue
        result.remove(msg)
        total -= count_message_tokens(msg)
        if total <= budget:
            break
    return result
