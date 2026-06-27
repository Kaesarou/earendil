from app.config.settings import Settings
from app.instruments.models import AssetClass, InstrumentProfile, RiskProfile


class InstrumentRegistry:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.crypto_symbols = self._parse_symbols(settings.crypto_symbols)
        self.equity_us_symbols = self._parse_symbols(settings.equity_us_symbols)
        self.equity_eu_symbols = self._parse_symbols(settings.equity_eu_symbols)

    def resolve(self, symbol: str) -> InstrumentProfile:
        normalized_symbol = self._normalize_symbol(symbol)

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

        if instrument_profile.asset_class == AssetClass.CRYPTO:
            return RiskProfile(
                asset_class=AssetClass.CRYPTO,
                max_position_size_percent=self.settings.crypto_max_position_size_percent,
                stop_loss_percent=self.settings.crypto_stop_loss_percent,
                take_profit_percent=self.settings.crypto_take_profit_percent,
                estimated_round_trip_fees=self.settings.crypto_estimated_round_trip_fees,
                min_expected_net_profit=self.settings.crypto_min_expected_net_profit,
                force_close_enabled=self.settings.crypto_force_close_enabled,
                force_close_hour=self.settings.crypto_force_close_hour,
                force_close_minute=self.settings.crypto_force_close_minute,
                max_spread_percent=self.settings.crypto_max_spread_percent,
                min_move_spread_ratio=self.settings.crypto_min_move_spread_ratio,
                dynamic_sl_tp_enabled=self.settings.crypto_dynamic_sl_tp_enabled,
                stop_loss_atr_multiplier=self.settings.crypto_stop_loss_atr_multiplier,
                take_profit_atr_multiplier=self.settings.crypto_take_profit_atr_multiplier,
                min_stop_loss_percent=self.settings.crypto_min_stop_loss_percent,
                max_stop_loss_percent=self.settings.crypto_max_stop_loss_percent,
                min_take_profit_percent=self.settings.crypto_min_take_profit_percent,
                max_take_profit_percent=self.settings.crypto_max_take_profit_percent,
            )

        if instrument_profile.asset_class == AssetClass.EQUITY_US:
            return RiskProfile(
                asset_class=AssetClass.EQUITY_US,
                max_position_size_percent=self.settings.equity_us_max_position_size_percent,
                stop_loss_percent=self.settings.equity_us_stop_loss_percent,
                take_profit_percent=self.settings.equity_us_take_profit_percent,
                estimated_round_trip_fees=self.settings.equity_us_estimated_round_trip_fees,
                min_expected_net_profit=self.settings.equity_us_min_expected_net_profit,
                force_close_enabled=self.settings.equity_us_force_close_enabled,
                force_close_hour=self.settings.equity_us_force_close_hour,
                force_close_minute=self.settings.equity_us_force_close_minute,
                max_spread_percent=self.settings.equity_us_max_spread_percent,
                min_move_spread_ratio=self.settings.equity_us_min_move_spread_ratio,
                dynamic_sl_tp_enabled=self.settings.equity_us_dynamic_sl_tp_enabled,
                stop_loss_atr_multiplier=self.settings.equity_us_stop_loss_atr_multiplier,
                take_profit_atr_multiplier=self.settings.equity_us_take_profit_atr_multiplier,
                min_stop_loss_percent=self.settings.equity_us_min_stop_loss_percent,
                max_stop_loss_percent=self.settings.equity_us_max_stop_loss_percent,
                min_take_profit_percent=self.settings.equity_us_min_take_profit_percent,
                max_take_profit_percent=self.settings.equity_us_max_take_profit_percent,
            )

        if instrument_profile.asset_class == AssetClass.EQUITY_EU:
            return RiskProfile(
                asset_class=AssetClass.EQUITY_EU,
                max_position_size_percent=self.settings.equity_eu_max_position_size_percent,
                stop_loss_percent=self.settings.equity_eu_stop_loss_percent,
                take_profit_percent=self.settings.equity_eu_take_profit_percent,
                estimated_round_trip_fees=self.settings.equity_eu_estimated_round_trip_fees,
                min_expected_net_profit=self.settings.equity_eu_min_expected_net_profit,
                force_close_enabled=self.settings.equity_eu_force_close_enabled,
                force_close_hour=self.settings.equity_eu_force_close_hour,
                force_close_minute=self.settings.equity_eu_force_close_minute,
                max_spread_percent=self.settings.equity_eu_max_spread_percent,
                min_move_spread_ratio=self.settings.equity_eu_min_move_spread_ratio,
                dynamic_sl_tp_enabled=self.settings.equity_eu_dynamic_sl_tp_enabled,
                stop_loss_atr_multiplier=self.settings.equity_eu_stop_loss_atr_multiplier,
                take_profit_atr_multiplier=self.settings.equity_eu_take_profit_atr_multiplier,
                min_stop_loss_percent=self.settings.equity_eu_min_stop_loss_percent,
                max_stop_loss_percent=self.settings.equity_eu_max_stop_loss_percent,
                min_take_profit_percent=self.settings.equity_eu_min_take_profit_percent,
                max_take_profit_percent=self.settings.equity_eu_max_take_profit_percent,
            )

        return RiskProfile(
            asset_class=AssetClass.UNKNOWN,
            max_position_size_percent=self.settings.max_position_size_percent,
            stop_loss_percent=self.settings.stop_loss_percent,
            take_profit_percent=self.settings.take_profit_percent,
            estimated_round_trip_fees=self.settings.estimated_round_trip_fees,
            min_expected_net_profit=self.settings.min_expected_net_profit,
            force_close_enabled=True,
            force_close_hour=self.settings.force_close_hour,
            force_close_minute=self.settings.force_close_minute,
            max_spread_percent=self.settings.max_spread_percent,
            min_move_spread_ratio=self.settings.min_move_spread_ratio,
            dynamic_sl_tp_enabled=self.settings.dynamic_sl_tp_enabled,
            stop_loss_atr_multiplier=self.settings.stop_loss_atr_multiplier,
            take_profit_atr_multiplier=self.settings.take_profit_atr_multiplier,
            min_stop_loss_percent=self.settings.min_stop_loss_percent,
            max_stop_loss_percent=self.settings.max_stop_loss_percent,
            min_take_profit_percent=self.settings.min_take_profit_percent,
            max_take_profit_percent=self.settings.max_take_profit_percent,
        )

    def _parse_symbols(self, raw_symbols: str) -> set[str]:
        return {
            self._normalize_symbol(symbol)
            for symbol in raw_symbols.split(',')
            if symbol.strip()
        }

    def _normalize_symbol(self, symbol: str) -> str:
        return symbol.strip().upper()
