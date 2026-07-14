from collections import defaultdict

from app.market.multi_timeframe import (
    MultiTimeframeConfig,
    MultiTimeframeService,
    TimeframeSeriesStore,
)
from app.market.timeframes import Timeframe


class FullSessionTimeframeSeriesStore(TimeframeSeriesStore):
    """Retain enough closed bars to preserve session-level features all day."""

    _DEFAULT_LIMITS = {
        Timeframe.M1: 1440,
        Timeframe.M5: 288,
        Timeframe.M15: 192,
        Timeframe.M30: 96,
        Timeframe.H1: 72,
    }


class FullSessionMultiTimeframeService(MultiTimeframeService):
    """Runtime service whose M1 history covers a complete 24-hour session."""

    def __init__(
        self,
        configs: dict[str, MultiTimeframeConfig] | None = None,
    ) -> None:
        super().__init__(configs)
        self._stores = defaultdict(FullSessionTimeframeSeriesStore)
