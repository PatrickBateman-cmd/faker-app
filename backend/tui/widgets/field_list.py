from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.keys import Keys
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Button, Input, Label


GENERATORS = [
    "first_name", "last_name", "name", "email", "phone_number",
    "job", "company", "catch_phrase", "domain_name", "url",
    "country", "country_code", "city", "street_address", "zipcode",
    "text", "boolean", "random_int", "pydecimal", "uuid4", "uuid_int",
    "bothify", "random_element", "currency_code", "swift", "iban",
    "bban", "date_between", "date_of_birth", "date_time", "word",
]

TYPES = ["string", "integer", "float", "boolean", "date"]


class FieldRow(Widget):
    def __init__(self, field: dict, index: int, edit_mode: bool = False) -> None:
        super().__init__()
        self.field = field
        self.index = index
        self.edit_mode = edit_mode

    def compose(self) -> ComposeResult:
        with Horizontal(classes="field-row"):
            yield Label(f"{self.index + 1:>3}", id=f"num-{self.index}")
            name_input = Input(
                value=self.field.get("name", ""),
                placeholder="name",
                id=f"name-{self.index}",
                classes="field-name",
            )
            gen_input = Input(
                value=self.field.get("generator", "text"),
                placeholder="generator",
                id=f"gen-{self.index}",
                classes="field-gen",
            )
            type_input = Input(
                value=self.field.get("type", "string"),
                placeholder="type",
                id=f"type-{self.index}",
                classes="field-type",
            )
            if self.edit_mode:
                name_input.focus()
            yield name_input
            yield gen_input
            yield type_input


class FieldList(Widget):
    mode = reactive("normal")
    selected = reactive(0)

    def __init__(self, title: str = "Fields") -> None:
        super().__init__()
        self._title = title
        self.fields: list[dict] = []
        self._key_buffer = ""

    def compose(self) -> ComposeResult:
        yield Label(self._title, classes="field-list-title")
        yield Label("", id="field-list-status", classes="field-list-status")
        with Vertical(id="field-rows"):
            pass

    def on_mount(self) -> None:
        self._render_fields()

    def watch_mode(self, mode: str) -> None:
        status = self.query_one("#field-list-status", Label)
        status.update(f"Mode: {mode.upper()}  (selected: {self.selected + 1}/{len(self.fields)})")
        self._render_fields()

    def _render_fields(self) -> None:
        container = self.query_one("#field-rows", Vertical)
        container.remove_children()
        for i, f in enumerate(self.fields):
            row = FieldRow(f, i, edit_mode=(self.mode == "edit" and i == self.selected))
            container.mount(row)
        if self.fields:
            row_widgets = container.query(FieldRow)
            if self.selected < len(row_widgets):
                row_widgets[self.selected].scroll_visible()

    def set_fields(self, fields: list[dict]) -> None:
        self.fields = fields
        self.selected = min(self.selected, len(fields) - 1) if fields else 0
        self._render_fields()

    def get_fields(self) -> list[dict]:
        return self.fields

    def action_next_field(self) -> None:
        if self.fields and self.selected < len(self.fields) - 1:
            self.selected += 1
            self._render_fields()

    def action_prev_field(self) -> None:
        if self.selected > 0:
            self.selected -= 1
            self._render_fields()

    def action_move_down(self) -> None:
        if self.selected < len(self.fields) - 1:
            self.fields[self.selected], self.fields[self.selected + 1] = (
                self.fields[self.selected + 1],
                self.fields[self.selected],
            )
            self.selected += 1
            self._render_fields()

    def action_move_up(self) -> None:
        if self.selected > 0:
            self.fields[self.selected], self.fields[self.selected - 1] = (
                self.fields[self.selected - 1],
                self.fields[self.selected],
            )
            self.selected -= 1
            self._render_fields()

    def action_insert_after(self) -> None:
        idx = self.selected + 1 if self.fields else 0
        self.fields.insert(idx, {"name": "", "generator": "text", "type": "string"})
        self.selected = idx
        self._render_fields()

    def action_insert_before(self) -> None:
        idx = self.selected if self.fields else 0
        self.fields.insert(idx, {"name": "", "generator": "text", "type": "string"})
        self.selected = idx
        self._render_fields()

    def action_delete_field(self) -> None:
        if not self.fields:
            return
        self.fields.pop(self.selected)
        if self.selected >= len(self.fields):
            self.selected = max(0, len(self.fields) - 1)
        self._render_fields()

    def action_enter_edit(self) -> None:
        if not self.fields:
            return
        self.mode = "edit"

    def action_leave_edit(self) -> None:
        self._sync_from_inputs()
        self.mode = "normal"

    def _sync_from_inputs(self) -> None:
        container = self.query_one("#field-rows", Vertical)
        for i, row in enumerate(container.query(FieldRow)):
            if i >= len(self.fields):
                break
            name_input = row.query_one(f"#name-{i}", Input)
            gen_input = row.query_one(f"#gen-{i}", Input)
            type_input = row.query_one(f"#type-{i}", Input)
            self.fields[i]["name"] = name_input.value
            self.fields[i]["generator"] = gen_input.value
            self.fields[i]["type"] = type_input.value

    def on_key(self, event) -> None:
        if self.mode == "normal":
            key = event.key
            if key == "j":
                self.action_next_field()
                event.prevent_default()
            elif key == "k":
                self.action_prev_field()
                event.prevent_default()
            elif key == "J":
                self.action_move_down()
                event.prevent_default()
            elif key == "K":
                self.action_move_up()
                event.prevent_default()
            elif key == "o":
                self.action_insert_after()
                event.prevent_default()
            elif key == "O":
                self.action_insert_before()
                event.prevent_default()
            elif key == "i":
                self.action_enter_edit()
                event.prevent_default()

    def on_input_key(self, event) -> None:
        if self.mode == "edit":
            if event.key == "escape":
                self.action_leave_edit()
                event.prevent_default()
            elif event.key == "enter":
                self.action_leave_edit()
                event.prevent_default()

    def on_button_pressed(self, event) -> None:
        if self.mode == "normal":
            self._sync_from_inputs()
            self.mode = "normal"

    def key_delete(self) -> None:
        if self.mode == "normal":
            self._key_buffer = ""
            self.action_delete_field()

    def action_delete(self) -> None:
        self.action_delete_field()

    def on_input_focus(self, event) -> None:
        pass
