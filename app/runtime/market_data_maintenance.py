from datetime import datetime, timezone

from app.market_data.models import MarketDataEvent, MarketDataSource
from app.runtime.candidate_flow import execute_ranked_candidates


class MarketDataMaintenance:
    def _all_monitored_symbols(self) -> list[str]:
        result = list(self.symbols)
        active_assets = {
            self.instrument_registry.resolve(symbol).asset_class
            for symbol in self.symbols
        }
        for asset_class, configured in (
            self.settings.benchmark_symbols_by_asset_class().items()
        ):
            if asset_class in active_assets:
                result.extend(configured)
        return list(
            dict.fromkeys(symbol.strip().upper() for symbol in result)
        )

    def _update_context_if_due(self, monotonic_now: float) -> None:
        if monotonic_now - self._last_context_update < 1.0:
            return
        self._last_context_update = monotonic_now
        relevant = {
            symbol: self.latest_snapshots[symbol]
            for symbol in [*self.active_symbols, *self.context_asset_classes]
            if symbol in self.latest_snapshots
        }
        if not relevant:
            return
        self.market_context_service.update(
            snapshots=relevant,
            session_decisions=self.session_decisions,
            context_asset_classes=self.context_asset_classes,
        )

    def _run_fallback_if_needed(self, now: datetime) -> None:
        monitored = list(
            dict.fromkeys([*self.active_symbols, *self.context_asset_classes])
        )
        stale = self.coordinator.stale_symbols(symbols=monitored, now=now)
        if not stale:
            return
        self.coordinator.mark_fallback_requested(stale, now)
        try:
            snapshots = self.rest_market_data.get_market_snapshots(stale)
        except Exception as exc:
            self.coordinator.mark_fallback_failed(stale)
            self.trade_journal.write(
                'rest_fallback_error',
                {
                    'symbols': stale,
                    'message': str(exc),
                    'loop_id': self.loop_id,
                },
            )
            return

        missing = [symbol for symbol in stale if symbol not in snapshots]
        if missing:
            self.coordinator.mark_fallback_failed(missing)
        received_at = datetime.now(timezone.utc)
        for symbol, snapshot in snapshots.items():
            self._handle_event(
                MarketDataEvent(
                    symbol=symbol,
                    source=MarketDataSource.REST_FALLBACK,
                    received_at=received_at,
                    snapshot=snapshot,
                    price_changed=True,
                ),
                received_at,
            )

    def _run_rest_control_if_due(
        self,
        now: datetime,
        monotonic_now: float,
    ) -> None:
        if not self.live_market_data.requires_websocket_health:
            return
        if (
            monotonic_now - self._last_rest_control
            < self.settings.rest_control_interval_seconds
        ):
            return
        self._last_rest_control = monotonic_now
        monitored = list(
            dict.fromkeys([*self.active_symbols, *self.context_asset_classes])
        )
        if not monitored:
            return
        try:
            snapshots = self.rest_market_data.get_market_snapshots(monitored)
        except Exception as exc:
            self.trade_journal.write(
                'rest_control_error',
                {
                    'symbols': monitored,
                    'message': str(exc),
                    'loop_id': self.loop_id,
                },
            )
            return

        received_at = datetime.now(timezone.utc)
        for symbol, snapshot in snapshots.items():
            websocket_snapshot = self.latest_snapshots.get(symbol)
            self.trade_journal.write(
                'rest_control_snapshot',
                {
                    'symbol': symbol,
                    'rest_snapshot': snapshot,
                    'websocket_snapshot': websocket_snapshot,
                    'last_delta': (
                        snapshot.last - websocket_snapshot.last
                        if websocket_snapshot is not None
                        else None
                    ),
                    'loop_id': self.loop_id,
                },
            )

    def _flush_decision_windows(self, now: datetime) -> None:
        for candidates in self.decision_windows.pop_ready(now=now):
            execute_ranked_candidates(
                candidates=candidates,
                execution_broker=self.execution_broker,
                risk_manager=self.risk_manager,
                executor=self.executor,
                position_tracker=self.position_tracker,
                trade_journal=self.trade_journal,
                position_store=self.position_store,
                strategy_profile=self.strategy_profile,
                cooldown_guard=self.cooldown_guard,
                candidate_economics_estimator=self.candidate_economics_estimator,
                is_broker_authorization_error=self.is_broker_authorization_error,
                pending_entry_manager=self.pending_entry_manager,
            )
