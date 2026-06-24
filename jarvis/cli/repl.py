"""
JARVIS CLI — REPL Interface
============================
The main conversational loop. Uses Rich for formatted output.

Commands:
  quit / exit   — End session
  /memory       — Show all stored Tier 1 facts
  /episodes     — Show Tier 2 episode count
  /budget       — Show last token budget report
  /clear        — Clear screen
  /help         — Show command list
"""
import sys
import os
import uuid

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box
from pyfiglet import figlet_format
from langchain_core.messages import HumanMessage

console = Console()

COMMANDS = {
    "/memory":   "Show all stored personal facts (Tier 1)",
    "/episodes": "Show total Tier 2 episodic memory count",
    "/budget":   "Show last turn token budget report",
    "/clear":    "Clear the terminal screen",
    "/help":     "Show this command list",
    "quit/exit": "End the session",
}


def print_banner() -> None:
    banner = figlet_format("J.A.R.V.I.S", font="slant")
    console.print(f"[bold cyan]{banner}[/bold cyan]")
    console.print(
        Panel.fit(
            "[bold]Just A Rather Very Intelligent System[/bold]\n"
            "[dim]3-Tier Memory · LangGraph · Groq LLaMA 3.3 70B[/dim]",
            border_style="cyan",
        )
    )
    console.print()


def print_budget_report(report: dict) -> None:
    """Print a compact token budget breakdown after each response."""
    table = Table(box=box.MINIMAL, show_header=False, pad_edge=False)
    table.add_column("Metric", style="dim", width=28)
    table.add_column("Value",  style="cyan")

    table.add_row("System Prompt",      f"{report.get('system_tokens', 0):,} tokens")
    table.add_row("RAG Context (Tier 2)",f"{report.get('rag_tokens', 0):,} tokens  "
                                         f"[dim]({report.get('rag_chunks_injected', 0)} chunks)[/dim]")
    table.add_row("RAG → Short-term rollover", f"+{report.get('rag_rollover', 0):,} tokens")
    table.add_row("Chat History (Tier 3)", f"{report.get('history_tokens', 0):,} tokens")
    table.add_row("─" * 26,             "─" * 14)
    table.add_row("Total Input",
                  f"[bold]{report.get('total_input_tokens', 0):,}[/bold] / 8,000 tokens  "
                  f"([bold cyan]{report.get('utilization_pct', 0)}%[/bold cyan])")
    table.add_row("Budget Remaining",   f"{report.get('budget_remaining', 0):,} tokens")

    console.print(Panel(table, title="[dim]📊 Token Budget[/dim]",
                         border_style="dim", padding=(0, 1)))


def handle_command(cmd: str, state: dict) -> bool:
    """Handle slash commands. Returns True if handled, False if unknown."""
    if cmd == "/memory":
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from core.memory.semantic import read_facts
        facts = read_facts()
        if not facts:
            console.print("[yellow]No facts stored yet.[/yellow]")
        else:
            t = Table(title="Tier 1 — Semantic Memory", border_style="cyan")
            t.add_column("Key", style="cyan"); t.add_column("Value", style="white")
            for k, v in sorted(facts.items()):
                t.add_row(k, v)
            console.print(t)
        return True

    if cmd == "/episodes":
        from core.memory.episodic import get_episode_count
        n = get_episode_count()
        console.print(f"[cyan]Tier 2 Episodic Memory:[/cyan] {n} episodes stored in Qdrant.")
        return True

    if cmd == "/budget":
        report = state.get("last_budget_report", {})
        if not report:
            console.print("[yellow]No budget report yet. Start a conversation first.[/yellow]")
        else:
            print_budget_report(report)
        return True

    if cmd == "/clear":
        os.system("cls" if os.name == "nt" else "clear")
        return True

    if cmd == "/help":
        t = Table(title="JARVIS Commands", border_style="cyan")
        t.add_column("Command", style="cyan"); t.add_column("Description", style="white")
        for cmd_name, desc in COMMANDS.items():
            t.add_row(cmd_name, desc)
        console.print(t)
        return True

    return False


def run_repl(graph, thread_id: str | None = None, voice_manager=None) -> None:
    """Main REPL loop. Pass thread_id to resume a previous session.
    Pass voice_manager to enable voice mode (wake word → listen → speak)."""
    print_banner()

    if thread_id is None:
        thread_id = str(uuid.uuid4())

    voice_mode = voice_manager is not None
    config = {"configurable": {"thread_id": thread_id}}
    console.print(f"[dim]Session ID: {thread_id}[/dim]")
    if voice_mode:
        console.print("[bold green]🎙  Voice mode ON[/bold green] [dim]— say [cyan]'JARVIS wake up'[/cyan] to activate[/dim]")
    console.print("[dim]Type [cyan]/help[/cyan] for commands. [cyan]quit[/cyan] to exit.\n[/dim]")

    local_state = {"last_budget_report": {}}
    initial_state = {
        "messages":          [],
        "user_facts":        {},
        "rag_chunks":        [],
        "budgeted_messages": [],
        "budget_report":     {},
        "llm_calls":         0,
    }

    while True:
        # ── Voice queue check (non-blocking) ─────────────────────────────────
        # Check if wake word thread deposited a transcribed query
        voice_input = voice_manager.get_pending_query() if voice_mode else None

        if voice_input:
            user_input = voice_input
            console.print(f"[bold green]🎙 Voice[/bold green] [bold cyan]You ❯[/bold cyan] {user_input}")
        else:
            # Normal text input
            prompt = "[bold green]🎙 You ❯[/bold green] " if voice_mode else "[bold cyan]You ❯[/bold cyan] "
            try:
                user_input = console.input(prompt).strip()
            except (KeyboardInterrupt, EOFError):
                console.print("\n[dim]Session ended.[/dim]")
                break

        if not user_input:
            continue

        if user_input.lower() in ("quit", "exit"):
            console.print(Panel(
                "[bold cyan]JARVIS[/bold cyan]: Goodbye, sir. Systems standing by.",
                border_style="cyan",
            ))
            if voice_mode:
                from tools.voice.tts import speak
                speak("Goodbye, sir. Systems standing by.", lang="en")
            break

        if user_input.startswith("/"):
            handle_command(user_input, local_state)
            continue

        # ── Invoke LangGraph ──────────────────────────────────────────────────
        try:
            result = graph.invoke(
                {**initial_state, "messages": [HumanMessage(content=user_input)]},
                config=config,
            )
        except Exception as e:
            console.print(f"[red]Error:[/red] {e}")
            continue

        # ── Display AI response ───────────────────────────────────────────────
        ai_messages = [m for m in result["messages"] if hasattr(m, "type") and m.type == "ai"]
        if ai_messages:
            response_text = ai_messages[-1].content
            console.print(Panel(
                Text(response_text, style="white"),
                title="[bold cyan]JARVIS[/bold cyan]",
                border_style="cyan",
                padding=(1, 2),
            ))
            # ── Speak response if voice mode active ───────────────────────────
            if voice_mode:
                voice_manager.speak_response(response_text)

        # ── Show token budget report ──────────────────────────────────────────
        budget = result.get("budget_report", {})
        if budget:
            local_state["last_budget_report"] = budget
            print_budget_report(budget)

        console.print()
