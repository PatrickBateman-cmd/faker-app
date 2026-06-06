import typer

from cli.common import console, get_state

from cli import generate as _generate
from cli import datasets as _datasets
from cli import templates as _templates
from cli import iso20022 as _iso20022
from cli import financial as _financial
from cli import transform as _transform
from cli import tui as _tui

app = typer.Typer(
    name="faker",
    help="Faker App — synthetic dataset generator CLI",
    no_args_is_help=True,
)


@app.callback()
def main_callback(
    ctx: typer.Context,
    db: str = typer.Option(None, "--db", "-d", help="DuckDB path override (default from .env)"),
) -> None:
    state = get_state()
    if db:
        state.db_path = db


@app.command(name="init")
def init_db(
    db: str = typer.Option(None, "--db", "-d", help="DuckDB path override"),
) -> None:
    """Initialize DuckDB database (creates metadata tables)."""
    state = get_state()
    path = db or state.db_path
    console.print(f"Initializing DuckDB at: [yellow]{path}[/yellow]")
    try:
        state.ensure_db(db=db)
        console.print("[green]Done.[/green]")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1) from e


@app.command(name="info")
def info(
    db: str = typer.Option(None, "--db", "-d", help="DuckDB path override"),
) -> None:
    """Show database statistics."""
    from cli.common import output_result

    state = get_state()
    try:
        mgr = state.ensure_db(db=db)
        rows = mgr.execute("SELECT COUNT(*) FROM metadata_datasets").fetchone()
        dataset_count = rows[0] if rows else 0
        rows = mgr.execute("SELECT COUNT(*) FROM metadata_templates").fetchone()
        template_count = rows[0] if rows else 0
        rows = mgr.execute("SELECT COUNT(*) FROM metadata_runs").fetchone()
        run_count = rows[0] if rows else 0
    except Exception:
        dataset_count = template_count = run_count = 0

    output_result(
        "Database Info",
        ["Key", "Value"],
        [
            ["Database Path", state.db_path],
            ["Datasets", str(dataset_count)],
            ["Templates", str(template_count)],
            ["Runs", str(run_count)],
        ],
        "table",
    )


app.add_typer(_generate.app, name="generate", help="Generate synthetic datasets")
app.add_typer(_datasets.app, name="datasets", help="Manage datasets")
app.add_typer(_templates.app, name="templates", help="Manage templates")
app.add_typer(_iso20022.app, name="iso", help="ISO 20022 catalog")
app.add_typer(_financial.app, name="financial", help="Financial data via yfinance")
app.add_typer(_transform.app, name="transform", help="Aggregate or dedup datasets")
app.add_typer(_tui.app, name="tui", help="Launch terminal user interface")
