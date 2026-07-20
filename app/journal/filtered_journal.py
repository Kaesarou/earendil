from __future__ import annotations

from collections.abc import Callable
from typing import Any


JournalPredicate = Callable[[str, dict[str, Any]], bool]


class FilteredJournal:
    def __init__(self, delegate, predicate: JournalPredicate):
        self.delegate = delegate
        self.predicate = predicate

    def write(self, event_type: str, payload: dict[str, Any]) -> bool:
        if not self.predicate(event_type, payload):
            return True
        return self.delegate.write(event_type, payload)

    def __getattr__(self, name: str):
        return getattr(self.delegate, name)


def keep_market_event(event_type: str, payload: dict[str, Any]) -> bool:
    # MarketDataEventFlow writes the canonical accepted price change. The legacy
    # symbol flow copy would otherwise duplicate the same full snapshot.
    return event_type != 'market_snapshot'


def keep_candle_event(event_type: str, payload: dict[str, Any]) -> bool:
    # The runtime emits one canonical candle_finalized record with quality.
    if event_type == 'candle_closed':
        return False
    if event_type.startswith('timeframe_bar_'):
        timeframe = str(payload.get('timeframe') or '').lower()
        if timeframe == 'm1':
            return False
    return True
