from dataclasses import dataclass


@dataclass(frozen=True)
class StructuralStopResult:
    valid: bool
    reason: str | None
    invalidation_price: float | None
    structural_distance_percent: float
    volatility_distance_percent: float
    minimum_distance_percent: float
    effective_distance_percent: float


def calculate_structural_stop(
    *,
    side: str,
    entry_price: float,
    invalidation_price: float | None,
    atr_percent: float | None,
    atr_multiplier: float,
    minimum_distance_percent: float,
    spread_percent: float,
) -> StructuralStopResult:
    normalized_side = side.strip().upper()
    if entry_price <= 0 or invalidation_price is None or invalidation_price <= 0:
        return _invalid('missing_structural_invalidation', invalidation_price)
    if normalized_side == 'BUY' and invalidation_price >= entry_price:
        return _invalid('invalid_buy_structural_stop', invalidation_price)
    if normalized_side == 'SELL' and invalidation_price <= entry_price:
        return _invalid('invalid_sell_structural_stop', invalidation_price)
    if normalized_side not in {'BUY', 'SELL'}:
        return _invalid('unsupported_structural_stop_side', invalidation_price)

    raw_structural_distance = abs(entry_price - invalidation_price) / entry_price * 100
    structural_distance = raw_structural_distance + max(0.0, spread_percent)
    volatility_distance = max(0.0, atr_percent or 0.0) * max(0.0, atr_multiplier)
    minimum_distance = max(0.0, minimum_distance_percent)
    effective_distance = max(structural_distance, volatility_distance, minimum_distance)
    return StructuralStopResult(
        valid=True,
        reason=None,
        invalidation_price=invalidation_price,
        structural_distance_percent=structural_distance,
        volatility_distance_percent=volatility_distance,
        minimum_distance_percent=minimum_distance,
        effective_distance_percent=effective_distance,
    )


def _invalid(reason: str, invalidation_price: float | None) -> StructuralStopResult:
    return StructuralStopResult(
        valid=False,
        reason=reason,
        invalidation_price=invalidation_price,
        structural_distance_percent=0.0,
        volatility_distance_percent=0.0,
        minimum_distance_percent=0.0,
        effective_distance_percent=0.0,
    )
