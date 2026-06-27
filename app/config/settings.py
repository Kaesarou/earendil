from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        extra='ignore',
    )
    app_log_path: str = Field(default='data/logs/earendil.log', alias='APP_LOG_PATH')
    position_store_path: str = Field(default='data/earendil.sqlite', alias='POSITION_STORE_PATH')
    ear_mode: str = Field(default='paper', alias='EAR_MODE')
    real_trading_enabled: bool = Field(default=False, alias='REAL_TRADING_ENABLED')
    log_level: str = Field(default='INFO', alias='LOG_LEVEL')
    poll_interval_seconds: int = Field(default=60, alias='POLL_INTERVAL_SECONDS')

    broker: str = Field(default='etoro', alias='BROKER')
    etoro_env: str = Field(default='demo', alias='ETORO_ENV')
    etoro_api_base_url: str = Field(default='https://public-api.etoro.com', alias='ETORO_API_BASE_URL')
    etoro_api_key: str = Field(default='', alias='ETORO_API_KEY')
    etoro_user_key: str = Field(default='', alias='ETORO_USER_KEY')

    default_symbol: str = Field(default='BTC', alias='DEFAULT_SYMBOL')
    watchlist: str = Field(default='', alias='WATCHLIST')
    base_currency: str = Field(default='USD', alias='BASE_CURRENCY')

    investment_strategy: str = Field(default='breakout', alias='INVESTMENT_STRATEGY')

    breakout_lookback: int = Field(default=3, alias='BREAKOUT_LOOKBACK')
    breakout_min_breakout_percent: float = Field(default=0.05, alias='BREAKOUT_MIN_BREAKOUT_PERCENT')
    breakout_require_green_candle: bool = Field(default=True, alias='BREAKOUT_REQUIRE_GREEN_CANDLE')
    breakout_min_close_position_percent: float = Field(default=70.0, alias='BREAKOUT_MIN_CLOSE_POSITION_PERCENT')
    breakout_min_candle_range_percent: float = Field(default=0.05, alias='BREAKOUT_MIN_CANDLE_RANGE_PERCENT')
    breakout_require_uptrend: bool = Field(default=False, alias='BREAKOUT_REQUIRE_UPTREND')
    breakout_trend_fast_lookback: int = Field(default=5, alias='BREAKOUT_TREND_FAST_LOOKBACK')
    breakout_trend_slow_lookback: int = Field(default=15, alias='BREAKOUT_TREND_SLOW_LOOKBACK')

    intraday_trend_lookback: int = Field(default=3, alias='INTRADAY_TREND_LOOKBACK')
    intraday_trend_fast_lookback: int = Field(default=5, alias='INTRADAY_TREND_FAST_LOOKBACK')
    intraday_trend_slow_lookback: int = Field(default=15, alias='INTRADAY_TREND_SLOW_LOOKBACK')
    intraday_trend_session_lookback: int = Field(default=30, alias='INTRADAY_TREND_SESSION_LOOKBACK')
    intraday_trend_min_session_move_percent: float = Field(default=0.15, alias='INTRADAY_TREND_MIN_SESSION_MOVE_PERCENT')
    intraday_trend_min_breakout_percent: float = Field(default=0.05, alias='INTRADAY_TREND_MIN_BREAKOUT_PERCENT')
    intraday_trend_min_candle_range_percent: float = Field(default=0.04, alias='INTRADAY_TREND_MIN_CANDLE_RANGE_PERCENT')
    intraday_trend_min_close_position_percent: float = Field(default=70.0, alias='INTRADAY_TREND_MIN_CLOSE_POSITION_PERCENT')
    intraday_trend_allow_short: bool = Field(default=False, alias='INTRADAY_TREND_ALLOW_SHORT')
    intraday_trend_atr_lookback: int = Field(default=14, alias='INTRADAY_TREND_ATR_LOOKBACK')
    intraday_trend_market_regime_filter_enabled: bool = Field(default=False, alias='INTRADAY_TREND_MARKET_REGIME_FILTER_ENABLED')
    intraday_trend_market_regime_min_trend_strength_percent: float = Field(default=0.02, alias='INTRADAY_TREND_MARKET_REGIME_MIN_TREND_STRENGTH_PERCENT')
    intraday_trend_market_regime_min_atr_percent: float = Field(default=0.0, alias='INTRADAY_TREND_MARKET_REGIME_MIN_ATR_PERCENT')
    intraday_trend_market_regime_max_atr_percent: float = Field(default=0.0, alias='INTRADAY_TREND_MARKET_REGIME_MAX_ATR_PERCENT')
    intraday_trend_market_regime_max_noise_ratio: float = Field(default=0.0, alias='INTRADAY_TREND_MARKET_REGIME_MAX_NOISE_RATIO')

    pre_scan_enabled: bool = Field(default=False, alias='PRE_SCAN_ENABLED')
    pre_scan_top_n: int = Field(default=0, alias='PRE_SCAN_TOP_N')
    pre_scan_min_score: float = Field(default=0.0, alias='PRE_SCAN_MIN_SCORE')
    pre_scan_allowed_market_regimes: str = Field(default='TRENDING', alias='PRE_SCAN_ALLOWED_MARKET_REGIMES')
    pre_scan_max_spread_percent: float = Field(default=0.0, alias='PRE_SCAN_MAX_SPREAD_PERCENT')
    pre_scan_min_session_move_percent: float = Field(default=0.0, alias='PRE_SCAN_MIN_SESSION_MOVE_PERCENT')
    pre_scan_min_trend_strength_percent: float = Field(default=0.0, alias='PRE_SCAN_MIN_TREND_STRENGTH_PERCENT')
    pre_scan_min_atr_percent: float = Field(default=0.0, alias='PRE_SCAN_MIN_ATR_PERCENT')
    pre_scan_max_atr_percent: float = Field(default=0.0, alias='PRE_SCAN_MAX_ATR_PERCENT')
    pre_scan_max_noise_ratio: float = Field(default=0.0, alias='PRE_SCAN_MAX_NOISE_RATIO')

    risk_strategy: str = Field(default='fixed_percent', alias='RISK_STRATEGY')
    max_open_positions: int = Field(default=1, alias='MAX_OPEN_POSITIONS')
    max_open_positions_per_symbol: int = Field(default=1, alias='MAX_OPEN_POSITIONS_PER_SYMBOL')
    max_trades_per_day: int = Field(default=3, alias='MAX_TRADES_PER_DAY')
    max_position_size_percent: float = Field(default=20.0, alias='MAX_POSITION_SIZE_PERCENT')
    stop_loss_percent: float = Field(default=0.8, alias='STOP_LOSS_PERCENT')
    take_profit_percent: float = Field(default=1.2, alias='TAKE_PROFIT_PERCENT')
    estimated_round_trip_fees: float = Field(default=0.0, alias='ESTIMATED_ROUND_TRIP_FEES')
    min_expected_net_profit: float = Field(default=0.0, alias='MIN_EXPECTED_NET_PROFIT')
    max_spread_percent: float = Field(default=0.0, alias='MAX_SPREAD_PERCENT')
    min_move_spread_ratio: float = Field(default=0.0, alias='MIN_MOVE_SPREAD_RATIO')
    dynamic_sl_tp_enabled: bool = Field(default=False, alias='DYNAMIC_SL_TP_ENABLED')
    stop_loss_atr_multiplier: float = Field(default=1.5, alias='STOP_LOSS_ATR_MULTIPLIER')
    take_profit_atr_multiplier: float = Field(default=2.5, alias='TAKE_PROFIT_ATR_MULTIPLIER')
    min_stop_loss_percent: float = Field(default=0.0, alias='MIN_STOP_LOSS_PERCENT')
    max_stop_loss_percent: float = Field(default=0.0, alias='MAX_STOP_LOSS_PERCENT')
    min_take_profit_percent: float = Field(default=0.0, alias='MIN_TAKE_PROFIT_PERCENT')
    max_take_profit_percent: float = Field(default=0.0, alias='MAX_TAKE_PROFIT_PERCENT')
    breakeven_stop_enabled: bool = Field(default=False, alias='BREAKEVEN_STOP_ENABLED')
    breakeven_trigger_percent: float = Field(default=1.0, alias='BREAKEVEN_TRIGGER_PERCENT')
    breakeven_buffer_percent: float = Field(default=0.0, alias='BREAKEVEN_BUFFER_PERCENT')
    trailing_stop_enabled: bool = Field(default=False, alias='TRAILING_STOP_ENABLED')
    trailing_stop_trigger_percent: float = Field(default=1.5, alias='TRAILING_STOP_TRIGGER_PERCENT')
    trailing_stop_distance_percent: float = Field(default=0.8, alias='TRAILING_STOP_DISTANCE_PERCENT')

    crypto_symbols: str = Field(default='', alias='CRYPTO_SYMBOLS')
    equity_us_symbols: str = Field(default='', alias='EQUITY_US_SYMBOLS')
    equity_eu_symbols: str = Field(default='', alias='EQUITY_EU_SYMBOLS')

    crypto_max_position_size_percent: float = Field(default=0.75, alias='CRYPTO_MAX_POSITION_SIZE_PERCENT')
    crypto_stop_loss_percent: float = Field(default=1.50, alias='CRYPTO_STOP_LOSS_PERCENT')
    crypto_take_profit_percent: float = Field(default=3.00, alias='CRYPTO_TAKE_PROFIT_PERCENT')
    crypto_estimated_round_trip_fees: float = Field(default=3.00, alias='CRYPTO_ESTIMATED_ROUND_TRIP_FEES')
    crypto_min_expected_net_profit: float = Field(default=8.00, alias='CRYPTO_MIN_EXPECTED_NET_PROFIT')
    crypto_force_close_enabled: bool = Field(default=False, alias='CRYPTO_FORCE_CLOSE_ENABLED')
    crypto_force_close_hour: int = Field(default=23, alias='CRYPTO_FORCE_CLOSE_HOUR')
    crypto_force_close_minute: int = Field(default=59, alias='CRYPTO_FORCE_CLOSE_MINUTE')
    crypto_max_spread_percent: float = Field(default=0.35, alias='CRYPTO_MAX_SPREAD_PERCENT')
    crypto_min_move_spread_ratio: float = Field(default=4.0, alias='CRYPTO_MIN_MOVE_SPREAD_RATIO')
    crypto_dynamic_sl_tp_enabled: bool = Field(default=False, alias='CRYPTO_DYNAMIC_SL_TP_ENABLED')
    crypto_stop_loss_atr_multiplier: float = Field(default=1.5, alias='CRYPTO_STOP_LOSS_ATR_MULTIPLIER')
    crypto_take_profit_atr_multiplier: float = Field(default=2.5, alias='CRYPTO_TAKE_PROFIT_ATR_MULTIPLIER')
    crypto_min_stop_loss_percent: float = Field(default=0.8, alias='CRYPTO_MIN_STOP_LOSS_PERCENT')
    crypto_max_stop_loss_percent: float = Field(default=2.5, alias='CRYPTO_MAX_STOP_LOSS_PERCENT')
    crypto_min_take_profit_percent: float = Field(default=1.5, alias='CRYPTO_MIN_TAKE_PROFIT_PERCENT')
    crypto_max_take_profit_percent: float = Field(default=5.0, alias='CRYPTO_MAX_TAKE_PROFIT_PERCENT')

    equity_us_max_position_size_percent: float = Field(default=0.75, alias='EQUITY_US_MAX_POSITION_SIZE_PERCENT')
    equity_us_stop_loss_percent: float = Field(default=0.90, alias='EQUITY_US_STOP_LOSS_PERCENT')
    equity_us_take_profit_percent: float = Field(default=1.60, alias='EQUITY_US_TAKE_PROFIT_PERCENT')
    equity_us_estimated_round_trip_fees: float = Field(default=2.50, alias='EQUITY_US_ESTIMATED_ROUND_TRIP_FEES')
    equity_us_min_expected_net_profit: float = Field(default=5.00, alias='EQUITY_US_MIN_EXPECTED_NET_PROFIT')
    equity_us_force_close_enabled: bool = Field(default=True, alias='EQUITY_US_FORCE_CLOSE_ENABLED')
    equity_us_force_close_hour: int = Field(default=21, alias='EQUITY_US_FORCE_CLOSE_HOUR')
    equity_us_force_close_minute: int = Field(default=55, alias='EQUITY_US_FORCE_CLOSE_MINUTE')
    equity_us_max_spread_percent: float = Field(default=0.10, alias='EQUITY_US_MAX_SPREAD_PERCENT')
    equity_us_min_move_spread_ratio: float = Field(default=3.0, alias='EQUITY_US_MIN_MOVE_SPREAD_RATIO')
    equity_us_dynamic_sl_tp_enabled: bool = Field(default=False, alias='EQUITY_US_DYNAMIC_SL_TP_ENABLED')
    equity_us_stop_loss_atr_multiplier: float = Field(default=1.2, alias='EQUITY_US_STOP_LOSS_ATR_MULTIPLIER')
    equity_us_take_profit_atr_multiplier: float = Field(default=2.0, alias='EQUITY_US_TAKE_PROFIT_ATR_MULTIPLIER')
    equity_us_min_stop_loss_percent: float = Field(default=0.4, alias='EQUITY_US_MIN_STOP_LOSS_PERCENT')
    equity_us_max_stop_loss_percent: float = Field(default=1.5, alias='EQUITY_US_MAX_STOP_LOSS_PERCENT')
    equity_us_min_take_profit_percent: float = Field(default=0.8, alias='EQUITY_US_MIN_TAKE_PROFIT_PERCENT')
    equity_us_max_take_profit_percent: float = Field(default=3.0, alias='EQUITY_US_MAX_TAKE_PROFIT_PERCENT')

    equity_eu_max_position_size_percent: float = Field(default=0.75, alias='EQUITY_EU_MAX_POSITION_SIZE_PERCENT')
    equity_eu_stop_loss_percent: float = Field(default=0.80, alias='EQUITY_EU_STOP_LOSS_PERCENT')
    equity_eu_take_profit_percent: float = Field(default=1.40, alias='EQUITY_EU_TAKE_PROFIT_PERCENT')
    equity_eu_estimated_round_trip_fees: float = Field(default=2.50, alias='EQUITY_EU_ESTIMATED_ROUND_TRIP_FEES')
    equity_eu_min_expected_net_profit: float = Field(default=5.00, alias='EQUITY_EU_MIN_EXPECTED_NET_PROFIT')
    equity_eu_force_close_enabled: bool = Field(default=True, alias='EQUITY_EU_FORCE_CLOSE_ENABLED')
    equity_eu_force_close_hour: int = Field(default=17, alias='EQUITY_EU_FORCE_CLOSE_HOUR')
    equity_eu_force_close_minute: int = Field(default=25, alias='EQUITY_EU_FORCE_CLOSE_MINUTE')
    equity_eu_max_spread_percent: float = Field(default=0.15, alias='EQUITY_EU_MAX_SPREAD_PERCENT')
    equity_eu_min_move_spread_ratio: float = Field(default=3.0, alias='EQUITY_EU_MIN_MOVE_SPREAD_RATIO')
    equity_eu_dynamic_sl_tp_enabled: bool = Field(default=False, alias='EQUITY_EU_DYNAMIC_SL_TP_ENABLED')
    equity_eu_stop_loss_atr_multiplier: float = Field(default=1.2, alias='EQUITY_EU_STOP_LOSS_ATR_MULTIPLIER')
    equity_eu_take_profit_atr_multiplier: float = Field(default=2.0, alias='EQUITY_EU_TAKE_PROFIT_ATR_MULTIPLIER')
    equity_eu_min_stop_loss_percent: float = Field(default=0.4, alias='EQUITY_EU_MIN_STOP_LOSS_PERCENT')
    equity_eu_max_stop_loss_percent: float = Field(default=1.5, alias='EQUITY_EU_MAX_STOP_LOSS_PERCENT')
    equity_eu_min_take_profit_percent: float = Field(default=0.8, alias='EQUITY_EU_MIN_TAKE_PROFIT_PERCENT')
    equity_eu_max_take_profit_percent: float = Field(default=3.0, alias='EQUITY_EU_MAX_TAKE_PROFIT_PERCENT')

    short_selling_enabled: bool = Field(default=False, alias='SHORT_SELLING_ENABLED')
    short_leverage: int = Field(default=1, alias='SHORT_LEVERAGE')

    force_close_hour: int = Field(default=21, alias='FORCE_CLOSE_HOUR')
    force_close_minute: int = Field(default=55, alias='FORCE_CLOSE_MINUTE')

    candle_timeframe_seconds: int = Field(default=60, alias='CANDLE_TIMEFRAME_SECONDS')

    journal_path: str = Field(default='data/logs/trades.jsonl', alias='JOURNAL_PATH')
    market_log_path: str = Field(default='data/logs/market.jsonl', alias='MARKET_LOG_PATH')
    candle_journal_path: str = Field(default='data/logs/candles.jsonl', alias='CANDLE_JOURNAL_PATH')

    def watchlist_symbols(self) -> list[str]:
        raw_symbols = self.watchlist if self.watchlist.strip() else self.default_symbol
        symbols: list[str] = []
        seen_symbols: set[str] = set()

        for raw_symbol in raw_symbols.split(','):
            symbol = raw_symbol.strip().upper()
            if not symbol:
                continue
            if symbol in seen_symbols:
                continue
            symbols.append(symbol)
            seen_symbols.add(symbol)

        if not symbols:
            raise ValueError('Watchlist cannot be empty.')

        return symbols


def get_settings() -> Settings:
    return Settings()
