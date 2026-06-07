import typer

from app.schemas.aggregation import (
    AggregateRequest,
    AggregationDef,
    DedupRequest,
    OrderByDef,
)
from app.services.transform_service import aggregate_dataset, dedup_dataset

from cli.common import console, get_state, output_result

app = typer.Typer(help="Aggregate or deduplicate datasets", no_args_is_help=True)


@app.command(name="aggregate")
def aggregate(
    dataset_id: str = typer.Argument(..., help="Source dataset ID"),
    name: str = typer.Option(..., "--name", "-n", help="Result dataset name"),
    group_by: str = typer.Option(..., "--group-by", "-g", help="Comma-separated column names"),
    agg: list[str] = typer.Option(
        ..., "--agg", "-a",
        help="Aggregation spec: column:function:alias (repeatable, e.g. -a amount:sum:total)",
    ),
    fmt: str = typer.Option("table", "--format", "-f", help="Output format"),
    db: str = typer.Option(None, "--db", "-d", help="DuckDB path override"),
) -> None:
    """Aggregate a dataset by group-by columns with aggregate functions."""
    state = get_state()
    state.ensure_db(db=db)

    aggs = []
    for spec in agg:
        parts = spec.split(":")
        if len(parts) == 2:
            col, func = parts
            alias = f"{func}_{col}"
        elif len(parts) == 3:
            col, func, alias = parts
        else:
            console.print(f"[red]Error:[/red] Invalid agg spec '{spec}'. Use column:function:alias")
            raise typer.Exit(code=1)
        aggs.append(AggregationDef(column=col, function=func, alias=alias))

    request = AggregateRequest(name=name, group_by=[c.strip() for c in group_by.split(",")], aggregations=aggs)

    try:
        result = aggregate_dataset(dataset_id, request)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1) from e

    rows = [[
        result.dataset_id,
        result.name,
        str(result.row_count),
        ", ".join(result.columns),
    ]]
    output_result(
        "Aggregation Result",
        ["ID", "Name", "Rows", "Columns"],
        rows,
        fmt,
        json_data=result.model_dump(),
    )


@app.command(name="dedup")
def dedup(
    dataset_id: str = typer.Argument(..., help="Source dataset ID"),
    name: str = typer.Option(..., "--name", "-n", help="Result dataset name"),
    keys: str = typer.Option(..., "--keys", "-k", help="Comma-separated key columns"),
    strategy: str = typer.Option(
        "keep_first", "--strategy", "-s",
        help="Strategy: keep_first, keep_last, keep_none",
    ),
    order_by: str = typer.Option(None, "--order-by", "-o", help="Order spec: column:asc (or :desc)"),
    fmt: str = typer.Option("table", "--format", "-f", help="Output format"),
    db: str = typer.Option(None, "--db", "-d", help="DuckDB path override"),
) -> None:
    """Deduplicate a dataset by key columns."""
    state = get_state()
    state.ensure_db(db=db)

    if strategy not in ("keep_first", "keep_last", "keep_none"):
        console.print("[red]Error:[/red] Strategy must be keep_first, keep_last, or keep_none")
        raise typer.Exit(code=1)

    order_by_def = None
    if order_by:
        parts = order_by.split(":")
        col = parts[0]
        direction = parts[1] if len(parts) > 1 else "desc"
        if direction not in ("asc", "desc"):
            console.print("[red]Error:[/red] Order direction must be asc or desc")
            raise typer.Exit(code=1)
        order_by_def = OrderByDef(column=col, direction=direction)

    request = DedupRequest(
        name=name,
        keys=[c.strip() for c in keys.split(",")],
        strategy=strategy,
        order_by=order_by_def,
    )

    try:
        result = dedup_dataset(dataset_id, request)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1) from e

    rows = [[
        result.dataset_id,
        result.name,
        str(result.row_count),
        ", ".join(result.columns),
    ]]
    output_result(
        "Dedup Result",
        ["ID", "Name", "Rows", "Columns"],
        rows,
        fmt,
        json_data=result.model_dump(),
    )
