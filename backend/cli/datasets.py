import typer

from app.services.dataset_service import (
    delete_dataset as _delete,
    get_dataset_rows,
    list_datasets as _list,
    rename_dataset as _rename,
)
from app.services.export_service import export_csv, export_jsonl, export_parquet, export_xlsx

from cli.common import console, get_state, output_result

app = typer.Typer(help="Manage datasets", no_args_is_help=True)


@app.command(name="list")
def list_datasets(
    fmt: str = typer.Option("table", "--format", "-f", help="Output format"),
    db: str = typer.Option(None, "--db", "-d", help="DuckDB path override"),
) -> None:
    """List all generated datasets."""
    state = get_state()
    state.ensure_db(db=db)
    datasets = _list()

    if not datasets:
        console.print("[yellow]No datasets found. Generate one with 'faker generate'[/yellow]")
        return

    rows = [
        [
            d["dataset_id"][:8] + "...",
            d["name"],
            str(d["row_count"]),
            ", ".join(d["columns"][:5]) + ("..." if len(d["columns"]) > 5 else ""),
            str(d["created_at"])[:19] if d["created_at"] else "",
        ]
        for d in datasets
    ]

    output_result(
        "Datasets",
        ["ID", "Name", "Rows", "Columns", "Created"],
        rows,
        fmt,
        json_data=datasets,
    )


@app.command(name="view")
def view_dataset(
    dataset_id: str = typer.Argument(..., help="Dataset ID"),
    page: int = typer.Option(1, "--page", "-p", help="Page number", min=1),
    per_page: int = typer.Option(50, "--per-page", "-P", help="Rows per page", min=1, max=500),
    fmt: str = typer.Option("table", "--format", "-f", help="Output format"),
    db: str = typer.Option(None, "--db", "-d", help="DuckDB path override"),
) -> None:
    """View rows of a dataset."""
    state = get_state()
    state.ensure_db(db=db)
    result = get_dataset_rows(dataset_id, page=page, per_page=per_page)

    if not result["meta"]:
        console.print(f"[red]Error:[/red] Dataset '{dataset_id}' not found")
        raise typer.Exit(code=1)

    meta = result["meta"]
    rows_data = result["rows"]
    total = result["total"]
    columns = meta["columns"] if meta["columns"] else (list(rows_data[0].keys()) if rows_data else [])

    if not rows_data:
        console.print("[yellow]No rows found.[/yellow]")
        return

    table_rows = [[str(r.get(c, "")) for c in columns] for r in rows_data]

    output_result(
        f"{meta['name']} (page {page}/{max(1, (total + per_page - 1) // per_page)} — {total} rows)",
        columns,
        table_rows,
        fmt,
        json_data={"meta": meta, "rows": rows_data, "total": total, "page": page, "per_page": per_page},
    )


@app.command(name="delete")
def delete_dataset(
    dataset_id: str = typer.Argument(..., help="Dataset ID"),
    db: str = typer.Option(None, "--db", "-d", help="DuckDB path override"),
) -> None:
    """Delete a dataset."""
    state = get_state()
    state.ensure_db(db=db)
    if _delete(dataset_id):
        console.print(f"[green]Dataset '{dataset_id}' deleted[/green]")
    else:
        console.print(f"[red]Error:[/red] Dataset '{dataset_id}' not found")
        raise typer.Exit(code=1)


@app.command(name="rename")
def rename_dataset(
    dataset_id: str = typer.Argument(..., help="Dataset ID"),
    name: str = typer.Option(..., "--name", "-n", help="New dataset name"),
    db: str = typer.Option(None, "--db", "-d", help="DuckDB path override"),
) -> None:
    """Rename a dataset."""
    state = get_state()
    state.ensure_db(db=db)
    if _rename(dataset_id, name):
        console.print(f"[green]Dataset renamed to '{name}'[/green]")
    else:
        console.print(f"[red]Error:[/red] Dataset '{dataset_id}' not found")
        raise typer.Exit(code=1)


@app.command(name="export")
def export_dataset(
    dataset_id: str = typer.Argument(..., help="Dataset ID"),
    format: str = typer.Argument("csv", help="Export format: csv, parquet, xlsx, jsonl"),
    output: str = typer.Option(None, "--output", "-o", help="Output file path"),
    db: str = typer.Option(None, "--db", "-d", help="DuckDB path override"),
) -> None:
    """Export a dataset to CSV, Parquet, or XLSX."""
    state = get_state()
    state.ensure_db(db=db)

    fmt_map = {"csv": export_csv, "parquet": export_parquet, "xlsx": export_xlsx, "jsonl": export_jsonl}
    exporter = fmt_map.get(format.lower())
    if not exporter:
        console.print(f"[red]Error:[/red] Unsupported format '{format}'. Use csv, parquet, xlsx, or jsonl")
        raise typer.Exit(code=1)

    try:
        from rich.progress import Progress, SpinnerColumn, TextColumn
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            progress.add_task(description="Exporting...", total=None)
            filepath = exporter(dataset_id)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1) from e

    if output:
        import shutil
        shutil.copy(filepath, output)
        console.print(f"[green]Exported to:[/green] {output}")
    else:
        console.print(f"[green]Exported to:[/green] {filepath}")
