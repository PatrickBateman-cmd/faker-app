import json

import typer
from rich.progress import Progress, SpinnerColumn, TextColumn

from app.schemas.generation import (
    ConstraintConfig,
    DatasetDefinition,
    FieldDefinition,
    GenerateRequest,
)
from app.services.generation_engine import generate_datasets

from cli.common import console, get_state, output_result

app = typer.Typer(
    name="generate",
    help="Generate synthetic datasets",
    no_args_is_help=True,
    invoke_without_command=True,
)


@app.callback(invoke_without_command=True)
def generate(
    ctx: typer.Context,
    name: str = typer.Option(..., "--name", "-n", help="Dataset name"),
    rows: int = typer.Option(100, "--rows", "-r", help="Number of rows", min=1, max=100000),
    template: str = typer.Option(None, "--template", "-t", help="Template name from library"),
    fields_json: str = typer.Option(None, "--fields-json", "-j", help="Inline JSON field definitions"),
    fields_file: str = typer.Option(None, "--fields-file", "-F", help="Path to JSON file with field definitions"),
    homogeneity: int = typer.Option(50, "--homogeneity", "-h", help="Homogeneity percentage (1-100)", min=1, max=100),
    seed: int = typer.Option(None, "--seed", "-s", help="Master seed (random if omitted)"),
    datasets_count: int = typer.Option(1, "--datasets", "-D", help="Number of datasets to generate (1-4)", min=1, max=4),
    datasets_file: str = typer.Option(None, "--datasets-file", help="JSON file with multiple dataset definitions"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress progress bar"),
    fmt: str = typer.Option("table", "--format", "-f", help="Output format"),
    db: str = typer.Option(None, "--db", "-d", help="DuckDB path override"),
) -> None:
    """Generate synthetic datasets from field definitions or a template."""
    if ctx.invoked_subcommand is not None:
        return

    state = get_state()
    state.ensure_db(db=db)

    if datasets_file:
        with open(datasets_file) as f:
            raw = f.read()
        defs_data = json.loads(raw)
        if isinstance(defs_data, dict):
            defs_data = [defs_data]
    elif template:
        from app.services.template_library import get_template

        tpl = get_template(template)
        if not tpl:
            console.print(f"[red]Error:[/red] Template '{template}' not found")
            raise typer.Exit(code=1)

        defs_data = []
        for i in range(datasets_count):
            tpl_name = name if datasets_count == 1 else f"{name}_{i + 1}"
            defs_data.append({
                "name": tpl_name,
                "rows": rows,
                "template": template,
                    "fields": [
                    {
                        "name": f.name,
                        "type": f.type if f.type else "string",
                        "generator": f.generator if f.generator else "text",
                        "null_probability": f.null_probability,
                        "constraint": _constraint_to_dict(f.constraint) if f.constraint else None,
                        "condition": f.condition,
                    }
                    for f in tpl.fields
                ],
            })
    elif fields_json:
        fields = json.loads(fields_json)
        defs_data = [{
            "name": name,
            "rows": rows,
            "fields": fields,
        }]
    elif fields_file:
        with open(fields_file) as f:
            fields = json.loads(f)
        defs_data = [{
            "name": name,
            "rows": rows,
            "fields": fields,
        }]
    else:
        console.print("[red]Error:[/red] One of --template, --fields-json, --fields-file, or --datasets-file is required")
        raise typer.Exit(code=1)

    dataset_defs = [_parse_dataset_def(d) for d in defs_data]

    request = GenerateRequest(
        datasets=dataset_defs,
        homogeneity=homogeneity,
        seed=seed,
    )

    if not quiet:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            progress.add_task(description="Generating...", total=None)
            resp = generate_datasets(request)
    else:
        resp = generate_datasets(request)

    json_data = resp.model_dump() if hasattr(resp, "model_dump") else resp
    rows_out = []
    for ds in resp.datasets:
        rows_out.append([
            ds.dataset_id[:8] + "...",
            ds.name,
            str(ds.row_count),
            ", ".join(ds.columns[:5]) + ("..." if len(ds.columns) > 5 else ""),
        ])

    output_result(
        f"Generated ({len(resp.datasets)} dataset(s))",
        ["ID", "Name", "Rows", "Columns"],
        rows_out,
        fmt,
        json_data=json_data,
    )


def _parse_dataset_def(d: dict) -> DatasetDefinition:
    fields = []
    for f in d.get("fields", []):
        constraint = None
        if f.get("constraint"):
            constraint = ConstraintConfig(**f["constraint"])
        fields.append(
            FieldDefinition(
                name=f["name"],
                type=f.get("type", "string"),
                generator=f.get("generator", "text"),
                constraint=constraint,
                null_probability=f.get("null_probability"),
                condition=f.get("condition"),
            )
        )
    return DatasetDefinition(
        name=d.get("name", "Untitled"),
        rows=d.get("rows", 100),
        template=d.get("template"),
        fields=fields,
    )


def _constraint_to_dict(c) -> dict | None:
    return {
        "min": c.min,
        "max": c.max,
        "min_age": c.min_age,
        "max_age": c.max_age,
        "values": c.values,
        "weights": c.weights,
        "right_digits": c.right_digits,
        "format": c.format,
        "start": c.start,
        "end": c.end,
    }
