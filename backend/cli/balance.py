import json as _json

import typer

from app.schemas.balance import BalanceDeriveRequest
from app.schemas.generation import FieldBreakConfig
from app.services.balance_service import derive_balances

from cli.common import console, get_state, output_result

app = typer.Typer(help="Derive daily account balances with optional injected breaks", no_args_is_help=True)


@app.command(name="derive")
def derive(
    dataset_id: str = typer.Argument(..., help="Source transactions dataset ID"),
    name: str = typer.Option(..., "--name", "-n", help="Result balance dataset name"),
    account_fields: str = typer.Option(..., "--account-fields", help="Comma-separated hierarchy columns"),
    currency_field: str = typer.Option("currency", "--currency-field"),
    date_field: str = typer.Option("transaction_date", "--date-field"),
    amount_field: str = typer.Option("amount", "--amount-field"),
    direction_field: str = typer.Option("transaction_type", "--direction-field"),
    credit_values: str = typer.Option("Credit,Deposit,Refund", "--credit-values"),
    debit_values: str = typer.Option("Debit,Withdrawal,Payment,Transfer", "--debit-values"),
    start_date: str = typer.Option(None, "--start-date", help="Default: MIN(date_field) in source"),
    end_date: str = typer.Option(None, "--end-date", help="Default: MAX(date_field) in source"),
    opening_balance_seed: float = typer.Option(
        None,
        "--opening-balance-seed",
        help="Reuse the seed returned by a prior 'faker balance derive' call to align both sides",
    ),
    balance_breaks_json: str = typer.Option(None, "--balance-breaks-json", help="JSON list of FieldBreakConfig"),
    fmt: str = typer.Option("table", "--format", "-f", help="Output format"),
    db: str = typer.Option(None, "--db", "-d", help="DuckDB path override"),
) -> None:
    """Derive a daily opening/closing balance dataset from a transactions dataset."""
    state = get_state()
    state.ensure_db(db=db)

    balance_breaks: list[FieldBreakConfig] = []
    if balance_breaks_json:
        try:
            balance_breaks = [FieldBreakConfig(**item) for item in _json.loads(balance_breaks_json)]
        except (ValueError, TypeError) as e:
            console.print(f"[red]Error:[/red] Invalid --balance-breaks-json: {e}")
            raise typer.Exit(code=1) from e

    request = BalanceDeriveRequest(
        name=name,
        account_fields=[c.strip() for c in account_fields.split(",") if c.strip()],
        currency_field=currency_field,
        date_field=date_field,
        amount_field=amount_field,
        direction_field=direction_field,
        credit_values=[c.strip() for c in credit_values.split(",") if c.strip()],
        debit_values=[c.strip() for c in debit_values.split(",") if c.strip()],
        start_date=start_date,
        end_date=end_date,
        opening_balance_seed=opening_balance_seed,
        balance_breaks=balance_breaks,
    )

    try:
        result = derive_balances(dataset_id, request)
    except (LookupError, ValueError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1) from e

    if fmt != "json":
        console.print(f"[cyan]Opening balance seed:[/cyan] {result.opening_balance_seed}")
        console.print("[dim]Reuse it with --opening-balance-seed on the paired call to align both sides.[/dim]")

    rows = [[
        result.dataset_id,
        result.name,
        str(result.row_count),
        f"{result.start_date} to {result.end_date}",
        str(result.break_count),
    ]]
    output_result(
        "Balance Derivation Result",
        ["ID", "Name", "Rows", "Date range", "Breaks"],
        rows,
        fmt,
        json_data=result.model_dump(),
    )
