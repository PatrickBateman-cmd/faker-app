import json

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Input, Label, Static

from app.core.database import DuckDBManager
from app.schemas.generation import (
    ConstraintConfig,
    DatasetDefinition,
    DatasetResult,
    FieldDefinition,
    GenerateRequest,
    GroupConfig,
)
from app.services.generation_engine import generate_datasets

from tui.widgets.field_list import FieldList


class GenerationScreen(Screen):
    def __init__(self) -> None:
        super().__init__()
        self._mode = "flat"
        self._result: list[DatasetResult] | None = None

    def compose(self) -> ComposeResult:
        yield Label("[bold]Generate Dataset[/bold]", id="gen-title")
        with Horizontal(classes="gen-controls"):
            yield Button("Flat", id="mode-flat", variant="primary")
            yield Button("Parent-Child", id="mode-grouped")
            yield Input(placeholder="Dataset name", id="gen-name", value="dataset")
            yield Input(placeholder="Rows", id="gen-rows", value="100")
        with Horizontal(classes="gen-extra"):
            yield Input(placeholder="Groups", id="gen-groups", value="4")
            yield Input(placeholder="Split %", id="gen-split", value="100")
        yield FieldList(title="Fields (Flat) / Child Fields (Grouped)", id="child-fields")
        yield FieldList(title="Parent Fields (Grouped mode)", id="parent-fields")
        yield Button("Generate", id="btn-generate", variant="primary")
        yield Static("", id="gen-result")

    def on_mount(self) -> None:
        child = self.query_one("#child-fields", FieldList)
        child.set_fields([{"name": "name", "generator": "name", "type": "string"}])
        parent = self.query_one("#parent-fields", FieldList)
        parent.set_fields([{"name": "id", "generator": "uuid4", "type": "string"}])
        parent.visible = False
        # Hide groups/split by default
        self.query_one("#gen-groups", Input).visible = False
        self.query_one("#gen-split", Input).visible = False

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "mode-flat":
            self._mode = "flat"
            self.query_one("#parent-fields", FieldList).visible = False
            self.query_one("#gen-groups", Input).visible = False
            self.query_one("#gen-split", Input).visible = False
            self.query_one("#child-fields", FieldList)._title = "Fields"
            self.query_one("#gen-title", Label).update("[bold]Generate Dataset (Flat)[/bold]")
        elif event.button.id == "mode-grouped":
            self._mode = "grouped"
            self.query_one("#parent-fields", FieldList).visible = True
            self.query_one("#gen-groups", Input).visible = True
            self.query_one("#gen-split", Input).visible = True
            self.query_one("#child-fields", FieldList)._title = "Child Fields"
            self.query_one("#gen-title", Label).update("[bold]Generate Dataset (Parent-Child)[/bold]")
        elif event.button.id == "btn-generate":
            self._do_generate()

    def _do_generate(self) -> None:
        name = self.query_one("#gen-name", Input).value or "dataset"
        rows = int(self.query_one("#gen-rows", Input).value or 100)

        try:
            if self._mode == "grouped":
                groups = int(self.query_one("#gen-groups", Input).value or 4)
                split = float(self.query_one("#gen-split", Input).value or 100)
                parent_fields = self.query_one("#parent-fields", FieldList).get_fields()
                child_fields = self.query_one("#child-fields", FieldList).get_fields()

                if not parent_fields:
                    self.query_one("#gen-result", Static).update("[red]Error:[/red] At least one parent field required")
                    return
                if not child_fields:
                    self.query_one("#gen-result", Static).update("[red]Error:[/red] At least one child field required")
                    return

                defs = [
                    DatasetDefinition(
                        name=name,
                        rows=rows,
                        fields=[],
                        group_config=GroupConfig(
                            num_groups=groups,
                            split_pct=split,
                            parent_fields=[_dict_to_field(f) for f in parent_fields],
                            child_fields=[_dict_to_field(f) for f in child_fields],
                        ),
                    )
                ]
            else:
                fields = self.query_one("#child-fields", FieldList).get_fields()
                if not fields:
                    self.query_one("#gen-result", Static).update("[red]Error:[/red] At least one field required")
                    return
                defs = [
                    DatasetDefinition(
                        name=name,
                        rows=rows,
                        fields=[_dict_to_field(f) for f in fields],
                    )
                ]

            request = GenerateRequest(datasets=defs, homogeneity=50)
            resp = generate_datasets(request)
            self._result = resp.datasets
            lines = "\n".join(
                f"  [green]{d.name}[/] — {d.row_count} rows, {len(d.columns)} cols"
                for d in resp.datasets
            )
            self.query_one("#gen-result", Static).update(f"[bold]Generated:[/bold]\n{lines}")
        except Exception as e:
            self.query_one("#gen-result", Static).update(f"[red]Error:[/red] {e}")


def _dict_to_field(d: dict) -> FieldDefinition:
    constraint = None
    if d.get("constraint"):
        constraint = ConstraintConfig(**d["constraint"])
    return FieldDefinition(
        name=d.get("name", ""),
        type=d.get("type", "string"),
        generator=d.get("generator", "text"),
        constraint=constraint,
    )
