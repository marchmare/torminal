import tomllib
import tomli_w
import asyncio
from typing import Self, Callable
from dataclasses import dataclass, field
from inotify_simple import INotify, flags
from threading import Thread

from torminal.requests import CONFIG_DIR

CONFIG_PATH = CONFIG_DIR / "settings.toml"


@dataclass
class Config:
    """Class representing user settings, stores data about queries defined during TORminal session."""

    time_window: int = 60
    peka_poll_interval = 60
    gtfs_rt_poll_interval = 5
    queries: list[list[str]] = field(default_factory=list)

    def add_query(self, query: list[str, str]) -> None:
        if query not in self.queries:
            self.queries.append(query)
            self.save()

    def remove_query(self, query: list[str, str]) -> None:
        if query not in self.queries:
            return
        self.queries.remove(query)
        self.save()

    @classmethod
    def load(cls) -> Self:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        if CONFIG_PATH.exists():
            with open(CONFIG_PATH, "rb") as f:
                return cls(**tomllib.load(f))
        return cls()

    def save(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_PATH, "wb") as f:
            tomli_w.dump(self.__dict__, f)

    def reload(self) -> None:
        self.__dict__.update(Config.load().__dict__)

    async def _watch(self, callback: Callable[[], None]) -> None:
        """Enable system call watcher for config file"""
        inotify = INotify()
        inotify.add_watch(CONFIG_PATH.parent, flags.CLOSE_WRITE)

        while True:
            for event in inotify.read():
                if event.name == CONFIG_PATH.name:
                    self.reload()
                    await callback()

    def watch(self, callback: Callable[[], None]) -> None:
        """Thread wrapper for system call watcher"""
        Thread(target=lambda: asyncio.run(self._watch(callback)), daemon=True).start()


config = Config.load()
