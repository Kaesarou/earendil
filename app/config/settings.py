from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        extra='ignore',
    )

    ear_mode: str = Field(default='paper', alias='EAR_MODE')
    real_trading_enabled: bool = Field(default=False, alias='REAL_TRADING_ENABLED')
    log_level: str = Field(default='INFO', alias='LOG_LEVEL')
    poll_interval_seconds: int = Field(default=60, alias='POLL_INTERVAL_SECONDS')

    broker: str = Field(default='etoro', alias='BROKER')
    etoro_env: str = Field(default='demo', alias='ETORO_ENV')
    etoro_api_base_url: str = Field(
        default='https://public-api.etoro.com',
        alias='ETORO_API_BASE_URL',
    )
    etoro_api_key: str = Field(default='', alias='ETORO_API_KEY')
    etoro_user_key: str = Field(default='', alias='ETORO_USER_KEY')

    default_symbol: str = Field(default='BTC', alias='DEFAULT_SYMBOL')
    watchlist: str = Field(default='', alias='WATCHLIST')
    base_currency: str = Field(default='USD', alias='BASE_CURRENCY')

    investment_strategy: str = Field(default='breakout', alias='INVESTMENT_STRATEGY')
    breakout_lookback: int = Field(default=3, alias='BREAKOUT_LOOKBACK')
    breakout_min_breakout_percent: float = Field(
        default=0.05,
        alias='BREAKOUT_MIN_BREAKOUT_PERCENT',
    )

    risk_strategy: str = Field(default='fixed_percent', alias='RISK_STRATEGY')
    max_open_positions: int = Field(default=1, alias='MAX_OPEN_POSITIONS')
    max_open_positions_per_symbol: int = Field(
        default=1,
        alias='MAX_OPEN_POSITIONS_PER_SYMBOL',
    )
    max_trades_per_day: int = Field(default=3, alias='MAX_TRADES_PER_DAY')
    max_position_size_percent: float = Field(
        default=20.0,
        alias='MAX_POSITION_SIZE_PERCENT',
    )
    stop_loss_percent: float = Field(default=0.8, alias='STOP_LOSS_PERCENT')
    take_profit_percent: float = Field(default=1.2, alias='TAKE_PROFIT_PERCENT')
    estimated_round_trip_fees: float = Field(
        default=0.0,
        alias='ESTIMATED_ROUND_TRIP_FEES',
    )
    min_expected_net_profit: float = Field(
        default=0.0,
        alias='MIN_EXPECTED_NET_PROFIT',
    )
    force_close_hour: int = Field(default=21, alias='FORCE_CLOSE_HOUR')
    force_close_minute: int = Field(default=55, alias='FORCE_CLOSE_MINUTE')

    candle_timeframe_seconds: int = Field(
        default=60,
        alias='CANDLE_TIMEFRAME_SECONDS',
    )

    journal_path: str = Field(default='data/logs/trades.jsonl', alias='JOURNAL_PATH')
    market_log_path: str = Field(default='data/logs/market.jsonl', alias='MARKET_LOG_PATH')
    candle_journal_path: str = Field(
        default='data/logs/candles.jsonl',
        alias='CANDLE_JOURNAL_PATH',
    )

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