from app.instruments.models import AssetClass, RiskProfile
from app.strategies.balanced_strategy_config import BalancedStrategyConfig


DEFAULT_RISK_PROFILES: dict[AssetClass, RiskProfile] = (
    BalancedStrategyConfig().risk_profiles()
)
