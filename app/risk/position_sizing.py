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
