import json

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Input, Label, RichLog, Static

from app.core.database import DuckDBManager
from app.services.financial_service import batch_to_dataset, get_history, get_quote


def _braille_line(values: list[float], width: int = 60, height: int = 8) -> list[str]:
    if not values:
        return []
    mn, mx = min(values), max(values)
    rng = mx - mn if mx != mn else 1
    normalized = [(v - mn) / rng * (height - 1) for v in values]
    scaled = [round(height - 1 - n) for n in normalized]

    braille_dots = [" ", "⢀", "⢠", "⢰", "⢸", "⡀", "⣀", "⣠", "⣰", "⣸",
                    "⡄", "⣄", "⣤", "⣴", "⣼", "⡆", "⣆", "⣦", "⣶", "⣾",
                    "⡇", "⣇", "⣧", "⣷", "⣿"]
    lines: list[str] = []
    for row in range(height):
        line_chars: list[str] = []
        for i in range(width):
            idx = int(i * len(scaled) / width) if scaled else 0
            if idx >= len(scaled):
                break
            col = scaled[idx]
            if col == row:
                line_chars.append("⣿")
            elif col < row:
                line_chars.append("⣀")
            else:
                line_chars.append(" ")
        lines.append("".join(line_chars))
    return lines


class FinancialScreen(Screen):
    def compose(self) -> ComposeResult:
        yield Label("[bold]Financial[/bold]", id="fin-title")
        with Horizontal():
            yield Input(placeholder="Symbol (e.g. AAPL)", id="fin-symbol")
            yield Button("Quote", id="btn-quote")
            yield Button("History", id="btn-history")
        yield Static("", id="fin-quote")
        yield RichLog(id="fin-chart", highlight=True, markup=True)
        with Horizontal():
            yield Input(placeholder="Period (1mo)", id="fin-period", value="1mo")
            yield Input(placeholder="Interval (1d)", id="fin-interval", value="1d")
        with Horizontal():
            yield Input(placeholder="Symbols (comma)", id="fin-batch", value="AAPL,MSFT")
            yield Input(placeholder="Dataset name", id="fin-batch-name")
            yield Button("Batch Fetch", id="btn-batch")
        yield Static("", id="fin-result")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        symbol = self.query_one("#fin-symbol", Input).value.strip().upper()
        period = self.query_one("#fin-period", Input).value.strip()
        interval = self.query_one("#fin-interval", Input).value.strip()

        try:
            if event.button.id == "btn-quote" and symbol:
                q = get_quote(symbol)
                lines = (
                    f"[bold]{q['shortName']}[/] [dim]({q['symbol']})[/]\n"
                    f"Price: [bold]${q['regularMarketPrice']:.2f}[/]  "
                    f"Change: {'[green]' if q['change'] >= 0 else '[red]'}{q['change']:+.2f} ({q['changePercent']:+.2f}%)[/]\n"
                    f"Open: {q.get('regularMarketOpen', 'N/A')}  "
                    f"High: {q['dayHigh']:.2f}  Low: {q['dayLow']:.2f}\n"
                    f"Volume: {q['volume']:,}  Market Cap: {q.get('marketCap', 'N/A')}"
                )
                self.query_one("#fin-quote", Static).update(lines)

            elif event.button.id == "btn-history" and symbol:
                data = get_history(symbol, period=period, interval=interval)
                if not data:
                    self.query_one("#fin-quote", Static).update("[yellow]No history data[/]")
                    return
                closes = [r["close"] for r in data]
                lines = _braille_line(closes, width=60, height=8)
                chart = self.query_one("#fin-chart", RichLog)
                chart.clear()
                for l in reversed(lines):
                    chart.write(l)
                info = (f"[dim]{symbol} — {period}/{interval} — "
                        f"{len(data)} records — "
                        f"Low: ${min(closes):.2f} High: ${max(closes):.2f}[/]")
                self.query_one("#fin-quote", Static).update(info)

            elif event.button.id == "btn-batch":
                symbols_str = self.query_one("#fin-batch", Input).value
                batch_name = self.query_one("#fin-batch-name", Input).value or None
                symbols = [s.strip().upper() for s in symbols_str.split(",") if s.strip()]
                if symbols:
                    result = batch_to_dataset(symbols, name=batch_name)
                    self.query_one("#fin-result", Static).update(
                        f"[green]Saved:[/] {result.name} ({result.row_count} rows, {len(result.columns)} cols)"
                    )

        except Exception as e:
            self.query_one("#fin-quote", Static).update(f"[red]{e}[/]")
