import json
from pathlib import Path
from typing import Any, Protocol
class AnalyticsProvider(Protocol):
    def write(self, event: dict[str, Any]) -> None: ...
class JsonlAnalyticsProvider:
    def __init__(self, path: str): self.path = Path(path)
    def write(self, event: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as stream: stream.write(json.dumps(event, ensure_ascii=False) + "\n")
class NoopAnalyticsProvider:
    def write(self, event: dict[str, Any]) -> None: return None
