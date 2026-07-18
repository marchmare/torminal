from textual.app import ComposeResult
from textual.widgets import Label, ProgressBar
from textual.screen import ModalScreen
from textual.containers import Container
from textual import work

from torminal.gtfs.static import GTFSStaticLoader
from torminal.gtfs.static import ProgressEvent
from torminal.tui.widgets.spinner import Spinner
from asyncio import sleep

LOGO = """░▀█▀░█▀█░█▀▄░█▄█░▀█▀░█▀█░█▀█░█░░░
░░█░░█░█░█▀▄░█░█░░█░░█░█░█▀█░█░░░
░░▀░░▀▀▀░▀░▀░▀░▀░▀▀▀░▀░▀░▀░▀░▀▀▀░"""


class LoadingScreen(ModalScreen):
    def compose(self) -> ComposeResult:
        with Container(classes="box"):
            yield Label(LOGO)
            yield Label("", id="loading_message")
            yield Spinner()
            yield ProgressBar(show_eta=False, show_percentage=False)

    def on_mount(self) -> None:
        self.load_data()

    @work
    async def load_data(self) -> None:
        """Main loader worker, initializes loader and progress bar, then loads GTFS static data."""

        loader = GTFSStaticLoader(self.update_progress)
        self.bar.update(total=loader.total)

        data = await loader.load()
        await sleep(0.25)

        self.dismiss(data)

    def update_progress(self, progress: ProgressEvent) -> None:
        """Update progress bar and loading message label state."""

        self.loading_message.update(progress.message)
        self.bar.animate("progress", progress.current, duration=0.3)

    @property
    def bar(self) -> ProgressBar:
        return self.query_one(ProgressBar)

    @property
    def loading_message(self) -> Label:
        return self.query_one("#loading_message", Label)
