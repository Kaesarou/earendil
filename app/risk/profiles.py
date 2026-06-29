from dataclasses import replace

from app.instruments.models import AssetClass, RiskProfile
from app.risk.trade_cooldown import TradeCooldownConfig


BALANCED_TRADE_COOLDOWN = TradeCooldownConfig(
    after_take_profit_minutes=30,
    after_stop_loss_minutes=45,
    after_manual_close_minutes=15,
    after_unknown_close_minutes=15,
)

AGGRESSIVE_TRADE_COOLDOWN = TradeCooldownConfig(
    after_take_profit_minutes=15,
    after_stop_loss_minutes=30,
    after_manual_close_minutes=10,
    after_unknown_close_minutes=10,
)

UNKNOWN_RISK_PROFILE = RiskProfile(
    asset_class=AssetClass.UNKNOWN,
    max_position_size_percent=20.0,
    stop_loss_percent=0.8,
    take_profit_percent=1.2,
    estimated_round_trip_fees=0.0,
    min_expected_net_profit=0.0,
    force_close_enabled=True,
    force_close_hour=21,
    force_close_minute=55,
    max_spread_percent=0.0,
    min_move_spread_ratio=0.0,
    dynamic_sl_tp_enabled=False,
    stop_loss_atr_multiplier=1.5,
    take_profit_atr_multiplier=2.5,
    min_stop_loss_percent=0.0,
    max_stop_loss_percent=0.0,
    min_take_profit_percent=0.0,
    max_take_profit_percent=0.0,
    breakeven_stop_enabled=False,
    breakeven_trigger_percent=1.0,
    breakeven_buffer_percent=0.0,
    trailing_stop_enabled=False,
    trailing_stop_trigger_percent=1.5,
    trailing_stop_distance_percent=0.8,
)

CRYPTO_RISK_PROFILE = RiskProfile(
    asset_class=AssetClass.CRYPTO,
    max_position_size_percent=0.75,
    stop_loss_percent=1.50,
    take_profit_percent=3.00,
    estimated_round_trip_fees=3.00,
    min_expected_net_profit=8.00,
    force_close_enabled=False,
    force_close_hour=23,
    force_close_minute=59,
    max_spread_percent=0.35,
    min_move_spread_ratio=4.0,
    dynamic_sl_tp_enabled=False,
    stop_loss_atr_multiplier=1.5,
    take_profit_atr_multiplier=2.5,
    min_stop_loss_percent=0.8,
    max_stop_loss_percent=2.5,
    min_take_profit_percent=1.5,
    max_take_profit_percent=5.0,
    breakeven_stop_enabled=False,
    breakeven_trigger_percent=1.0,
    breakeven_buffer_percent=0.0,
    trailing_stop_enabled=False,
    trailing_stop_trigger_percent=1.5,
    trailing_stop_distance_percent=0.8,
)

EQUITY_US_RISK_PROFILE = RiskProfile(
    asset_class=AssetClass.EQUITY_US,
    max_position_size_percent=0.75,
    stop_loss_percent=0.90,
    take_profit_percent=1.60,
    estimated_round_trip_fees=2.50,
    min_expected_net_profit=5.00,
    force_close_enabled=True,
    force_close_hour=21,
    force_close_minute=55,
    max_spread_percent=0.10,
    min_move_spread_ratio=3.0,
    dynamic_sl_tp_enabled=False,
    stop_loss_atr_multiplier=1.2,
    take_profit_atr_multiplier=2.0,
    min_stop_loss_percent=0.4,
    max_stop_loss_percent=1.5,
    min_take_profit_percent=0.8,
    max_take_profit_percent=3.0,
    breakeven_stop_enabled=False,
    breakeven_trigger_percent=1.0,
    breakeven_buffer_percent=0.0,
    trailing_stop_enabled=False,
    trailing_stop_trigger_percent=1.5,
    trailing_stop_distance_percent=0.8,
)

EQUITY_EU_RISK_PROFILE = RiskProfile(
    asset_class=AssetClass.EQUITY_EU,
    max_position_size_percent=0.75,
    stop_loss_percent=0.80,
    take_profit_percent=1.40,
    estimated_round_trip_fees=2.50,
    min_expected_net_profit=5.00,
    force_close_enabled=True,
    force_close_hour=17,
    force_close_minute=25,
    max_spread_percent=0.15,
    min_move_spread_ratio=3.0,
    dynamic_sl_tp_enabled=False,
    stop_loss_atr_multiplier=1.2,
    take_profit_atr_multiplier=2.0,
    min_stop_loss_percent=0.4,
    max_stop_loss_percent=1.5,
    min_take_profit_percent=0.8,
    max_take_profit_percent=3.0,
    breakeven_stop_enabled=False,
    breakeven_trigger_percent=1.0,
    breakeven_buffer_percent=0.0,
    trailing_stop_enabled=False,
    trailing_stop_trigger_percent=1.5,
    trailing_stop_distance_percent=0.8,
)


def _risk_profiles_with_cooldown(
    trade_cooldown: TradeCooldownConfig,
) -> dict[AssetClass, RiskProfile]:
    return {
        AssetClass.UNKNOWN: replace(
            UNKNOWN_RISK_PROFILE,
            trade_cooldown=trade_cooldown,
        ),
        AssetClass.CRYPTO: replace(
            CRYPTO_RISK_PROFILE,
            trade_cooldown=trade_cooldown,
        ),
        AssetClass.EQUITY_US: replace(
            EQUITY_US_RISK_PROFILE,
            trade_cooldown=trade_cooldown,
        ),
        AssetClass.EQUITY_EU: replace(
            EQUITY_EU_RISK_PROFILE,
            trade_cooldown=trade_cooldown,
        ),
    }


BALANCED_RISK_PROFILES = _risk_profiles_with_cooldown(BALANCED_TRADE_COOLDOWN)
AGGRESSIVE_RISK_PROFILES = _risk_profiles_with_cooldown(AGGRESSIVE_TRADE_COOLDOWN)
DEFAULT_RISK_PROFILES: dict[AssetClass, RiskProfile] = BALANCED_RISK_PROFILES


def risk_profiles_for_aggressiveness(name: str) -> dict[AssetClass, RiskProfile]:
    normalized_name = name.strip().lower()

    if normalized_name in ('balanced', 'balance'):
        return BALANCED_RISK_PROFILES

    if normalized_name in ('aggressive', 'aggressif', 'aggressiv'):
        return AGGRESSIVE_RISK_PROFILES

    raise ValueError(
        f'Unsupported risk aggressiveness: {name}. '
        'Expected one of: balanced, aggressive.'
    )
