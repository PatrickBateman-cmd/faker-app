import typer
from app.core.database import DuckDBManager

app = typer.Typer(name="tui", help="Launch the terminal user interface")


@app.callback(invoke_without_command=True)
def tui(
    db: str = typer.Option(None, "--db", "-d", help="DuckDB path override"),
) -> None:
    """Launch the terminal user interface."""
    from cli.common import get_state

    state = get_state()
    state.ensure_db(db=db)

    from tui.app import FakerTUI
    app = FakerTUI()
    app.run()
