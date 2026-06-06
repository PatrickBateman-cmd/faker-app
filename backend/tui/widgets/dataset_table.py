from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Button, DataTable, Label
from textual.widget import Widget


class DatasetTable(Widget):
    def __init__(self, title: str = "Data") -> None:
        super().__init__()
        self._title = title
        self._page = 1
        self._per_page = 50
        self._total = 0
        self._columns: list[str] = []
        self._rows: list[list] = []

    def compose(self) -> ComposeResult:
        yield Label(self._title, classes="table-title")
        yield DataTable(id="data-table")
        with Horizontal(id="pagination", classes="pagination"):
            yield Button("< Prev", id="prev-page", classes="page-btn")
            yield Label("Page 1", id="page-info", classes="page-info")
            yield Button("Next >", id="next-page", classes="page-btn")

    def on_mount(self) -> None:
        self._render()

    def set_data(self, columns: list[str], rows: list[list], total: int) -> None:
        self._columns = columns
        self._rows = rows
        self._total = total
        self._page = 1
        self._render()

    def _render(self) -> None:
        table = self.query_one("#data-table", DataTable)
        table.clear()
        table.columns.clear()
        table.rows.clear()

        if not self._columns:
            return

        table.add_columns(*self._columns)
        for row in self._rows:
            table.add_row(*[str(v) if v is not None else "" for v in row])

        page_info = self.query_one("#page-info", Label)
        total_pages = max(1, -(-self._total // self._per_page))
        page_info.update(f"Page {self._page} of {total_pages}")

        prev_btn = self.query_one("#prev-page", Button)
        next_btn = self.query_one("#next-page", Button)
        prev_btn.disabled = self._page <= 1
        next_btn.disabled = self._page >= total_pages

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "prev-page" and self._page > 1:
            self._page -= 1
            self._render()
        elif event.button.id == "next-page":
            total_pages = max(1, -(-self._total // self._per_page))
            if self._page < total_pages:
                self._page += 1
                self._render()
