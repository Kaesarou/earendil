from dataclasses import dataclass

from app.execution.candidate_ranking import rank_trade_candidates
from app.execution.trade_candidate import TradeCandidate
from app.market.models import MarketSnapshot


@dataclass(frozen=True)
class PreScanConfig:
    enabled: bool = False
    top_n: int = 0
    min_score: float = 0.0
    allowed_market_regimes: tuple[str, ...] = ()
    max_spread_percent: float = 0.0
    min_session_move_percent: float = 0.0
    min_trend_strength_percent: float = 0.0
    min_atr_percent: float = 0.0
    max_atr_percent: float = 0.0
    max_noise_ratio: float = 0.0


@dataclass(frozen=True)
class RejectedPreScanCandidate:
    candidate: TradeCandidate
    reason: str


@dataclass(frozen=True)
class PreScanResult:
    selected_candidates: list[TradeCandidate]
    rejected_candidates: list[RejectedPreScanCandidate]


def pre_scan_candidates(
    candidates: list[TradeCandidate],
    config: PreScanConfig,
) -> PreScanResult:
    if not config.enabled:
        return PreScanResult(
            selected_candidates=rank_trade_candidates(candidates),
            rejected_candidates=[],
        )

    selected_candidates: list[TradeCandidate] = []
    rejected_candidates: list[RejectedPreScanCandidate] = []

    for candidate in rank_trade_candidates(candidates):
        rejection_reason = _pre_scan_rejection_reason(candidate, config)

        if rejection_reason is not None:
            rejected_candidates.append(
                RejectedPreScanCandidate(
                    candidate=candidate,
                    reason=rejection_reason,
                )
            )
            continue

        selected_candidates.append(candidate)

    if config.top_n > 0 and len(selected_candidates) > config.top_n:
        kept_candidates = selected_candidates[: config.top_n]
        overflow_candidates = selected_candidates[config.top_n:]
        rejected_candidates.extend(
            RejectedPreScanCandidate(
                candidate=candidate,
                reason='pre_scan_outside_top_n',
            )
            for candidate in overflow_candidates
        )
        selected_candidates = kept_candidates

    return PreScanResult(
        selected_candidates=selected_candidates,
        rejected_candidates=rejected_candidates,
    )


def _pre_scan_rejection_reason(
    candidate: TradeCandidate,
    config: PreScanConfig,
) -> str | None:
    metadata = candidate.signal.metadata or {}

    market_regime = str(metadata.get('market_regime', '')).upper()
    if config.allowed_market_regimes and market_regime:
        if market_regime not in config.allowed_market_regimes:
            return 'pre_scan_market_regime_rejected'

    spread_percent = spread_percent(candidate.snapshot)
    if config.max_spread_percent > 0 and spread_percent > config.max_spread_percent:
        return 'pre_scan_spread_too_high'

    session_move_percent = abs(
        _first_float_metadata(
            metadata,
            'session_move_percent',
            'regime_session_move_percent',
        )
    )
    if (
        config.min_session_move_percent > 0
        and session_move_percent < config.min_session_move_percent
    ):
        return 'pre_scan_session_move_too_low'

    trend_strength_percent = abs(
        _first_float_metadata(
            metadata,
            'trend_strength_percent',
            'regime_trend_strength_percent',
        )
    )
    if (
        config.min_trend_strength_percent > 0
        and trend_strength_percent < config.min_trend_strength_percent
    ):
        return 'pre_scan_trend_strength_too_low'

    atr_percent = _first_float_metadata(
        metadata,
        'atr_percent',
        'regime_atr_percent',
    )
    if config.min_atr_percent > 0 and atr_percent < config.min_atr_percent:
        return 'pre_scan_atr_too_low'

    if config.max_atr_percent > 0 and atr_percent > config.max_atr_percent:
        return 'pre_scan_atr_too_high'

    noise_ratio = _first_float_metadata(metadata, 'regime_noise_ratio')
    if config.max_noise_ratio > 0 and noise_ratio > config.max_noise_ratio:
        return 'pre_scan_noise_ratio_too_high'

    if candidate.score < config.min_score:
        return 'pre_scan_score_too_low'

    return None


def _first_float_metadata(metadata: dict, *keys: str) -> float:
    for key in keys:
        if key not in metadata:
            continue

        return _float_value(metadata.get(key))

    return 0.0


def _float_value(value) -> float:
    if value is None:
        return 0.0

    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
