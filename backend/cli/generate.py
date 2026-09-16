import json

import typer
from rich.progress import Progress, SpinnerColumn, TextColumn

from app.schemas.generation import (
    ConstraintConfig,
    DatasetDefinition,
    FieldBreakConfig,
    FieldDefinition,
    GenerateRequest,
    GroupConfig,
)
from app.services import generation_engine
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
    name: str = typer.Option(None, "--name", "-n", help="Dataset name"),
    rows: int = typer.Option(100, "--rows", "-r", help="Number of rows", min=1, max=100000),
    template: str = typer.Option(None, "--template", "-t", help="Template name from library"),
    fields_json: str = typer.Option(None, "--fields-json", "-j", help="Inline JSON field definitions"),
    fields_file: str = typer.Option(None, "--fields-file", "-F", help="Path to JSON file with field definitions"),
    homogeneity: int = typer.Option(50, "--homogeneity", "-h", help="Homogeneity percentage (1-100)", min=1, max=100),
    seed: int = typer.Option(None, "--seed", "-s", help="Master seed (random if omitted)"),
    datasets_count: int = typer.Option(1, "--datasets", "-D", help="Number of datasets to generate (1-4)", min=1, max=4),
    datasets_file: str = typer.Option(None, "--datasets-file", help="JSON file with multiple dataset definitions"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress progress bar"),
    groups: int = typer.Option(None, "--groups", "-g", help="Number of parent groups for parent-child generation"),
    split_pct: float = typer.Option(100.0, "--split-pct", help="% of rows in parent groups (rest are flat, default 100)"),
    parent_fields_json: str = typer.Option(None, "--parent-fields-json", help="Inline JSON parent field definitions (for grouped mode)"),
    child_fields_json: str = typer.Option(None, "--child-fields-json", help="Inline JSON child field definitions (for grouped mode)"),
    fmt: str = typer.Option("table", "--format", "-f", help="Output format"),
    db: str = typer.Option(None, "--db", "-d", help="DuckDB path override"),
    reconciliation_mode: bool = typer.Option(False, "--reconciliation-mode", help="Lock this batch into reconciliation mode: full overlap + optional intentional breaks"),
    exact_fields: str = typer.Option(None, "--exact-fields", help="Comma-separated field names shared across datasets; first is the join key"),
    overlap_ratio: float = typer.Option(0.0, "--overlap-ratio", help="Fraction of rows drawn from the shared pool (0.0-1.0)", min=0.0, max=1.0),
    field_breaks_json: str = typer.Option(None, "--field-breaks-json", help="Inline JSON list of field break configs (requires --reconciliation-mode)"),
) -> None:
    """Generate synthetic datasets from field definitions or a template."""
    if ctx.invoked_subcommand is not None:
        return

    if name is None:
        console.print("[red]Error:[/red] --name is required")
        raise typer.Exit(code=1)

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
    elif groups is not None:
        defs_data = [{
            "name": name,
            "rows": rows,
            "fields": [],
        }]
    else:
        console.print("[red]Error:[/red] One of --template, --fields-json, --fields-file, --datasets-file, or --groups is required")
        raise typer.Exit(code=1)

    dataset_defs = [_parse_dataset_def(d) for d in defs_data]

    if reconciliation_mode and overlap_ratio != 0.0:
        console.print("[red]Error:[/red] --overlap-ratio cannot be combined with --reconciliation-mode (it is forced to 1.0 automatically)")
        raise typer.Exit(code=1)

    exact_fields_list = [s.strip() for s in exact_fields.split(",") if s.strip()] if exact_fields else []
    field_breaks_list = (
        [FieldBreakConfig(**fb) for fb in json.loads(field_breaks_json)] if field_breaks_json else []
    )

    if groups is not None:
        pf = json.loads(parent_fields_json) if parent_fields_json else []
        cf = json.loads(child_fields_json) if child_fields_json else []
        group_cfg = GroupConfig(
            num_groups=groups,
            split_pct=split_pct,
            parent_fields=[_parse_field(f) for f in pf],
            child_fields=[_parse_field(f) for f in cf],
        )
        for dd in dataset_defs:
            dd.group_config = group_cfg

    request = GenerateRequest(
        datasets=dataset_defs,
        homogeneity=homogeneity,
        seed=seed,
        overlap_ratio=overlap_ratio,
        exact_fields=exact_fields_list,
        reconciliation_mode=reconciliation_mode,
        field_breaks=field_breaks_list,
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

    json_data = resp.model_dump()
    rows_out = []
    for ds in resp.datasets:
        rows_out.append([
            ds.dataset_id,
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


def _parse_field(f: dict) -> FieldDefinition:
    constraint = None
    if f.get("constraint"):
        constraint = ConstraintConfig(**f["constraint"])
    return FieldDefinition(
        name=f["name"],
        type=f.get("type", "string"),
        generator=f.get("generator", "text"),
        constraint=constraint,
        null_probability=f.get("null_probability"),
        condition=f.get("condition"),
        unique=f.get("unique", False),
        formula=f.get("formula"),
    )


def _parse_dataset_def(d: dict) -> DatasetDefinition:
    fields = [_parse_field(f) for f in d.get("fields", [])]
    group_cfg = None
    if d.get("group_config"):
        gc = d["group_config"]
        group_cfg = GroupConfig(
            num_groups=gc["num_groups"],
            split_pct=gc.get("split_pct", 100),
            parent_fields=[_parse_field(f) for f in gc.get("parent_fields", [])],
            child_fields=[_parse_field(f) for f in gc.get("child_fields", [])],
        )
    return DatasetDefinition(
        name=d.get("name", "Untitled"),
        rows=d.get("rows", 100),
        template=d.get("template"),
        fields=fields,
        group_config=group_cfg,
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


@app.command("breaks")
def breaks_cmd(
    run_id: int = typer.Argument(..., help="Run ID returned by `faker generate`"),
    fmt: str = typer.Option("table", "--format", "-f", help="Output format"),
    db: str = typer.Option(None, "--db", "-d", help="DuckDB path override"),
) -> None:
    """Show the reconciliation ground truth (intentional breaks) for a run."""
    state = get_state()
    state.ensure_db(db=db)

    records = generation_engine.get_recon_breaks(run_id)
    rows_out = [
        [str(r.id), r.dataset_id, r.field_name, str(r.join_key_value), str(r.true_value), str(r.broken_value), r.break_style]
        for r in records
    ]
    output_result(
        f"Reconciliation breaks for run {run_id} ({len(records)})",
        ["ID", "Dataset", "Field", "Join Key", "True Value", "Broken Value", "Style"],
        rows_out,
        fmt,
        json_data=[r.model_dump() for r in records],
    )
