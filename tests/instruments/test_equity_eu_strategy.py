from app.execution.sl_tp_profile import EffectiveSlTpResolver
from app.instruments.base_configs import EQUITY_EU_CONFIG
from app.strategies.signals import Signal


def signal(side: str):
    return Signal(
        action=side,
        setup_quality=0.8,
        reason='test',
        metadata={'atr_percent': 0.4},
    )


def test_eu_buy_uses_longer_trend_profile():
    risk = EQUITY_EU_CONFIG.risk
    resolved = EffectiveSlTpResolver().resolve_for_signal(
        signal=signal('BUY'),
        risk_profile=risk,
    )
    assert resolved.source == 'eu_trend_buy_v1'
    assert resolved.take_profit_percent == 2.0
    assert resolved.stop_loss_percent == 1.2
    assert risk.stale_position_for('BUY').max_age_minutes == 180


def test_eu_sell_uses_named_standard_intraday_profile():
    risk = EQUITY_EU_CONFIG.risk
    resolved = EffectiveSlTpResolver().resolve_for_signal(
        signal=signal('SELL'),
        risk_profile=risk,
    )
    assert resolved.source == 'eu_intraday_fixed_v1'
    assert resolved.take_profit_percent == 1.0
    assert resolved.stop_loss_percent == 0.7
    assert risk.stale_position_for('SELL').max_age_minutes == 75


def test_micro_scalp_source_is_not_part_of_canonical_profile():
    risk = EQUITY_EU_CONFIG.risk
    sources = {
        EffectiveSlTpResolver().resolve_for_signal(
            signal=signal(side),
            risk_profile=risk,
        ).source
        for side in ('BUY', 'SELL')
    }
    assert 'eu_micro_scalp_fallback' not in sources
