from dataclasses import dataclass


@dataclass(frozen=True)
class TradePlan:
    approved: bool
    reason: str
    symbol: str | None = None
    side: str | None = None
    amount: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    expected_gross_profit: float | None = None
    estimated_fees: float | None = None
    expected_net_profit: float | None = None