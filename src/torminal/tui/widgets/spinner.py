from rich.spinner import Spinner as Spinner_
from textual.widgets import Static


class Spinner(Static):
    def __init__(self) -> None:
        super().__init__()
        self._spinner = Spinner_("dots12")

    def on_mount(self) -> None:
        self.update_render = self.set_interval(1 / 60, self.update_spinner)

    def update_spinner(self) -> None:
        self.update(self._spinner)
