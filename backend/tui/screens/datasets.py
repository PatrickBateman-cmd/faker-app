import json

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Input, Label, Static

from app.core.database import DuckDBManager
from app.services.dataset_service import delete_dataset, get_dataset, list_datasets

from tui.widgets.dataset_table import DatasetTable


class DatasetsScreen(Screen):
    def compose(self) -> ComposeResult:
        yield Label("[bold]Datasets[/bold]", id="ds-title")
        with Horizontal():
            with Vertical(id="ds-list", classes="sidebar"):
                yield Input(placeholder="Search...", id="ds-search")
                yield Static("", id="ds-items")
            with Vertical(id="ds-detail", classes="main-panel"):
                yield Static("Select a dataset", id="ds-info")
                yield DatasetTable(id="ds-table")
                with Horizontal(classes="ds-actions"):
                    yield Button("Export CSV", id="export-csv")
                    yield Button("Export JSONL", id="export-jsonl")
                    yield Button("Delete", id="delete-ds", variant="error")

    def on_mount(self) -> None:
        self._refresh_list()

    def _refresh_list(self) -> None:
        try:
            datasets = list_datasets()
            items = "\n".join(
                f"  [bold]{d['name']}[/] [dim]({d['row_count']} rows, {d['dataset_id']})[/dim]"
                for d in datasets
            )
            self.query_one("#ds-items", Static).update(items)
        except Exception as e:
            self.query_one("#ds-items", Static).update(f"[red]{e}[/]")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn = event.button.id
        if btn in ("export-csv", "export-jsonl"):
            self._export(btn.split("-")[1])
        elif btn == "delete-ds":
            self._confirm_delete()

    def _export(self, fmt: str) -> None:
        from app.services.export_service import export_dataset
        dataset_id = getattr(self, "_selected_id", None)
        if not dataset_id:
            self.query_one("#ds-info", Static).update("[red]No dataset selected[/]")
            return
        path = f"/tmp/{dataset_id}.{fmt}"
        try:
            export_dataset(dataset_id, fmt, path)
            self.query_one("#ds-info", Static).update(f"[green]Exported to {path}[/]")
        except Exception as e:
            self.query_one("#ds-info", Static).update(f"[red]{e}[/]")

    def _confirm_delete(self) -> None:
        dataset_id = getattr(self, "_selected_id", None)
        if not dataset_id:
            return
        try:
            delete_dataset(dataset_id)
            self._selected_id = None
            self._refresh_list()
            self.query_one("#ds-info", Static).update("[dim]Dataset deleted[/]")
        except Exception as e:
            self.query_one("#ds-info", Static).update(f"[red]{e}[/]")
