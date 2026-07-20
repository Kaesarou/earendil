from datetime import datetime

from app.runtime.candidate_flow import execute_ranked_candidates
from app.runtime.position_lifecycle import close_positions_triggered_by_snapshot


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

    def _applied_monitored_symbols(self) -> list[str]:
        applied = set(self._applied_feed_symbols)
        return [
            symbol
            for symbol in self._desired_market_data_symbols()
            if symbol in applied
        ]

    def _run_position_fallback_if_due(
        self,
        now: datetime,
        monotonic_now: float,
    ) -> None:
        if not self.live_market_data.requires_websocket_health:
            return

        applied = set(self._applied_feed_symbols)
        open_symbols = list(
            dict.fromkeys(
                position.symbol.strip().upper()
                for position in self.position_tracker.open_positions_snapshot()
                if position.symbol.strip().upper() in applied
            )
        )
        if not open_symbols:
            return

        fallback_symbols = self.coordinator.position_fallback_symbols(
            symbols=open_symbols,
            now=now,
            force=not self.live_market_data.connection_healthy(),
        )
        if not fallback_symbols:
            return
        if (
            monotonic_now - self._last_position_fallback
            < self.settings.position_fallback_interval_seconds
        ):
            return
        self._last_position_fallback = monotonic_now

        try:
            snapshots = self.rest_market_data.get_market_snapshots(
                fallback_symbols
            )
        except Exception as exc:
            self.coordinator.mark_fallback_failed(fallback_symbols)
            self.trade_journal.write(
                'rest_position_fallback_error',
                {
                    'symbols': fallback_symbols,
                    'message': str(exc),
                    'loop_id': self.loop_id,
                },
            )
            return

        received_symbols = list(snapshots)
        if received_symbols:
            self.coordinator.mark_fallback_succeeded(received_symbols)
        missing = [
            symbol for symbol in fallback_symbols if symbol not in snapshots
        ]
        if missing:
            self.coordinator.mark_fallback_failed(missing)

        for symbol, snapshot in snapshots.items():
            self.trade_journal.write(
                'rest_position_fallback_snapshot',
                {
                    'symbol': symbol,
                    'snapshot': snapshot,
                    'loop_id': self.loop_id,
                },
            )
            close_positions_triggered_by_snapshot(
                symbol=symbol,
                snapshot=snapshot,
                executor=self.executor,
                position_tracker=self.position_tracker,
                risk_manager=self.risk_manager,
                trade_journal=self.trade_journal,
                position_store=self.position_store,
                cooldown_store=self.cooldown_store,
                is_broker_authorization_error=(
                    self.is_broker_authorization_error
                ),
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
        monitored = self._applied_monitored_symbols()
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
