from dataclasses import dataclass

from app.execution.candidate_selector import CandidateSelectionConfig
from app.instruments.models import AssetClass, InstrumentConfig


@dataclass(frozen=True)
class StrategyProfileConfig:
    name: str
    crypto: InstrumentConfig
    equity_us: InstrumentConfig
    equity_eu: InstrumentConfig
    candidate_selection_configs: dict[
        AssetClass,
        CandidateSelectionConfig,
    ]

    @property
    def instrument_configs(self) -> dict[AssetClass, InstrumentConfig]:
        return {
            AssetClass.CRYPTO: self.crypto,
            AssetClass.EQUITY_US: self.equity_us,
            AssetClass.EQUITY_EU: self.equity_eu,
        }

    def instrument_config_for_asset_class(
        self,
        asset_class: AssetClass,
    ) -> InstrumentConfig:
        try:
            return self.instrument_configs[asset_class]
        except KeyError as exc:
            raise ValueError(
                f'Unsupported asset class: {asset_class}'
            ) from exc

    def candidate_selection_config_for_asset_class(
        self,
        asset_class: AssetClass,
    ) -> CandidateSelectionConfig:
        self.instrument_config_for_asset_class(asset_class)
        try:
            return self.candidate_selection_configs[asset_class]
        except KeyError as exc:
            raise ValueError(
                'Missing candidate selection config for '
                f'{asset_class.value}.'
            ) from exc
