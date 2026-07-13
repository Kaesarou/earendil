from datetime import datetime, timezone

import pytest

from app.execution.sl_tp_profile import EffectiveSlTpResolver
from app.execution.trade_candidate import TradeCandidate
from app.instruments.models import AssetClass, RiskProfile
from app.market.models import Candle, MarketSnapshot
from app.strategies.signals import Signal


def risk_profile(*, dynamic_sl_tp_enabled: bool = True) -> RiskProfile:
    return RiskProfile(
        asset_class=AssetClass.EQUITY_US,
        max_position_size_percent=1.0,
        stop_loss_percent=0.9,
        take_profit_percent=1.6,
        force_close_enabled=False,
        force_close_hour=21,
        force_close_minute=55,
        max_spread_percent=1.0,
        min_move_spread_ratio=0.0,
        dynamic_sl_tp_enabled=dynamic_sl_tp_enabled,
        stop_loss_atr_multiplier=1.5,
        take_profit_atr_multiplier=2.5,
        min_stop_loss_percent=0.5,
        max_stop_loss_percent=2.0,
        min_take_profit_percent=1.0,
        max_take_profit_percent=4.0,
    )


def candidate(*, action: str = 'BUY', atr_percent: float | None = 0.8) -> TradeCandidate:
    now = datetime(2026, 7, 8, 12, 0, tzinfo=timezone.utc)
    snapshot = MarketSnapshot(
        symbol='AAPL',
        bid=99.95,
        ask=100.05,
        last=100.0,
        timestamp=now,
    )
    candle = Candle(
        symbol='AAPL',
        timeframe_seconds=60,
        open=99.5,
        high=100.5,
        low=99.0,
        close=100.0,
        volume=None,
        opened_at=now,
        closed_at=now,
    )
    metadata = {} if atr_percent is None else {'atr_percent': atr_percent}
    return TradeCandidate(
        symbol='AAPL',
        snapshot=snapshot,
        candle=candle,
        signal=Signal(action=action, setup_quality=0.8, reason='test', metadata=metadata),
        score=120.0,
        rank_reason='test',
    )


def test_resolver_uses_fixed_values_when_dynamic_is_disabled():
    effective_sl_tp = EffectiveSlTpResolver().resolve(
        candidate=candidate(atr_percent=0.8),
        risk_profile=risk_profile(dynamic_sl_tp_enabled=False),
    )

    assert effective_sl_tp.mode == 'fixed'
    assert effective_sl_tp.source == 'fixed'
    assert effective_sl_tp.stop_loss_percent == 0.9
    assert effective_sl_tp.take_profit_percent == 1.6
    assert effective_sl_tp.atr_percent == 0.8
    assert effective_sl_tp.dynamic_sl_tp_enabled is False


def test_resolver_falls_back_to_fixed_values_when_atr_is_missing():
    effective_sl_tp = EffectiveSlTpResolver().resolve(
        candidate=candidate(atr_percent=None),
        risk_profile=risk_profile(),
    )

    assert effective_sl_tp.mode == 'fixed'
    assert effective_sl_tp.source == 'missing_atr_fallback_fixed'
    assert effective_sl_tp.stop_loss_percent == 0.9
    assert effective_sl_tp.take_profit_percent == 1.6
    assert effective_sl_tp.atr_percent is None
    assert effective_sl_tp.metadata['fallback_reason'] == 'missing_or_invalid_atr_percent'


def test_resolver_floors_dynamic_values_when_atr_is_too_low():
    effective_sl_tp = EffectiveSlTpResolver().resolve(
        candidate=candidate(atr_percent=0.1),
        risk_profile=risk_profile(),
    )

    assert effective_sl_tp.mode == 'dynamic'
    assert effective_sl_tp.source == 'dynamic_floor'
    assert effective_sl_tp.dynamic_sl_raw_percent == pytest.approx(0.15)
    assert effective_sl_tp.dynamic_tp_raw_percent == pytest.approx(0.25)
    assert effective_sl_tp.stop_loss_percent == 0.5
    assert effective_sl_tp.take_profit_percent == 1.0


def test_resolver_uses_raw_dynamic_values_when_atr_is_inside_bounds():
    effective_sl_tp = EffectiveSlTpResolver().resolve(
        candidate=candidate(atr_percent=0.8),
        risk_profile=risk_profile(),
    )

    assert effective_sl_tp.mode == 'dynamic'
    assert effective_sl_tp.source == 'dynamic_raw'
    assert effective_sl_tp.stop_loss_percent == pytest.approx(1.2)
    assert effective_sl_tp.take_profit_percent == pytest.approx(2.0)
    assert effective_sl_tp.dynamic_sl_clamped_percent == pytest.approx(1.2)
    assert effective_sl_tp.dynamic_tp_clamped_percent == pytest.approx(2.0)


def test_resolver_caps_dynamic_values_when_atr_is_too_high():
    effective_sl_tp = EffectiveSlTpResolver().resolve(
        candidate=candidate(atr_percent=3.0),
        risk_profile=risk_profile(),
    )

    assert effective_sl_tp.mode == 'dynamic'
    assert effective_sl_tp.source == 'dynamic_cap'
    assert effective_sl_tp.dynamic_sl_raw_percent == pytest.approx(4.5)
    assert effective_sl_tp.dynamic_tp_raw_percent == pytest.approx(7.5)
    assert effective_sl_tp.stop_loss_percent == 2.0
    assert effective_sl_tp.take_profit_percent == 4.0


@pytest.mark.parametrize('action', ['BUY', 'SELL'])
def test_resolver_uses_same_percentages_for_buy_and_sell(action: str):
    effective_sl_tp = EffectiveSlTpResolver().resolve(
        candidate=candidate(action=action, atr_percent=0.8),
        risk_profile=risk_profile(),
    )

    assert effective_sl_tp.mode == 'dynamic'
    assert effective_sl_tp.stop_loss_percent == pytest.approx(1.2)
    assert effective_sl_tp.take_profit_percent == pytest.approx(2.0)
