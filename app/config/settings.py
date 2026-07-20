from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        extra='forbid',
    )

    app_log_path: str = Field(default='data/logs/goblin.log', alias='APP_LOG_PATH')
    position_store_path: str = Field(default='data/goblin.sqlite', alias='POSITION_STORE_PATH')
    journal_path: str = Field(default='data/logs/trades.jsonl', alias='JOURNAL_PATH')
    market_log_path: str = Field(default='data/logs/market.jsonl.gz', alias='MARKET_LOG_PATH')
    candle_journal_path: str = Field(
        default='data/logs/candles.jsonl.gz',
        alias='CANDLE_JOURNAL_PATH',
    )
    errors_journal_path: str = Field(default='data/logs/errors.jsonl', alias='ERRORS_JOURNAL_PATH')
    debug_decisions_journal_path: str = Field(
        default='data/logs/debug_decisions.jsonl.gz',
        alias='DEBUG_DECISIONS_JOURNAL_PATH',
    )
    daily_summary_path: str = Field(default='data/logs/daily_summary.json', alias='DAILY_SUMMARY_PATH')
    partial_daily_summary_path: str = Field(
        default='data/logs/daily_summary.partial.json',
        alias='PARTIAL_DAILY_SUMMARY_PATH',
    )
    run_manifest_path: str = Field(
        default='data/logs/run_manifest.json',
        alias='RUN_MANIFEST_PATH',
    )
    journal_detail_level: str = Field(default='normal', alias='JOURNAL_DETAIL_LEVEL')
    journal_keep_debug_decisions: bool = Field(
        default=False,
        alias='JOURNAL_KEEP_DEBUG_DECISIONS',
    )
    journal_write_partial_summary: bool = Field(
        default=True,
        alias='JOURNAL_WRITE_PARTIAL_SUMMARY',
    )
    journal_partial_summary_interval_minutes: int = Field(
        default=15,
        alias='JOURNAL_PARTIAL_SUMMARY_INTERVAL_MINUTES',
    )
    runtime_heartbeat_minutes: int = Field(
        default=5,
        alias='RUNTIME_HEARTBEAT_MINUTES',
    )

    broker: str = Field(default='paper', alias='BROKER')
    log_level: str = Field(default='INFO', alias='LOG_LEVEL')
    poll_interval_seconds: int = Field(default=10, alias='POLL_INTERVAL_SECONDS')

    market_data_mode: str = Field(default='auto', alias='MARKET_DATA_MODE')
    market_data_queue_capacity: int = Field(
        default=4096,
        alias='MARKET_DATA_QUEUE_CAPACITY',
    )
    ws_symbol_silence_seconds: float = Field(
        default=5.0,
        alias='WS_SYMBOL_SILENCE_SECONDS',
    )
    ws_global_silence_seconds: float = Field(
        default=15.0,
        alias='WS_GLOBAL_SILENCE_SECONDS',
    )
    rest_control_interval_seconds: float = Field(
        default=60.0,
        alias='REST_CONTROL_INTERVAL_SECONDS',
    )
    rest_fallback_cooldown_seconds: float = Field(
        default=5.0,
        alias='REST_FALLBACK_COOLDOWN_SECONDS',
    )
    decision_window_grace_seconds: float = Field(
        default=5.0,
        alias='DECISION_WINDOW_GRACE_SECONDS',
    )

    etoro_api_key: str = Field(default='', alias='ETORO_API_KEY')
    etoro_user_key: str = Field(default='', alias='ETORO_USER_KEY')
    etoro_sellshort_safety_sl_buffer_percent: float = Field(
        default=0.30,
        alias='ETORO_SELLSHORT_SAFETY_SL_BUFFER_PERCENT',
    )

    watchlist: str = Field(default='', alias='WATCHLIST')
    base_currency: str = Field(default='USD', alias='BASE_CURRENCY')
    max_open_positions: int = Field(default=1, alias='MAX_OPEN_POSITIONS')
    max_open_positions_per_symbol: int = Field(default=1, alias='MAX_OPEN_POSITIONS_PER_SYMBOL')
    max_trades_per_session: int = Field(default=3, alias='MAX_TRADES_PER_SESSION')

    crypto_symbols: str = Field(default='', alias='CRYPTO_SYMBOLS')
    equity_us_symbols: str = Field(default='', alias='EQUITY_US_SYMBOLS')
    equity_eu_symbols: str = Field(default='', alias='EQUITY_EU_SYMBOLS')
    market_benchmark_crypto: str = Field(
        default='Crypto10',
        alias='MARKET_BENCHMARK_CRYPTO',
    )
    market_benchmark_equity_us: str = Field(
        default='SPX500',
        alias='MARKET_BENCHMARK_EQUITY_US',
    )
    market_benchmark_equity_eu: str = Field(
        default='FRA40',
        alias='MARKET_BENCHMARK_EQUITY_EU',
    )
    trading_session_timezone: str = Field(default='Europe/Paris', alias='TRADING_SESSION_TIMEZONE')
    trading_sessions_crypto: str = Field(default='', alias='TRADING_SESSIONS_CRYPTO')
    trading_sessions_equity_us: str = Field(default='', alias='TRADING_SESSIONS_EQUITY_US')
    trading_sessions_equity_eu: str = Field(default='', alias='TRADING_SESSIONS_EQUITY_EU')

    def watchlist_symbols(self) -> list[str]:
        symbols = self._parse_symbols(self.watchlist)
        if not symbols:
            raise ValueError('Watchlist cannot be empty.')
        return symbols

    def benchmark_symbols_by_asset_class(self):
        from app.instruments.models import AssetClass

        return {
            AssetClass.CRYPTO: tuple(self._parse_symbols(self.market_benchmark_crypto)),
            AssetClass.EQUITY_US: tuple(self._parse_symbols(self.market_benchmark_equity_us)),
            AssetClass.EQUITY_EU: tuple(self._parse_symbols(self.market_benchmark_equity_eu)),
        }

    def _parse_symbols(self, raw_symbols: str) -> list[str]:
        symbols: list[str] = []
        seen_symbols: set[str] = set()
        for raw_symbol in raw_symbols.strip().split(','):
            symbol = raw_symbol.strip().upper()
            if not symbol or symbol in seen_symbols:
                continue
            symbols.append(symbol)
            seen_symbols.add(symbol)
        return symbols


def get_settings() -> Settings:
    return Settings()
