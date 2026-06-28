from app.config.settings import Settings
from app.strategies.base import InvestmentStrategy
from app.strategies.intraday_trend import (
    IntradayTrendStrategy,
    IntradayTrendStrategyConfig,
)


def build_investment_strategy(settings: Settings) -> InvestmentStrategy:
    
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

