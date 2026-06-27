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
    spread_percent: float | None = None
    max_spread_percent: float | None = None
    expected_move_percent: float | None = None
    min_required_move_percent: float | None = None
    min_move_spread_ratio: float | None = None
    atr_percent: float | None = None
    dynamic_sl_tp_enabled: bool | None = None
    effective_stop_loss_percent: float | None = None
    effective_take_profit_percent: float | None = None
