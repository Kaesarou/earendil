from app.instruments.crypto_config import CryptoConfig
from app.instruments.equity_eu_config import EquityEuConfig
from app.instruments.equity_us_config import EquityUsConfig
from app.instruments.models import AssetClass, InstrumentConfig

CRYPTO_CONFIG = CryptoConfig()
EQUITY_US_CONFIG = EquityUsConfig()
EQUITY_EU_CONFIG = EquityEuConfig()

BASE_INSTRUMENT_CONFIGS: dict[AssetClass, InstrumentConfig] = {
    AssetClass.CRYPTO: CRYPTO_CONFIG,
    AssetClass.EQUITY_US: EQUITY_US_CONFIG,
    AssetClass.EQUITY_EU: EQUITY_EU_CONFIG,
}
