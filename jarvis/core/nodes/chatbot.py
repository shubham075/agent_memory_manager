"""
Node 2 — chatbot_node
======================
Calls the LLM with the budgeted message list produced by context_manager_node.
Supports Groq (default) and OpenAI (future swap via LLM_PROVIDER env var).

Output tokens are controlled via max_tokens=1600 on the LLM constructor.
This is separate from the input window — we never waste input tokens on output.
"""
from langchain_core.messages import AIMessage
from core.config import (
    LLM_PROVIDER, LLM_MODEL, LLM_TEMPERATURE, LLM_MAX_TOKENS,
    GROQ_API_KEY, OPENAI_API_KEY,
)
from core.state import JarvisState

# ── LLM Factory (swap provider by changing .env LLM_PROVIDER) ─────────────────
def _build_llm():
    if LLM_PROVIDER == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=LLM_MODEL,
            temperature=LLM_TEMPERATURE,
            max_tokens=LLM_MAX_TOKENS,
            openai_api_key=OPENAI_API_KEY,
        )
    # Default: Groq (free, fastest inference available)
    from langchain_groq import ChatGroq
    return ChatGroq(
        model=LLM_MODEL,
        temperature=LLM_TEMPERATURE,
        max_tokens=LLM_MAX_TOKENS,
        groq_api_key=GROQ_API_KEY,
    )

_llm = None

def _get_llm():
    global _llm
    if _llm is None:
        _llm = _build_llm()
    return _llm


def chatbot_node(state: JarvisState) -> dict:
    """
    Pure function — calls LLM with budgeted_messages, returns AI response.
    The response is added to the messages list via operator.add in the state.
    """
    budgeted_messages = state["budgeted_messages"]
    response: AIMessage = _get_llm().invoke(budgeted_messages)
    return {
        "messages":  [response],
        "llm_calls": state.get("llm_calls", 0) + 1,
    }
