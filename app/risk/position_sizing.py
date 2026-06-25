from typing import Protocol

from app.config.settings import Settings


class PositionSizingStrategy(Protocol):
    def calculate_amount(self, account_equity: float, settings: Settings) -> float:
        raise NotImplementedError


class FixedPercentPositionSizing:
    def calculate_amount(self, account_equity: float, settings: Settings) -> float:
        max_position_amount = account_equity * (
            settings.max_position_size_percent / 100
        )

        return max(0.0, round(max_position_amount, 2))


def build_position_sizing_strategy(settings: Settings) -> PositionSizingStrategy:
    if settings.risk_strategy == 'fixed_percent':
        return FixedPercentPositionSizing()

    raise ValueError(f'Unsupported risk strategy: {settings.risk_strategy}')