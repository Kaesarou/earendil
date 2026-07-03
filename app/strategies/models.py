from dataclasses import dataclass

from app.execution.candidate_selector import CandidateSelectionConfig
from app.instruments.models import AssetClass, TrendStrategyConfig


@dataclass(frozen=True)
class StrategyProfileConfig:
    name: str
    crypto: TrendStrategyConfig
    equity_us: TrendStrategyConfig
    equity_eu: TrendStrategyConfig
    candidate_selection_top_n: int = 0

    def trend_config_for_asset_class(self, asset_class: AssetClass) -> TrendStrategyConfig:
        if asset_class == AssetClass.CRYPTO:
            return self.crypto
        if asset_class == AssetClass.EQUITY_US:
            return self.equity_us
        if asset_class == AssetClass.EQUITY_EU:
            return self.equity_eu

        raise ValueError(f'Unsupported asset class: {asset_class}')

    def candidate_selection_config_for_asset_class(self, asset_class: AssetClass) -> CandidateSelectionConfig:
        return CandidateSelectionConfig(
            top_n=self.candidate_selection_top_n,
        )
