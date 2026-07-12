from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace

from app.execution.candidate_economics import CandidateEconomics, EvaluatedTradeCandidate
from app.execution.candidate_selector import CandidateSelectionConfig, selection_threshold_for
from app.execution.eu_micro_scalp_fallback import EuMicroScalpFallbackAdjuster
from app.execution.scoring.tp_feasibility import CandidateTpFeasibilityEvaluator, TpFeasibilityAnalyzer
from app.execution.sl_tp_profile import EffectiveSlTp
from app.execution.trade_candidate import TradeCandidate
from app.instruments.models import AssetClass, RiskProfile, TpFeasibilityConfig
from app.market.models import Candle, MarketSnapshot
from app.risk.trade_cost_model import TradeCostConfig
from app.strategies.signals import Signal


def _snapshot(symbol: str = 'SAN.PA') -> MarketSnapshot:
    now = datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc)
    return MarketSnapshot(symbol=symbol, bid=100.0, ask=100.0, last=100.0, timestamp=now)


def _candle(symbol: str = 'SAN.PA') -> Candle:
    now = datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc)
    return Candle(
        symbol=symbol,
        timeframe_seconds=60,
        open=99.5,
        high=100.2,
        low=99.4,
        close=100.0,
        volume=None,
        opened_at=now,
        closed_at=now,
    )


def _candidate(
    *,
    symbol: str = 'SAN.PA',
    score: float = 155.0,
    side: str = 'BUY',
    metadata: dict | None = None,
) -> TradeCandidate:
    return TradeCandidate(
        symbol=symbol,
        snapshot=_snapshot(symbol),
        candle=_candle(symbol),
        signal=Signal(
            action=side,
            confidence=0.8,
            reason='trend_bullish_breakout',
            metadata=metadata
            or {
                'atr_percent': 0.20,
                'snapshot_momentum_percent': 0.30,
                'session_move_percent': 0.30,
            },
        ),
        score=score,
        rank_reason='test_candidate',
        base_score=score,
        entry_quality_metadata={
            'distance_to_recent_high_percent': 1.0,
            'distance_to_recent_low_percent': 1.0,
        },
    )


def _economics(position_value: float = 1000.0) -> CandidateEconomics:
    return CandidateEconomics(
        position_value=position_value,
        expected_gross_profit=10.0,
        expected_net_profit=7.0,
        expected_net_profit_percent=0.70,
        estimated_total_cost=3.0,
        estimated_total_cost_percent=0.30,
        min_expected_net_profit_percent=0.10,
        required_min_expected_net_profit_amount=1.0,
        effective_take_profit_percent=1.0,
        effective_stop_loss_percent=0.7,
        cost_to_tp_ratio=0.30,
        reward_to_risk_ratio=1.4286,
        net_reward_to_risk_ratio=0.70,
    )


def _evaluated_candidate(
    *,
    candidate: TradeCandidate | None = None,
    economics: CandidateEconomics | None = None,
    effective_sl_tp: EffectiveSlTp | None = None,
) -> EvaluatedTradeCandidate:
    return EvaluatedTradeCandidate(
        candidate=candidate or _candidate(),
        economics=economics or _economics(),
        effective_sl_tp=effective_sl_tp,
    )


def _risk_profile(asset_class: AssetClass = AssetClass.EQUITY_EU) -> RiskProfile:
    return RiskProfile(
        asset_class=asset_class,
        max_position_size_percent=0.75,
        stop_loss_percent=0.70,
        take_profit_percent=1.00,
        force_close_enabled=False,
        force_close_hour=17,
        force_close_minute=25,
        max_spread_percent=0.15,
        min_move_spread_ratio=3.0,
        dynamic_sl_tp_enabled=False,
        stop_loss_atr_multiplier=1.2,
        take_profit_atr_multiplier=2.0,
        min_stop_loss_percent=0.4,
        max_stop_loss_percent=1.5,
        min_take_profit_percent=0.8,
        max_take_profit_percent=3.0,
        trade_cost=TradeCostConfig(
            open_fee_percent=0.15,
            close_fee_percent=0.15,
            include_spread_cost=True,
            min_expected_net_profit_percent=0.10,
        ),
        tp_feasibility=TpFeasibilityConfig(),
    )


def test_eu_micro_scalp_fallback_is_default_for_strong_eu_candidate_penalized_by_normal_tp():
    result = CandidateTpFeasibilityEvaluator().evaluate(
        evaluated_candidate=_evaluated_candidate(),
        risk_profile=_risk_profile(),
    )

    assert result.effective_sl_tp is not None
    assert result.effective_sl_tp.source == 'eu_micro_scalp_fallback'
    assert result.effective_sl_tp.take_profit_percent == 0.60
    assert result.effective_sl_tp.stop_loss_percent == 0.60
    assert result.effective_sl_tp.metadata['selection_min_score'] == 110.0
    assert result.candidate.score == 110.0
    assert result.candidate.tp_feasibility_metadata['adaptation'] == 'eu_micro_scalp_fallback'
    assert result.economics.expected_net_profit_percent == 0.30


def test_eu_micro_scalp_fallback_ignores_non_eu_candidates():
    result = CandidateTpFeasibilityEvaluator().evaluate(
        evaluated_candidate=_evaluated_candidate(candidate=_candidate(symbol='MSFT')),
        risk_profile=_risk_profile(AssetClass.EQUITY_US),
    )

    assert result.effective_sl_tp is None
    assert result.candidate.tp_feasibility_metadata.get('adaptation') is None


def test_eu_micro_scalp_fallback_refuses_weak_raw_score():
    result = CandidateTpFeasibilityEvaluator().evaluate(
        evaluated_candidate=_evaluated_candidate(candidate=_candidate(score=140.0)),
        risk_profile=_risk_profile(),
    )

    assert result.effective_sl_tp is None
    assert result.candidate.tp_feasibility_metadata.get('adaptation') is None


def test_selection_threshold_can_be_overridden_by_effective_sl_tp_metadata():
    evaluated_candidate = _evaluated_candidate()
    evaluated_candidate = EvaluatedTradeCandidate(
        candidate=evaluated_candidate.candidate,
        economics=evaluated_candidate.economics,
        effective_sl_tp=EffectiveSlTp(
            stop_loss_percent=0.6,
            take_profit_percent=0.6,
            atr_percent=0.2,
            mode='fixed',
            source='eu_micro_scalp_fallback',
            metadata={'selection_min_score': 110.0},
        ),
    )

    threshold, source = selection_threshold_for(
        evaluated_candidate,
        CandidateSelectionConfig(top_n=2, min_score=115.0),
    )

    assert threshold == 110.0
    assert source == 'effective_sl_tp_selection_min_score'


def test_pending_eu_micro_scalp_keeps_structural_stop_and_reduced_position_size():
    raw_candidate = _candidate(score=155.0)
    structural_sl_tp = EffectiveSlTp(
        stop_loss_percent=1.2,
        take_profit_percent=1.0,
        atr_percent=0.2,
        mode='fixed',
        source='pending_structural',
        metadata={
            'entry_origin': 'pending_confirmation',
            'structural_invalidation_price': 98.8,
            'structural_stop_valid': True,
            'constant_risk_baseline_stop_loss_percent': 0.6,
        },
    )
    normal_evaluated = _evaluated_candidate(
        candidate=replace(raw_candidate, score=108.0),
        economics=_economics(position_value=500.0),
        effective_sl_tp=structural_sl_tp,
    )
    normal_analysis = SimpleNamespace(
        effective_take_profit_percent=1.0,
        effective_stop_loss_percent=1.2,
        adjusted_score=108.0,
        score_before_tp_feasibility=155.0,
    )
    adjuster = EuMicroScalpFallbackAdjuster(TpFeasibilityAnalyzer())

    fallback_sl_tp = adjuster._fallback_effective_sl_tp(
        normal_analysis=normal_analysis,
        normal_evaluated_candidate=normal_evaluated,
    )
    fallback_evaluated = adjuster._with_fallback_economics(
        source_evaluated_candidate=normal_evaluated,
        fallback_candidate=raw_candidate,
        risk_profile=_risk_profile(),
        effective_sl_tp=fallback_sl_tp,
    )

    assert fallback_sl_tp.source == 'pending_structural'
    assert fallback_sl_tp.stop_loss_percent == 1.2
    assert fallback_sl_tp.take_profit_percent == 0.6
    assert fallback_sl_tp.metadata['structural_invalidation_price'] == 98.8
    assert fallback_sl_tp.metadata['adaptation'] == 'eu_micro_scalp_fallback'
    assert fallback_evaluated.candidate.score == 155.0
    assert fallback_evaluated.economics.position_value == 500.0
