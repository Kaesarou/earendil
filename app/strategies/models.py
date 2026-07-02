from dataclasses import dataclass

from app.execution.pre_scan import PreScanConfig
from app.instruments.models import AssetClass


@dataclass(frozen=True)
class TrendStrategyConfig:
    lookback: int
    fast_lookback: int
    slow_lookback: int
    session_lookback: int
    min_session_move_percent: float
    min_breakout_percent: float
    min_candle_range_percent: float
    min_close_position_percent: float
    atr_lookback: int
    market_regime_filter_enabled: bool
    market_regime_min_trend_strength_percent: float
    market_regime_min_atr_percent: float
    market_regime_max_atr_percent: float
    market_regime_max_noise_ratio: float
    snapshot_momentum_window_seconds: int = 180
    min_snapshot_momentum_percent: float = 0.20


@dataclass(frozen=True)
class AssetStrategyConfig:
    trend: TrendStrategyConfig
    pre_scan: PreScanConfig


@dataclass(frozen=True)
class StrategyProfileConfig:
    name: str
    crypto: AssetStrategyConfig
    equity_us: AssetStrategyConfig
    equity_eu: AssetStrategyConfig

    def asset_config_for(self, asset_class: AssetClass) -> AssetStrategyConfig:
        if asset_class == AssetClass.CRYPTO:
            return self.crypto
        if asset_class == AssetClass.EQUITY_US:
            return self.equity_us
        if asset_class == AssetClass.EQUITY_EU:
            return self.equity_eu
        return self.crypto

    def trend_config_for_asset_class(self, asset_class: AssetClass) -> TrendStrategyConfig:
        return self.asset_config_for(asset_class).trend

    def pre_scan_config_for_asset_class(self, asset_class: AssetClass) -> PreScanConfig:
        return self.asset_config_for_asset_class(asset_class).pre_scan
