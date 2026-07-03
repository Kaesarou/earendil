from app.instruments.models import AssetClass, RiskProfile
from app.strategies.strategy import strategy_profile_from_name

DEFAULT_RISK_PROFILES: dict[AssetClass, RiskProfile] = strategy_profile_from_name(
    'balanced'
).risk_profiles()


def risk_profiles_for_aggressiveness(name: str) -> dict[AssetClass, RiskProfile]:
    return strategy_profile_from_name(name).risk_profiles()
