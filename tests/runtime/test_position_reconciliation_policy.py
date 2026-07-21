from datetime import datetime, timezone

from app.runtime.market_data_session_flow import MarketDataSessionFlow
from app.runtime.runtime_policy import POSITION_RECONCILIATION_INTERVAL_SECONDS


class RecordingCooldownStore:
    def __init__(self) -> None:
        self.deleted_at = []

    def delete_expired(self, now) -> None:
        self.deleted_at.append(now)


class RecordingBrokerOperations:
    def __init__(self) -> None:
        self.reconciled_at = []

    def schedule_reconciliation(self, *, now) -> None:
        self.reconciled_at.append(now)


class ReconciliationFlow(MarketDataSessionFlow):
    def __init__(self) -> None:
        self._last_position_reconciliation = 100.0
        self.cooldown_store = RecordingCooldownStore()
        self.broker_operations = RecordingBrokerOperations()


def test_reconciliation_uses_code_versioned_cadence_without_settings():
    flow = ReconciliationFlow()
    now = datetime(2026, 7, 21, 23, 45, tzinfo=timezone.utc)

    flow._reconcile_positions_if_due(
        now,
        100.0 + POSITION_RECONCILIATION_INTERVAL_SECONDS - 0.001,
    )
    assert flow.broker_operations.reconciled_at == []

    flow._reconcile_positions_if_due(
        now,
        100.0 + POSITION_RECONCILIATION_INTERVAL_SECONDS,
    )
    assert flow.cooldown_store.deleted_at == [now]
    assert flow.broker_operations.reconciled_at == [now]
