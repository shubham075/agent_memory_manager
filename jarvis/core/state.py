"""
JARVIS State Definition
Single TypedDict shared across all graph nodes.
"""
import operator
from typing import Annotated, TypedDict
from langchain_core.messages import AnyMessage


class JarvisState(TypedDict):
    # Tier 3: Full raw conversation history (LangGraph appends via operator.add)
    messages: Annotated[list[AnyMessage], operator.add]

    # Tier 1: User facts loaded from SQLite (in-memory cache per turn)
    user_facts: dict

    # Tier 2: RAG chunks retrieved this turn from Qdrant
    rag_chunks: list[dict]

    # Final LLM-ready message list after budgeting + trimming
    budgeted_messages: list[AnyMessage]

    # Token usage report for observability (printed after each response)
    budget_report: dict

    # Total LLM calls in this session
    llm_calls: int
