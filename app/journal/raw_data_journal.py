from collections.abc import Callable
from typing import Any

from app.journal.jsonl_journal import JsonlJournal

RawEventObserver = Callable[[str, dict[str, Any], bool], None]


class RawDataJournal:
    def __init__(self, journal: JsonlJournal, observer: RawEventObserver):
        self.journal = journal
        self.observer = observer

    def write(self, event_type: str, payload: dict[str, Any]) -> bool:
        written = self.journal.write(event_type, payload)
        self.observer(event_type, payload, written)
        return written
