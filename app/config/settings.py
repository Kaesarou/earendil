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
    journal_path: str = Field(default='data/logs/trades.jsonl', alias='JOURNAL_PATH')
    market_log_path: str = Field(default='data/logs/market.jsonl', alias='MARKET_LOG_PATH')
    candle_journal_path: str = Field(default='data/logs/candles.jsonl', alias='CANDLE_JOURNAL_PATH')

    broker: str = Field(default='paper', alias='BROKER')
    log_level: str = Field(default='INFO', alias='LOG_LEVEL')
    poll_interval_seconds: int = Field(default=60, alias='POLL_INTERVAL_SECONDS')
    candle_timeframe_seconds: int = Field(default=60, alias='CANDLE_TIMEFRAME_SECONDS')

    etoro_api_key: str = Field(default='', alias='ETORO_API_KEY')
    etoro_user_key: str = Field(default='', alias='ETORO_USER_KEY')

    watchlist: str = Field(default='', alias='WATCHLIST')
    base_currency: str = Field(default='USD', alias='BASE_CURRENCY')
    strategy_aggressiveness: str = Field(default='balanced', alias='STRATEGY_AGGRESSIVENESS')

    max_open_positions: int = Field(default=1, alias='MAX_OPEN_POSITIONS')
    max_open_positions_per_symbol: int = Field(default=1, alias='MAX_OPEN_POSITIONS_PER_SYMBOL')
    max_trades_per_day: int = Field(default=3, alias='MAX_TRADES_PER_DAY')

    crypto_symbols: str = Field(default='', alias='CRYPTO_SYMBOLS')
    equity_us_symbols: str = Field(default='', alias='EQUITY_US_SYMBOLS')
    equity_eu_symbols: str = Field(default='', alias='EQUITY_EU_SYMBOLS')

    def watchlist_symbols(self) -> list[str]:
        raw_symbols = self.watchlist.strip()
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
