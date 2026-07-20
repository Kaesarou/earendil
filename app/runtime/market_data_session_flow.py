from app.instruments.models import AssetClass
from app.market.timeframes import BarCompleteness
from app.runtime.pending_entry_flow import write_pending_events
from app.runtime.position_lifecycle import reconcile_externally_closed_positions
from app.runtime.session_runtime import filter_symbols_by_trading_session
from app.strategies.strategy import TrendStrategy


class MarketDataSessionFlow:
    def _refresh_sessions_if_due(self, now, monotonic_now: float) -> None:
        if monotonic_now - self._last_session_refresh < 1.0:
            return
        self._last_session_refresh = monotonic_now
        (
            active_symbols,
            session_decisions,
            started_symbols,
            completed_session_keys,
        ) = filter_symbols_by_trading_session(
            symbols=self.symbols,
            instrument_registry=self.instrument_registry,
            trading_session_service=self.trading_session_service,
            trading_session_state=self.trading_session_state,
            now=now,
        )
        self.active_symbols = active_symbols
        self.session_decisions = session_decisions
        self.context_asset_classes = self._context_symbols_for_active_assets(
            active_symbols
        )
        for symbol, decision in session_decisions.items():
            self.trade_journal.write(
                'session_state',
                {
                    'symbol': symbol,
                    'session_decision': decision,
                    'loop_id': self.loop_id,
                },
            )

        for session_key in completed_session_keys:
            self.risk_manager.reset_session_trades(session_key)
            self.market_context_service.reset_session(session_key)
            write_pending_events(
                self.trade_journal,
                self.pending_entry_manager.invalidate_session(session_key),
            )
            self.trade_journal.write(
                'session_trades_reset',
                {'session_key': session_key, 'loop_id': self.loop_id},
            )
        for symbol in started_symbols:
            self.market_data_validator.reset_symbol(symbol)
            self.coordinator.reset_symbol(symbol, now=now)
            self.decision_windows.reset_symbol(symbol)
            self._write_partial_timeframe_bars(
                symbol,
                self.multi_timeframe_service.reset_symbol(symbol),
            )
            self.candle_builders[symbol].reset()
            self.strategies[symbol] = TrendStrategy(
                self.instrument_registry.config_for(symbol).trend
            )
            self._last_bucket_by_symbol.pop(symbol, None)
            self._degraded_buckets = {
                item for item in self._degraded_buckets if item[0] != symbol
            }
            self.trade_journal.write(
                'session_started',
                {
                    'symbol': symbol,
                    'session_decision': session_decisions[symbol],
                    'loop_id': self.loop_id,
                },
            )

    def _reconcile_positions_if_due(self, now, monotonic_now: float) -> None:
        if (
            monotonic_now - self._last_position_reconciliation
            < self.settings.poll_interval_seconds
        ):
            return
        self._last_position_reconciliation = monotonic_now
        self.cooldown_store.delete_expired(now)
        reconcile_externally_closed_positions(
            broker=self.execution_broker,
            position_tracker=self.position_tracker,
            risk_manager=self.risk_manager,
            position_store=self.position_store,
            cooldown_store=self.cooldown_store,
            trade_journal=self.trade_journal,
            is_broker_authorization_error=self.is_broker_authorization_error,
        )

    def _context_symbols_for_active_assets(
        self,
        active_symbols: list[str],
    ) -> dict[str, AssetClass]:
        active_assets = {
            self.instrument_registry.resolve(symbol).asset_class
            for symbol in active_symbols
        }
        result: dict[str, AssetClass] = {}
        for asset_class, symbols in (
            self.settings.benchmark_symbols_by_asset_class().items()
        ):
            if asset_class not in active_assets:
                continue
            for symbol in symbols:
                if symbol not in active_symbols:
                    result[symbol] = asset_class
        return result

    def _write_partial_timeframe_bars(self, symbol: str, bars) -> None:
        for bar in bars:
            event_type = (
                'timeframe_bar_partial'
                if bar.completeness == BarCompleteness.PARTIAL
                else 'timeframe_bar_incomplete'
            )
            self.candle_journal.write(
                event_type,
                {
                    'symbol': symbol,
                    'timeframe': bar.timeframe.name.lower(),
                    'timeframe_bar': bar,
                    'loop_id': self.loop_id,
                },
            )
