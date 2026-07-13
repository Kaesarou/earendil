from dataclasses import dataclass, field

from app.execution.candidate_selector import CandidateSelectionConfig
from app.instruments.models import AssetClass, InstrumentConfig


@dataclass(frozen=True)
class StrategyProfileConfig:
    name: str
    crypto: InstrumentConfig
    equity_us: InstrumentConfig
    equity_eu: InstrumentConfig
    candidate_selection_top_n: int
    candidate_selection_min_score: float
    candidate_selection_dynamic_min_scores: dict[AssetClass, float] = field(default_factory=dict)

    @property
    def instrument_configs(self) -> dict[AssetClass, InstrumentConfig]:
        return {
            AssetClass.CRYPTO: self.crypto,
            AssetClass.EQUITY_US: self.equity_us,
            AssetClass.EQUITY_EU: self.equity_eu,
        }

    def instrument_config_for_asset_class(self, asset_class: AssetClass) -> InstrumentConfig:
        try:
            return self.instrument_configs[asset_class]
        except KeyError as exc:
            raise ValueError(f'Unsupported asset class: {asset_class}') from exc

    def candidate_selection_config_for_asset_class(
        self,
        asset_class: AssetClass,
    ) -> CandidateSelectionConfig:
        self.instrument_config_for_asset_class(asset_class)
        return CandidateSelectionConfig(
            top_n=self.candidate_selection_top_n,
            min_score=self.candidate_selection_min_score,
            dynamic_min_score=self.candidate_selection_dynamic_min_scores.get(asset_class),
        )
