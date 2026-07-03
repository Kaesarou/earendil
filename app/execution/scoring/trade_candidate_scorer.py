from app.execution.scoring.buy_signal_scorer import BuySignalScorer
from app.execution.scoring.sell_signal_scorer import SellSignalScorer
from app.execution.scoring.signal_scorer import SignalScorer
from app.market.models import Candle, MarketSnapshot
from app.strategies.signals import Signal


class TradeCandidateScorer:
    def __init__(
        self,
        *,
        buy_scorer: SignalScorer | None = None,
        sell_scorer: SignalScorer | None = None,
    ):
        self.buy_scorer = buy_scorer or BuySignalScorer()
        self.sell_scorer = sell_scorer or SellSignalScorer()

    def score(
        self,
        *,
        snapshot: MarketSnapshot,
        candle: Candle,
        signal: Signal,
    ) -> float:
        return self._scorer_for(signal).score(
            snapshot=snapshot,
            candle=candle,
            signal=signal,
        )

    def _scorer_for(self, signal: Signal) -> SignalScorer:
        if signal.action == 'SELL':
            return self.sell_scorer

        return self.buy_scorer
