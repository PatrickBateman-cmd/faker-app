from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.screen import Screen

from tui.screens.dashboard import DashboardScreen
from tui.screens.generation import GenerationScreen
from tui.screens.datasets import DatasetsScreen
from tui.screens.financial import FinancialScreen
from tui.screens.templates import TemplatesScreen
from tui.screens.iso20022 import Iso20022Screen


class FakerTUI(App):
    SCREENS = {
        "dashboard": DashboardScreen,
        "generation": GenerationScreen,
        "datasets": DatasetsScreen,
        "financial": FinancialScreen,
        "templates": TemplatesScreen,
        "iso20022": Iso20022Screen,
    }

    BINDINGS = [
        Binding("1", "switch_to('dashboard')", "Dashboard", priority=True),
        Binding("2", "switch_to('generation')", "Generation", priority=True),
        Binding("3", "switch_to('datasets')", "Datasets", priority=True),
        Binding("4", "switch_to('financial')", "Financial", priority=True),
        Binding("5", "switch_to('templates')", "Templates", priority=True),
        Binding("6", "switch_to('iso20022')", "ISO 20022", priority=True),
        Binding("g d", "switch_to('dashboard')", "Dashboard", priority=True),
        Binding("g g", "switch_to('generation')", "Generation", priority=True),
        Binding("g s", "switch_to('datasets')", "Datasets", priority=True),
        Binding("g f", "switch_to('financial')", "Financial", priority=True),
        Binding("g t", "switch_to('templates')", "Templates", priority=True),
        Binding("g i", "switch_to('iso20022')", "ISO 20022", priority=True),
        Binding("q", "quit", "Quit", priority=True),
        Binding("ctrl+c", "quit", "Quit", priority=True),
    ]

    CSS_PATH = "app.tcss"
    TITLE = "Faker App"
    SUB_TITLE = "Synthetic Data Generator"

    def on_mount(self) -> None:
        self.push_screen("dashboard")

    def action_switch_to(self, screen_name: str) -> None:
        if screen_name in self.SCREENS:
            self.switch_screen(screen_name)
