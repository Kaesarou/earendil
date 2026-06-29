from collections.abc import Mapping

from app.config.settings import Settings
from app.instruments.models import AssetClass, InstrumentProfile, RiskProfile
from app.risk.profiles import DEFAULT_RISK_PROFILES
from app.utils.commons import normalize_symbol


class InstrumentRegistry:
    def __init__(
        self,
        settings: Settings,
        risk_profiles: Mapping[AssetClass, RiskProfile] | None = None,
    ):
        self.settings = settings
        self.risk_profiles = risk_profiles or DEFAULT_RISK_PROFILES
        self.crypto_symbols = self._parse_symbols(settings.crypto_symbols)
        self.equity_us_symbols = self._parse_symbols(settings.equity_us_symbols)
        self.equity_eu_symbols = self._parse_symbols(settings.equity_eu_symbols)

    def resolve(self, symbol: str) -> InstrumentProfile:
        normalized_symbol = normalize_symbol(symbol)

        if normalized_symbol in self.crypto_symbols:
            return InstrumentProfile(
                symbol=normalized_symbol,
                asset_class=AssetClass.CRYPTO,
            )

        if normalized_symbol in self.equity_us_symbols:
            return InstrumentProfile(
                symbol=normalized_symbol,
                asset_class=AssetClass.EQUITY_US,
            )

        if normalized_symbol in self.equity_eu_symbols:
            return InstrumentProfile(
                symbol=normalized_symbol,
                asset_class=AssetClass.EQUITY_EU,
            )

        return InstrumentProfile(
            symbol=normalized_symbol,
            asset_class=AssetClass.UNKNOWN,
        )

    def risk_profile_for(self, symbol: str) -> RiskProfile:
        instrument_profile = self.resolve(symbol)
        return self.risk_profiles.get(
            instrument_profile.asset_class,
            self.risk_profiles[AssetClass.UNKNOWN],
        )

    def _parse_symbols(self, raw_symbols: str) -> set[str]:
        return {
            normalize_symbol(symbol)
            for symbol in raw_symbols.split(',')
            if symbol.strip()
        }
