from typing import Protocol

from app.instruments.models import RiskProfile


class PositionSizingStrategy(Protocol):
    def calculate_amount(
        self,
        account_equity: float,
        risk_profile: RiskProfile,
    ) -> float:
        raise NotImplementedError


class FixedPercentPositionSizing:
    def calculate_amount(
        self,
        account_equity: float,
        risk_profile: RiskProfile,
    ) -> float:
        max_position_amount = account_equity * (
            risk_profile.max_position_size_percent / 100
        )
        return max(0.0, round(max_position_amount, 2))


def constant_risk_position_value(
    *,
    baseline_position_value: float,
    baseline_stop_loss_percent: float,
    effective_stop_loss_percent: float,
) -> float:
    if (
        baseline_position_value <= 0
        or baseline_stop_loss_percent <= 0
        or effective_stop_loss_percent <= 0
    ):
        return 0.0
    allowed_dollar_risk = baseline_position_value * baseline_stop_loss_percent / 100
    adjusted_position_value = allowed_dollar_risk / (effective_stop_loss_percent / 100)
    return round(max(0.0, min(baseline_position_value, adjusted_position_value)), 2)
