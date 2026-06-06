import pathlib

import typer

from app.services.template_library import (
    create_template as _create,
    delete_template as _delete,
    get_template,
    list_templates as _list,
)

from cli.common import console, output_result

app = typer.Typer(help="Manage templates", no_args_is_help=True)


@app.command(name="list")
def list_templates(
    fmt: str = typer.Option("table", "--format", "-f", help="Output format"),
) -> None:
    """List all templates from the library."""
    templates = _list()
    if not templates:
        console.print("[yellow]No templates found.[/yellow]")
        return

    rows = [
        [t.name, t.category, t.description or "", str(t.field_count)]
        for t in templates
    ]

    output_result(
        "Templates",
        ["Name", "Category", "Description", "Fields"],
        rows,
        fmt,
        json_data=[t.model_dump() for t in templates],
    )


@app.command(name="show")
def show_template(
    name: str = typer.Argument(..., help="Template name"),
    fmt: str = typer.Option("table", "--format", "-f", help="Output format"),
) -> None:
    """Show template details and its fields."""
    tpl = get_template(name)
    if not tpl:
        console.print(f"[red]Error:[/red] Template '{name}' not found")
        raise typer.Exit(code=1)

    console.print(f"[bold cyan]Template:[/bold cyan] {tpl.name}")
    console.print(f"[bold]Category:[/bold] {tpl.category}")
    console.print(f"[bold]Description:[/bold] {tpl.meta.description}")
    console.print()

    field_rows = [
        [
            f.name,
            f.type,
            f.generator,
            str(f.constraint.min) if f.constraint and f.constraint.min is not None else "",
            str(f.constraint.max) if f.constraint and f.constraint.max is not None else "",
            f.constraint.values or "" if f.constraint else "",
        ]
        for f in tpl.fields
    ]

    output_result(
        f"Fields ({len(tpl.fields)})",
        ["Name", "Type", "Generator", "Min", "Max", "Values"],
        field_rows,
        fmt,
        json_data=tpl.model_dump(),
    )


@app.command(name="create")
def create_template(
    xml_file: str = typer.Argument(..., help="Path to XML template file"),
    fmt: str = typer.Option("table", "--format", "-f", help="Output format"),
) -> None:
    """Create a template from an XML file."""
    path = pathlib.Path(xml_file)
    if not path.exists():
        console.print(f"[red]Error:[/red] File '{xml_file}' not found")
        raise typer.Exit(code=1)

    xml_content = path.read_text(encoding="utf-8")
    try:
        tpl = _create(xml_content)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1) from e
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1) from e

    rows = [[tpl.name, tpl.category, tpl.meta.description, str(len(tpl.fields))]]
    output_result(
        "Template Created",
        ["Name", "Category", "Description", "Fields"],
        rows,
        fmt,
        json_data=tpl.model_dump(),
    )


@app.command(name="delete")
def delete_template(
    name: str = typer.Argument(..., help="Template name"),
) -> None:
    """Delete a template from the library."""
    if _delete(name):
        console.print(f"[green]Template '{name}' deleted[/green]")
    else:
        console.print(f"[red]Error:[/red] Template '{name}' not found")
        raise typer.Exit(code=1)
