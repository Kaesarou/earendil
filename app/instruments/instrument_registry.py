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

        raise ValueError(
            f"Unsupported instrument symbol '{normalized_symbol}'. "
            'Declare it in exactly one asset category: '
            'CRYPTO_SYMBOLS, EQUITY_US_SYMBOLS or EQUITY_EU_SYMBOLS.'
        )

    def risk_profile_for(self, symbol: str) -> RiskProfile:
        instrument_profile = self.resolve(symbol)

        try:
            return self.risk_profiles[instrument_profile.asset_class]
        except KeyError as exc:
            raise ValueError(
                f"No risk profile configured for asset class '{instrument_profile.asset_class}' "
                f"used by symbol '{instrument_profile.symbol}'."
            ) from exc

    def _parse_symbols(self, raw_symbols: str) -> set[str]:
        return {
            normalize_symbol(symbol)
            for symbol in raw_symbols.split(',')
            if symbol.strip()
        }
    
    def validate_supported_symbols(self, symbols: list[str]) -> None:
        unsupported_symbols: list[str] = []

        for symbol in symbols:
            try:
                self.resolve(symbol)
            except ValueError:
                unsupported_symbols.append(normalize_symbol(symbol))

        if unsupported_symbols:
            formatted_symbols = ', '.join(sorted(set(unsupported_symbols)))
            raise ValueError(
                'Invalid instrument configuration: unsupported symbols in WATCHLIST: '
                f'{formatted_symbols}. Declare each symbol in exactly one asset category: '
                'CRYPTO_SYMBOLS, EQUITY_US_SYMBOLS or EQUITY_EU_SYMBOLS.'
            )
