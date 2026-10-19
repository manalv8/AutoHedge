"""
AutoHedge CLI — welcome screen and interactive REPL.
"""

import argparse
import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.columns import Columns
from rich import box

from autohedge.env_loader import load_env, require_openai_key

load_env()
if not require_openai_key():
    Console().print(
        "[yellow]Warning: OPENAI_API_KEY not set. Set it in .env or export it.[/]"
    )

try:
    from importlib.metadata import version as _version

    VERSION = _version("autohedge")
except Exception:
    VERSION = "0.1.2"

console = Console()

# ASCII art: minimal "hedge" / chart vibe
BANNER_ART = r"""
    ▄▄▄▄▄▄▄
   █████████
  ▐▀▄▄▄▄▄▀▌
     ▀ ▀
  ▄▄ ▀▄▀ ▄▄
"""

TIPS = [
    "Enter a task prompt to run (e.g. 'Analyze NVDA and SOL-USD')",
    "Paper trading only: every recommendation goes to outputs/ledger.jsonl",
    "Type 'quit' or 'exit' to leave",
    "Type 'help' or '?' for commands",
]

RECENT_FILE = Path.home() / ".autohedge" / "recent_tasks.txt"
MAX_RECENT = 5


def _get_recent_tasks() -> list[str]:
    if not RECENT_FILE.exists():
        return []
    try:
        lines = RECENT_FILE.read_text().strip().splitlines()
        return [
            ln.strip() for ln in lines[-MAX_RECENT:] if ln.strip()
        ]
    except Exception:
        return []


def _append_recent(task: str) -> None:
    try:
        RECENT_FILE.parent.mkdir(parents=True, exist_ok=True)
        recent = _get_recent_tasks()
        if task in recent:
            recent.remove(task)
        recent.append(task)
        RECENT_FILE.write_text("\n".join(recent[-MAX_RECENT:]))
    except Exception:
        pass


def _welcome() -> None:
    cwd = Path.cwd()
    try:
        cwd_str = cwd.relative_to(Path.home())
        cwd_display = f"~/{cwd_str}"
    except ValueError:
        cwd_display = str(cwd)

    welcome = Text("Welcome to AutoHedge", style="bold orange1")
    subtitle = Text(
        f"v{VERSION} · {cwd_display}",
        style="dim",
    )

    tips_text = Text(
        "Tips for getting started\n", style="bold orange1"
    )
    tips_text.append(" — ".join(TIPS), style="dim")

    recent = _get_recent_tasks()
    recent_heading = Text("Recent activity\n", style="bold orange1")
    if recent:
        recent_body = Text("\n".join(recent[-3:]), style="dim")
    else:
        recent_body = Text("No recent activity", style="dim")

    left = Text()
    left.append(welcome)
    left.append("\n\n")
    left.append(BANNER_ART, style="cyan")
    left.append("\n")
    left.append(subtitle)

    right = Text()
    right.append(tips_text)
    right.append("\n")
    right.append("─" * 50 + "\n", style="dim")
    right.append(recent_heading)
    right.append(recent_body)

    # Two-column layout inside one panel (Claude Code style)
    left_panel = Panel(
        left,
        box=box.MINIMAL,
        padding=(0, 1),
        border_style="dim",
        expand=False,
    )
    right_panel = Panel(
        right,
        box=box.MINIMAL,
        padding=(0, 1),
        border_style="dim",
        expand=True,
    )
    cols = Columns(
        [left_panel, right_panel], expand=True, equal=False
    )
    console.print(
        Panel(
            cols,
            title=f"[bold]AutoHedge v{VERSION}[/]",
            title_align="left",
            border_style="cyan",
            padding=(0, 1),
        )
    )


def _run_task(task: str) -> list:
    from autohedge import AutoHedge

    return AutoHedge().run(task=task)


def _fmt(value) -> str:
    return "-" if value is None else f"{value:,.4g}"


def render_recommendations(recs: list) -> None:
    """Print recommendations as a table."""
    table = Table(title="Paper recommendations", box=box.SIMPLE)
    for col in (
        "ticker",
        "approved",
        "reasons",
        "entry",
        "stop",
        "tp",
        "notional",
    ):
        table.add_column(col)
    for r in recs:
        o = r.order
        table.add_row(
            r.ticker or "-",
            "[green]yes[/]" if r.approved else "[red]no[/]",
            ", ".join(r.reasons) or "-",
            _fmt(o and o.entry_price),
            _fmt(o and o.stop_loss),
            _fmt(o and o.take_profit),
            _fmt(o and o.notional_usd),
        )
    console.print(table)


def render_evaluation(outcomes: list, report) -> None:
    """Print scored outcomes and the aggregate report."""
    table = Table(title="Outcomes", box=box.SIMPLE)
    for col in ("ticker", "status", "return %", "buy&hold %"):
        table.add_column(col)
    for o in outcomes:
        table.add_row(
            o.ticker,
            o.status,
            _fmt(o.return_pct),
            _fmt(o.benchmark_return_pct),
        )
    console.print(table)

    def pct(v):
        return "-" if v is None else f"{v:.2f}%"

    console.print(
        f"Recommendations: {report.n_total} · "
        f"Resolved: {report.n_resolved} · "
        f"Pending: {report.n_pending} · "
        f"Unfilled: {report.n_unfilled}"
    )
    console.print(
        "Win rate: "
        + (
            "-"
            if report.win_rate is None
            else f"{report.win_rate * 100:.1f}%"
        )
        + f" · Expectancy (net of fees): {pct(report.expectancy_pct)}"
        + f" · Buy & hold: {pct(report.avg_benchmark_return_pct)}"
    )


def run_repl() -> None:
    _welcome()

    while True:
        try:
            prompt = Text("> ", style="bold cyan")
            console.print(prompt, end="")
            line = input().strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Goodbye.[/]")
            break

        if not line:
            continue

        lower = line.lower()
        if lower in ("quit", "exit", "q"):
            console.print("[dim]Goodbye.[/]")
            break

        if lower in ("help", "?", "h"):
            for t in TIPS:
                console.print(f"  [dim]·[/] {t}")
            continue

        # Treat as task prompt
        _append_recent(line)
        try:
            console.print("[dim]Running...[/]")
            render_recommendations(_run_task(line))
        except Exception as e:
            console.print(f"[red]Error: {e}[/]")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="autohedge",
        description="AutoHedge — paper-trading research agents.",
        epilog="""
Commands (when running the REPL):
  <task>     Run a task (e.g. 'Analyze NVDA and SOL-USD')
  help, ?, h Show in-REPL tips
  quit, exit, q  Exit the REPL

Examples:
  autohedge                       Start the interactive REPL
  autohedge run "Analyze NVDA"    Run one task and exit
  autohedge evaluate              Score past recommendations
  autohedge --version             Show version
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version",
        "-v",
        action="version",
        version=f"%(prog)s {VERSION}",
        help="Show program version and exit.",
    )
    sub = parser.add_subparsers(dest="command")
    run_p = sub.add_parser("run", help="Run one task and exit.")
    run_p.add_argument("task", help="Task prompt in natural language.")
    eval_p = sub.add_parser(
        "evaluate", help="Score recommendations in the ledger."
    )
    eval_p.add_argument(
        "--ledger",
        default="outputs/ledger.jsonl",
        help="Path to ledger.jsonl (default: outputs/ledger.jsonl).",
    )
    return parser


def main() -> None:
    """Entry point for the AutoHedge CLI."""
    parser = _build_parser()
    # Treat bare "help" as --help (e.g. "autohedge help")
    if len(sys.argv) == 2 and sys.argv[1].lower() == "help":
        parser.print_help()
        sys.exit(0)
    args = parser.parse_args()  # exits on --help / --version
    if args.command == "run":
        try:
            render_recommendations(_run_task(args.task))
        except Exception as e:
            console.print(f"[red]Error: {e}[/]")
            sys.exit(1)
    elif args.command == "evaluate":
        from autohedge.evaluation import evaluate_ledger

        render_evaluation(*evaluate_ledger(Path(args.ledger)))
    else:
        run_repl()
    sys.exit(0)


if __name__ == "__main__":
    main()
