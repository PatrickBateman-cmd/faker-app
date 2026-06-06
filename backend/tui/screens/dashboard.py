from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Label, Static

from app.core.database import DuckDBManager


class StatCard(Static):
    def __init__(self, label: str, value: str, color: str = "cyan") -> None:
        super().__init__()
        self._label = label
        self._value = value
        self._color = color

    def on_mount(self) -> None:
        self.styles.border = ("solid", self._color)
        self.styles.padding = (1, 2)
        self.styles.margin = (0, 1)
        self.render_content()

    def render_content(self) -> None:
        self.update(f"[bold {self._color}]{self._value}[/]\n[dim]{self._label}[/]")


class DashboardScreen(Screen):
    def compose(self) -> ComposeResult:
        yield Label("[bold cyan]Faker App[/bold cyan]  —  Synthetic Data Generator", id="title")
        yield Label("[dim]Terminal User Interface[/dim]", id="subtitle")
        with Horizontal(id="stats-row"):
            yield StatCard("Total Datasets", "...", "cyan")
            yield StatCard("Total Templates", "...", "green")
            yield StatCard("Total Rows Generated", "...", "yellow")
        yield Static("[bold]Quick Navigation[/bold]", classes="section-title")
        yield Label(
            "[dim]"
            "  [bold]1[/] / [bold]g d[/]  Dashboard    [bold]4[/] / [bold]g f[/]  Financial\n"
            "  [bold]2[/] / [bold]g g[/]  Generation   [bold]5[/] / [bold]g t[/]  Templates\n"
            "  [bold]3[/] / [bold]g s[/]  Datasets     [bold]6[/] / [bold]g i[/]  ISO 20022\n"
            "\n"
            "  [bold]q[/]          Quit\n"
            "[/dim]",
            id="nav-hints",
        )

    def on_mount(self) -> None:
        self._load_stats()

    def _load_stats(self) -> None:
        try:
            db = DuckDBManager.get_instance()
            ds_count = db.execute("SELECT COUNT(*) FROM metadata_datasets").fetchone()[0]
            tpl_count = db.execute("SELECT COUNT(*) FROM metadata_templates").fetchone()[0]
            row_sum = db.execute("SELECT COALESCE(SUM(row_count), 0) FROM metadata_datasets").fetchone()[0]
            cards = self.query(StatCard)
            if len(cards) >= 3:
                cards[0].render_content()
                cards[0].update(f"[bold cyan]{ds_count}[/]\n[dim]Total Datasets[/]")
                cards[1].update(f"[bold green]{tpl_count}[/]\n[dim]Total Templates[/]")
                cards[2].update(f"[bold yellow]{row_sum:,}[/]\n[dim]Total Rows Generated[/]")
        except Exception:
            pass
