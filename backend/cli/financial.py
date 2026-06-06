import typer

from app.services.financial_service import batch_history, batch_to_dataset, get_history, get_quote

from cli.common import console, get_state, output_result

app = typer.Typer(help="Financial data via yfinance", no_args_is_help=True)


@app.command(name="quote")
def quote(
    symbol: str = typer.Argument(..., help="Stock symbol (e.g. AAPL)"),
    fmt: str = typer.Option("table", "--format", "-f", help="Output format"),
) -> None:
    """Get a real-time quote for a symbol."""
    with console.status(f"Fetching quote for {symbol}..."):
        try:
            q = get_quote(symbol)
        except ValueError as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(code=1) from e

    rows = [[
        q["symbol"],
        q["shortName"],
        f"{q['currency']} {q['regularMarketPrice']:.2f}",
        f"{q['change']:+.2f}",
        f"{q['changePercent']:+.2f}%",
        str(q["volume"]),
    ]]
    output_result(
        f"Quote: {symbol}",
        ["Symbol", "Name", "Price", "Change", "Change %", "Volume"],
        rows,
        fmt,
        json_data=q,
    )


@app.command(name="history")
def history(
    symbol: str = typer.Argument(..., help="Stock symbol"),
    period: str = typer.Option("1mo", "--period", "-p", help="Period: 1d, 5d, 1mo, 3mo, 6mo, 1y, 5y, max"),
    interval: str = typer.Option("1d", "--interval", "-i", help="Interval: 1m, 2m, 5m, 15m, 30m, 60m, 1d, 1wk, 1mo"),
    fmt: str = typer.Option("table", "--format", "-f", help="Output format"),
) -> None:
    """Get historical price data for a symbol."""
    with console.status(f"Fetching history for {symbol} ({period})..."):
        try:
            data = get_history(symbol, period=period, interval=interval)
        except ValueError as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(code=1) from e

    if not data:
        console.print(f"[yellow]No history data for {symbol}[/yellow]")
        return

    rows = [
        [
            r["date"],
            f"{r['open']:.2f}",
            f"{r['high']:.2f}",
            f"{r['low']:.2f}",
            f"{r['close']:.2f}",
            str(r["volume"]),
        ]
        for r in data[:50]
    ]

    output_result(
        f"History: {symbol} ({period}, {interval}) — showing {min(50, len(data))} of {len(data)} rows",
        ["Date", "Open", "High", "Low", "Close", "Volume"],
        rows,
        fmt,
        json_data=data,
    )


@app.command(name="batch")
def batch(
    symbols: str = typer.Argument(..., help="Comma-separated symbols (e.g. AAPL,MSFT,GOOG)"),
    name: str = typer.Option(None, "--name", "-n", help="Dataset name"),
    history: bool = typer.Option(False, "--history", help="Fetch full history instead of current snapshot"),
    period: str = typer.Option("1mo", "--period", "-p", help="History period (1d, 5d, 1mo, 3mo, 6mo, 1y, 5y, max)"),
    interval: str = typer.Option("1d", "--interval", "-i", help="History interval (1m, 5m, 15m, 30m, 60m, 1d, 1wk, 1mo)"),
    fmt: str = typer.Option("table", "--format", "-f", help="Output format"),
    db: str = typer.Option(None, "--db", "-d", help="DuckDB path override"),
) -> None:
    """Fetch data for multiple symbols and save as a dataset.

    Defaults to current snapshot (1 row/symbol). Use --history for time series.
    """
    state = get_state()
    state.ensure_db(db=db)

    symbol_list = [s.strip() for s in symbols.split(",") if s.strip()]
    if not symbol_list:
        console.print("[red]Error:[/red] At least one symbol required")
        raise typer.Exit(code=1)
    if len(symbol_list) > 50:
        console.print("[red]Error:[/red] Maximum 50 symbols allowed")
        raise typer.Exit(code=1)

    if history:
        label = f"history ({period}, {interval})"
        with console.status(f"Fetching history for {len(symbol_list)} symbols..."):
            try:
                result = batch_history(symbol_list, period=period, interval=interval, name=name)
            except ValueError as e:
                console.print(f"[red]Error:[/red] {e}")
                raise typer.Exit(code=1) from e
    else:
        label = "quotes"
        with console.status(f"Fetching quotes for {len(symbol_list)} symbols..."):
            try:
                result = batch_to_dataset(symbol_list, name=name)
            except ValueError as e:
                console.print(f"[red]Error:[/red] {e}")
                raise typer.Exit(code=1) from e

    rows = [[
        result.dataset_id[:8] + "...",
        result.name,
        str(result.row_count),
        ", ".join(result.columns),
    ]]
    output_result(
        f"Financial Batch Dataset ({label})",
        ["ID", "Name", "Rows", "Columns"],
        rows,
        fmt,
        json_data={
            "dataset_id": result.dataset_id,
            "name": result.name,
            "table_name": result.table_name,
            "row_count": result.row_count,
            "columns": result.columns,
        },
    )
    console.print(f"\n[green]View:[/green] faker datasets view {result.dataset_id}")
