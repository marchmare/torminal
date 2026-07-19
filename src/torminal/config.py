import tomllib
import tomli_w
from typing import Self
from dataclasses import dataclass, field

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


config = Config.load()
