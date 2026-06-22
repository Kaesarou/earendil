from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    ear_mode: str = Field(default='paper', alias='EAR_MODE')
    log_level: str = Field(default='INFO', alias='LOG_LEVEL')
    poll_interval_seconds: int = Field(default=60, alias='POLL_INTERVAL_SECONDS')

    broker: str = Field(default='etoro', alias='BROKER')
    etoro_env: str = Field(default='demo', alias='ETORO_ENV')
    etoro_api_base_url: str = Field(default='https://api.etoro.com', alias='ETORO_API_BASE_URL')
    etoro_api_key: str = Field(default='', alias='ETORO_API_KEY')
    etoro_user_key: str = Field(default='', alias='ETORO_USER_KEY')

    default_symbol: str = Field(default='BTC', alias='DEFAULT_SYMBOL')
    base_currency: str = Field(default='USD', alias='BASE_CURRENCY')
    max_open_positions: int = Field(default=1, alias='MAX_OPEN_POSITIONS')
    max_trades_per_day: int = Field(default=3, alias='MAX_TRADES_PER_DAY')
    risk_per_trade_percent: float = Field(default=1.0, alias='RISK_PER_TRADE_PERCENT')
    max_position_size_percent: float = Field(default=20.0, alias='MAX_POSITION_SIZE_PERCENT')
    stop_loss_percent: float = Field(default=0.8, alias='STOP_LOSS_PERCENT')
    take_profit_percent: float = Field(default=1.2, alias='TAKE_PROFIT_PERCENT')
    force_close_hour: int = Field(default=21, alias='FORCE_CLOSE_HOUR')
    force_close_minute: int = Field(default=55, alias='FORCE_CLOSE_MINUTE')

    journal_path: str = Field(default='data/logs/trades.jsonl', alias='JOURNAL_PATH')
    market_log_path: str = Field(default='data/logs/market.jsonl', alias='MARKET_LOG_PATH')


def get_settings() -> Settings:
    return Settings()
