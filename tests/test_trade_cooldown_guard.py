from datetime import datetime, timedelta, timezone

from app.persistence.trade_cooldown_store import TradeCooldownStore
from app.risk.trade_cooldown import CloseReason, TradeCooldownConfig, TradeCooldownEntry
from app.risk.trade_cooldown_guard import TradeCooldownGuard


def save_cooldown(store: TradeCooldownStore) -> TradeCooldownEntry:
    closed_at = datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc)
    entry = TradeCooldownEntry(
        symbol='AMD',
        side='SELL',
        close_reason=CloseReason.TAKE_PROFIT,
        raw_close_reason='take_profit_hit',
        closed_at=closed_at,
        expires_at=closed_at + timedelta(minutes=30),
        position_id='position-1',
        created_at=closed_at,
    )
    return store.save_or_extend(entry)


def test_trade_cooldown_guard_blocks_same_symbol_and_side(tmp_path):
    store = TradeCooldownStore(str(tmp_path / 'earendil.sqlite'))
    entry = save_cooldown(store)
    guard = TradeCooldownGuard(store)

    decision = guard.check(
        symbol='amd',
        side='sell',
        config=TradeCooldownConfig(),
        now=entry.closed_at + timedelta(minutes=10),
    )

    assert not decision.allowed
    assert decision.reason == 'cooldown_after_take_profit'
    assert decision.remaining_seconds == 20 * 60


def test_trade_cooldown_guard_allows_opposite_side(tmp_path):
    store = TradeCooldownStore(str(tmp_path / 'earendil.sqlite'))
    entry = save_cooldown(store)
    guard = TradeCooldownGuard(store)

    decision = guard.check(
        symbol='AMD',
        side='BUY',
        config=TradeCooldownConfig(),
        now=entry.closed_at + timedelta(minutes=10),
    )

    assert decision.allowed


def test_trade_cooldown_guard_allows_when_disabled(tmp_path):
    store = TradeCooldownStore(str(tmp_path / 'earendil.sqlite'))
    entry = save_cooldown(store)
    guard = TradeCooldownGuard(store)

    decision = guard.check(
        symbol='AMD',
        side='SELL',
        config=TradeCooldownConfig(enabled=False),
        now=entry.closed_at + timedelta(minutes=10),
    )

    assert decision.allowed
