"""
JARVIS First-Run Setup Wizard
================================
Collects your personal profile and pre-populates Tier 1 Semantic Memory.
Run once: python setup_wizard.py
"""
from rich.console import Console
from rich.prompt import Prompt, Confirm
from rich.panel import Panel
from rich.table import Table

console = Console()

PROFILE_FIELDS: list[tuple[str, str, str, str]] = [
    # (fact_key, display_label, category, example)
    ("preferred_name",   "Your preferred name / nickname",     "identity",    "e.g. Shubham"),
    ("full_name",        "Full name",                          "identity",    "e.g. Shubham Kumar"),
    ("age",              "Age",                                "identity",    "e.g. 25"),
    ("location",         "City / Country",                     "identity",    "e.g. Delhi, India"),
    ("email",            "Email address",                      "identity",    "e.g. you@gmail.com"),
    ("profession",       "Profession / Job title",             "work",        "e.g. AI Engineer"),
    ("workplace",        "Company / Organisation",             "work",        "e.g. TechCorp"),
    ("skills",           "Primary skills (comma-separated)",   "work",        "e.g. Python, ML, LangChain"),
    ("current_project",  "Current main project",               "work",        "e.g. JARVIS AI Assistant"),
    ("languages_spoken", "Languages spoken",                   "identity",    "e.g. Hindi, English"),
    ("hobbies",          "Hobbies / interests",                "preferences", "e.g. reading, coding, chess"),
    ("preferred_lang",   "Preferred programming language",     "preferences", "e.g. Python"),
    ("working_hours",    "Typical working hours",              "preferences", "e.g. 9 AM – 11 PM IST"),
    ("goals",            "Current short-term goals",           "work",        "e.g. Build JARVIS v1"),
]


def run_wizard() -> None:
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

    from core.memory.semantic import init_semantic_db, bulk_write_facts, read_facts

    console.print(Panel.fit(
        "[bold cyan]JARVIS Setup Wizard[/bold cyan]\n"
        "[dim]Populating your personal profile into Tier 1 Semantic Memory[/dim]",
        border_style="cyan",
    ))

    # Create table first (safe if it already exists)
    init_semantic_db()

    # Check if profile already exists
    existing = read_facts()
    if existing:
        console.print(f"\n[yellow]A profile with {len(existing)} facts already exists.[/yellow]")
        if not Confirm.ask("Overwrite / update it?", default=False):
            console.print("[green]Setup skipped. Your existing profile is intact.[/green]")
            return

    facts: dict[str, tuple[str, str]] = {}

    console.print("\n[bold]Enter your details[/bold] (press Enter to skip any field):\n")

    for key, label, category, example in PROFILE_FIELDS:
        value = Prompt.ask(f"  [cyan]{label}[/cyan] [dim]({example})[/dim]", default="")
        if value.strip():
            facts[key] = (value.strip(), category)

    if not facts:
        console.print("[red]No data entered. Setup cancelled.[/red]")
        return

    bulk_write_facts(facts)

    # Show summary table
    table = Table(title="Saved Profile", border_style="green")
    table.add_column("Key", style="cyan")
    table.add_column("Value", style="white")
    table.add_column("Category", style="dim")
    for key, (value, cat) in facts.items():
        table.add_row(key, value, cat)
    console.print(table)

    console.print("\n[bold green]✓ Profile saved to Tier 1 Semantic Memory (SQLite)[/bold green]")
    console.print("[dim]Run [cyan]python main.py[/cyan] to start JARVIS.[/dim]\n")


if __name__ == "__main__":
    run_wizard()
