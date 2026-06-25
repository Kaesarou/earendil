from app.config.settings import Settings
from app.strategies.base import InvestmentStrategy
from app.strategies.breakout import BreakoutStrategy, BreakoutStrategyConfig


def build_investment_strategy(settings: Settings) -> InvestmentStrategy:
    if settings.investment_strategy == 'breakout':
        return BreakoutStrategy(
            BreakoutStrategyConfig(
                lookback=settings.breakout_lookback,
                min_breakout_percent=settings.breakout_min_breakout_percent,
            )
        )

    raise ValueError(f'Unsupported investment strategy: {settings.investment_strategy}')