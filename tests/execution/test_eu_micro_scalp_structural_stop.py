from types import SimpleNamespace

from app.execution.eu_micro_scalp_fallback import (
    FALLBACK_SELECTION_MIN_SCORE,
    FALLBACK_TP_PERCENT,
    EuMicroScalpFallbackAdjuster,
)
from app.execution.sl_tp_profile import EffectiveSlTp


def test_micro_scalp_preserves_pending_structural_stop_and_metadata():
    adjuster = EuMicroScalpFallbackAdjuster(analyzer=SimpleNamespace())
    structural = EffectiveSlTp(
        stop_loss_percent=0.9,
        take_profit_percent=1.0,
        atr_percent=0.2,
        mode='dynamic',
        source='pending_structural',
        metadata={
            'entry_origin': 'pending_confirmation',
            'structural_invalidation_price': 99.1,
            'constant_risk_baseline_stop_loss_percent': 0.4,
        },
    )
    normal_candidate = SimpleNamespace(effective_sl_tp=structural)
    normal_analysis = SimpleNamespace(
        effective_take_profit_percent=1.0,
        effective_stop_loss_percent=0.9,
        adjusted_score=108.0,
        score_before_tp_feasibility=160.0,
        atr_percent=0.2,
    )

    result = adjuster._fallback_effective_sl_tp(
        normal_analysis=normal_analysis,
        normal_evaluated_candidate=normal_candidate,
    )

    assert result.source == 'pending_structural'
    assert result.stop_loss_percent == 0.9
    assert result.take_profit_percent == FALLBACK_TP_PERCENT
    assert result.metadata['entry_origin'] == 'pending_confirmation'
    assert result.metadata['structural_invalidation_price'] == 99.1
    assert result.metadata['constant_risk_baseline_stop_loss_percent'] == 0.4
    assert result.metadata['selection_min_score'] == FALLBACK_SELECTION_MIN_SCORE
