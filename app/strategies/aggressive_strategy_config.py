from dataclasses import dataclass

from app.instruments.base_configs import CRYPTO_CONFIG, EQUITY_EU_CONFIG, EQUITY_US_CONFIG
from app.instruments.config_overrides import with_overrides
from app.instruments.models import InstrumentConfig
from app.risk.trade_cooldown import TradeCooldownConfig
from app.strategies.models import StrategyProfileConfig

AGGRESSIVE_TRADE_COOLDOWN = TradeCooldownConfig(
    after_take_profit_minutes=15,
    after_stop_loss_minutes=30,
    after_manual_close_minutes=10,
    after_unknown_close_minutes=10,
)

AGGRESSIVE_CRYPTO_CONFIG = with_overrides(
    CRYPTO_CONFIG,
    trend={
        'session_lookback': 20,
        'min_session_move_percent': 0.20,
        'min_close_position_percent': 70.0,
        'market_regime_min_trend_strength_percent': 0.03,
        'min_snapshot_momentum_percent': 0.20,
    },
    risk={
        'trade_cooldown': AGGRESSIVE_TRADE_COOLDOWN,
    },
)

AGGRESSIVE_EQUITY_US_CONFIG = with_overrides(
    EQUITY_US_CONFIG,
    trend={
        'session_lookback': 20,
        'min_session_move_percent': 0.12,
        'min_breakout_percent': 0.03,
        'min_candle_range_percent': 0.02,
        'min_close_position_percent': 68.0,
        'market_regime_min_trend_strength_percent': 0.02,
        'market_regime_min_atr_percent': 0.005,
        'market_regime_max_atr_percent': 0.70,
        'market_regime_max_noise_ratio': 2.5,
        'min_snapshot_momentum_percent': 0.15,
    },
    risk={
        'trade_cooldown': AGGRESSIVE_TRADE_COOLDOWN,
    },
)

AGGRESSIVE_EQUITY_EU_CONFIG = with_overrides(
    EQUITY_EU_CONFIG,
    trend={
        'session_lookback': 20,
        'min_session_move_percent': 0.10,
        'min_breakout_percent': 0.03,
        'min_candle_range_percent': 0.02,
        'min_close_position_percent': 68.0,
        'market_regime_min_trend_strength_percent': 0.02,
        'market_regime_min_atr_percent': 0.005,
        'market_regime_max_atr_percent': 0.70,
        'market_regime_max_noise_ratio': 2.5,
        'min_snapshot_momentum_percent': 0.15,
    },
    risk={
        'trade_cooldown': AGGRESSIVE_TRADE_COOLDOWN,
    },
)


@dataclass(frozen=True)
class AggressiveStrategyConfig(StrategyProfileConfig):
    name: str = 'aggressive'
    candidate_selection_top_n: int = 2
    candidate_selection_min_score: float = 105.0
    crypto: InstrumentConfig = AGGRESSIVE_CRYPTO_CONFIG
    equity_us: InstrumentConfig = AGGRESSIVE_EQUITY_US_CONFIG
    equity_eu: InstrumentConfig = AGGRESSIVE_EQUITY_EU_CONFIG
