"""
JARVIS LangGraph — Graph Assembly
===================================
Graph topology:
    START → context_manager_node → chatbot_node → memory_update_node → END

Checkpointer: SqliteSaver
    Persists full state to disk so JARVIS remembers sessions across restarts.
    db_path: data/jarvis_checkpoints.db
    thread_id: uuid4 per session (pass same id to resume a session)

IMPORTANT: SqliteSaver must be kept open for the full session lifetime.
Use build_graph() as a context manager via `with build_graph() as graph:`.
"""
import sqlite3
from contextlib import contextmanager

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite import SqliteSaver

from core.state import JarvisState
from core.nodes import context_manager_node, chatbot_node, memory_update_node
from core.config import CHECKPOINT_DB_PATH


def _build_state_graph():
    """Build the StateGraph (nodes + edges) — no checkpointer yet."""
    builder = StateGraph(JarvisState)

    builder.add_node("context_manager", context_manager_node)
    builder.add_node("chatbot",         chatbot_node)
    builder.add_node("memory_update",   memory_update_node)

    builder.add_edge(START,             "context_manager")
    builder.add_edge("context_manager", "chatbot")
    builder.add_edge("chatbot",         "memory_update")
    builder.add_edge("memory_update",   END)

    return builder


@contextmanager
def build_graph():
    """
    Context manager that yields a compiled JARVIS graph with an open
    SqliteSaver checkpointer. The connection is closed cleanly on exit.

    Usage:
        with build_graph() as graph:
            run_repl(graph)
    """
    conn = sqlite3.connect(CHECKPOINT_DB_PATH, check_same_thread=False)
    try:
        checkpointer = SqliteSaver(conn)
        compiled = _build_state_graph().compile(checkpointer=checkpointer)
        yield compiled
    finally:
        conn.close()

