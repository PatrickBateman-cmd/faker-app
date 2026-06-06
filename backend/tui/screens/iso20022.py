from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Input, Label, Static

from app.services.iso20022_service import search_messages


class Iso20022Screen(Screen):
    def compose(self) -> ComposeResult:
        yield Label("[bold]ISO 20022[/bold]", id="iso-title")
        with Horizontal():
            yield Input(placeholder="Search messages...", id="iso-search")
            yield Button("Search", id="btn-search")
        yield Static("", id="iso-results")
        yield Button("Save as Template", id="btn-save-template")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-search":
            self._do_search()
        elif event.button.id == "btn-save-template":
            self._save_template()

    def _do_search(self) -> None:
        q = self.query_one("#iso-search", Input).value.strip()
        if not q:
            return
        try:
            messages = search_messages(q)
            if not messages:
                self.query_one("#iso-results", Static).update("[yellow]No results[/]")
                return
            lines = "\n".join(
                f"  [bold]{m['name']}[/] [dim]({m['business_area']})[/]"
                for m in messages[:20]
            )
            self.query_one("#iso-results", Static).update(lines)
        except Exception as e:
            self.query_one("#iso-results", Static).update(f"[red]{e}[/]")

    def _save_template(self) -> None:
        self.query_one("#iso-results", Static).update("[dim]Use the web UI or CLI to save templates from ISO messages[/]")
