from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Input, Label, Static

from app.services.template_library import get_template, list_templates


class TemplatesScreen(Screen):
    def compose(self) -> ComposeResult:
        yield Label("[bold]Templates[/bold]", id="tpl-title")
        with Horizontal():
            with Vertical(id="tpl-list", classes="sidebar"):
                yield Input(placeholder="Search...", id="tpl-search")
                yield Static("", id="tpl-items")
            with Vertical(id="tpl-detail", classes="main-panel"):
                yield Static("Select a template", id="tpl-info")

    def on_mount(self) -> None:
        self._refresh()

    def _refresh(self) -> None:
        try:
            templates = list_templates()
            items = "\n".join(
                f"  [bold]{t.name}[/] [dim]({t.category})[/dim]"
                for t in templates
            )
            self.query_one("#tpl-items", Static).update(items)
        except Exception as e:
            self.query_one("#tpl-items", Static).update(f"[red]{e}[/]")
