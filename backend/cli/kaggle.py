from __future__ import annotations

from typing import Optional

import typer
from rich.table import Table

from cli.common import console, get_state, output_result

app = typer.Typer(help="Import datasets from Kaggle", no_args_is_help=True)


@app.command(name="search")
def search(
    query: str = typer.Argument(..., help="Search query"),
    page: int = typer.Option(1, "--page", "-p", help="Page number"),
    per_page: int = typer.Option(20, "--per-page", help="Results per page"),
    format: str = typer.Option("table", "--format", "-f", help="Output format: table or json"),
) -> None:
    """Search for datasets on Kaggle."""
    from app.services import kaggle_service

    state = get_state()
    state.ensure_db()
    try:
        result = kaggle_service.search_datasets(query, page=page, per_page=per_page)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1) from e

    datasets = result["datasets"]
    if not datasets:
        console.print("[yellow]No datasets found.[/yellow]")
        return

    output_result(
        f"Kaggle Search: '{query}' (page {page})",
        ["Ref", "Title", "Files", "Downloads", "Usability"],
        [
            [
                d["ref"],
                d["title"][:50],
                str(d["file_count"]),
                str(d["download_count"]),
                f"{d['usability_rating']:.2f}",
            ]
            for d in datasets
        ],
        format,
    )


@app.command(name="files")
def list_files(
    ref: str = typer.Argument(..., help="Dataset ref as owner/slug"),
    format: str = typer.Option("table", "--format", "-f"),
) -> None:
    """List CSV files in a Kaggle dataset."""
    from app.services import kaggle_service

    if "/" not in ref:
        console.print("[red]Error:[/red] ref must be in owner/slug format")
        raise typer.Exit(code=1)
    owner, slug = ref.split("/", 1)

    state = get_state()
    state.ensure_db()
    try:
        files = kaggle_service.list_files(owner, slug)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1) from e

    if not files:
        console.print("[yellow]No CSV files found in this dataset.[/yellow]")
        return

    output_result(
        f"Files in {ref}",
        ["Name", "Size (bytes)", "Created"],
        [[f["name"], str(f["size"]), f["creation_date"][:10]] for f in files],
        format,
    )


@app.command(name="import")
def import_dataset(
    ref: str = typer.Argument(..., help="Dataset ref as owner/slug"),
    file_name: str = typer.Argument(..., help="CSV file name to import"),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="Dataset name override"),
    max_rows: Optional[int] = typer.Option(None, "--max-rows", help="Row limit"),
    format: str = typer.Option("table", "--format", "-f"),
) -> None:
    """Download and import a Kaggle CSV into a dataset."""
    from app.services import kaggle_service

    if "/" not in ref:
        console.print("[red]Error:[/red] ref must be in owner/slug format")
        raise typer.Exit(code=1)
    owner, slug = ref.split("/", 1)

    state = get_state()
    state.ensure_db()
    console.print(f"Importing [cyan]{owner}/{slug}/{file_name}[/cyan] from Kaggle…")
    try:
        result = kaggle_service.import_file(
            owner=owner,
            slug=slug,
            file_name=file_name,
            dataset_name=name,
            max_rows=max_rows,
        )
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1) from e

    output_result(
        "Imported Dataset",
        ["Field", "Value"],
        [
            ["Dataset ID", result["dataset_id"]],
            ["Name", result["name"]],
            ["Rows", str(result["row_count"])],
            ["Columns", str(len(result["columns"]))],
        ],
        format,
    )
