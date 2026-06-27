from app.config.settings import Settings
from app.strategies.base import InvestmentStrategy
from app.strategies.breakout import BreakoutStrategy, BreakoutStrategyConfig
from app.strategies.intraday_trend import (
    IntradayTrendStrategy,
    IntradayTrendStrategyConfig,
)


def build_investment_strategy(settings: Settings) -> InvestmentStrategy:
    if settings.investment_strategy == 'breakout':
        return BreakoutStrategy(
            BreakoutStrategyConfig(
                lookback=settings.breakout_lookback,
                min_breakout_percent=settings.breakout_min_breakout_percent,
                require_green_candle=settings.breakout_require_green_candle,
                min_close_position_percent=settings.breakout_min_close_position_percent,
                min_candle_range_percent=settings.breakout_min_candle_range_percent,
                require_uptrend=settings.breakout_require_uptrend,
                trend_fast_lookback=settings.breakout_trend_fast_lookback,
                trend_slow_lookback=settings.breakout_trend_slow_lookback,
            )
        )

    if settings.investment_strategy == 'intraday_trend':
        return IntradayTrendStrategy(
            IntradayTrendStrategyConfig(
                lookback=settings.intraday_trend_lookback,
                fast_lookback=settings.intraday_trend_fast_lookback,
                slow_lookback=settings.intraday_trend_slow_lookback,
                session_lookback=settings.intraday_trend_session_lookback,
                min_session_move_percent=settings.intraday_trend_min_session_move_percent,
                min_breakout_percent=settings.intraday_trend_min_breakout_percent,
                min_candle_range_percent=settings.intraday_trend_min_candle_range_percent,
                min_close_position_percent=settings.intraday_trend_min_close_position_percent,
                allow_short=settings.intraday_trend_allow_short,
                atr_lookback=getattr(settings, 'intraday_trend_atr_lookback', 14),
                market_regime_filter_enabled=getattr(
                    settings,
                    'intraday_trend_market_regime_filter_enabled',
                    False,
                ),
                market_regime_min_trend_strength_percent=getattr(
                    settings,
                    'intraday_trend_market_regime_min_trend_strength_percent',
                    0.02,
                ),
                market_regime_min_atr_percent=getattr(
                    settings,
                    'intraday_trend_market_regime_min_atr_percent',
                    0.0,
                ),
                market_regime_max_atr_percent=getattr(
                    settings,
                    'intraday_trend_market_regime_max_atr_percent',
                    0.0,
                ),
                market_regime_max_noise_ratio=getattr(
                    settings,
                    'intraday_trend_market_regime_max_noise_ratio',
                    0.0,
                ),
            )
        )

    raise ValueError(f'Unsupported investment strategy: {settings.investment_strategy}')
