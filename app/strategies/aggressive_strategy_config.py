from dataclasses import dataclass, replace

from app.instruments.crypto_config import CryptoConfig
from app.instruments.equity_eu_config import EquityEuConfig
from app.instruments.equity_us_config import EquityUsConfig
from app.instruments.models import TrendStrategyConfig
from app.strategies.models import StrategyProfileConfig


@dataclass(frozen=True)
class AggressiveStrategyConfig(StrategyProfileConfig):
    name: str = 'aggressive'
    candidate_selection_top_n: int = 2

    crypto: TrendStrategyConfig = replace(
        CryptoConfig().trend,
        session_lookback=20,
        min_session_move_percent=0.20,
        min_close_position_percent=70.0,
        market_regime_min_trend_strength_percent=0.03,
        min_snapshot_momentum_percent=0.20,
    )

    equity_us: TrendStrategyConfig = replace(
        EquityUsConfig().trend,
        session_lookback=20,
        min_session_move_percent=0.12,
        min_breakout_percent=0.03,
        min_candle_range_percent=0.02,
        min_close_position_percent=68.0,
        market_regime_min_trend_strength_percent=0.02,
        market_regime_min_atr_percent=0.005,
        market_regime_max_atr_percent=0.70,
        market_regime_max_noise_ratio=2.5,
        min_snapshot_momentum_percent=0.15,
    )

    equity_eu: TrendStrategyConfig = replace(
        EquityEuConfig().trend,
        session_lookback=20,
        min_session_move_percent=0.10,
        min_breakout_percent=0.03,
        min_candle_range_percent=0.02,
        min_close_position_percent=68.0,
        market_regime_min_trend_strength_percent=0.02,
        market_regime_min_atr_percent=0.005,
        market_regime_max_atr_percent=0.70,
        market_regime_max_noise_ratio=2.5,
        min_snapshot_momentum_percent=0.15,
    )