from app.execution.scoring.signal_scorer import directional_score, float_metadata
from app.market.models import Candle, MarketSnapshot
from app.strategies.signals import Signal


class SellSignalScorer:
    def score(
        self,
        *,
        snapshot: MarketSnapshot,
        candle: Candle,
        signal: Signal,
    ) -> float:
        metadata = signal.metadata or {}
        close_position_percent = float_metadata(metadata, 'close_position_percent')

        return directional_score(
            snapshot=snapshot,
            candle=candle,
            signal=signal,
            close_quality=100 - close_position_percent,
        )
