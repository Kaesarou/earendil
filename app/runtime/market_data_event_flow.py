from datetime import datetime, timezone

from app.market.data_quality import MarketDataStatus
from app.market_data.models import MarketDataEvent, MarketDataSource
from app.runtime.symbol_flow import process_closed_candle, process_symbol


class MarketDataEventFlow:
    def _handle_event(self, event: MarketDataEvent, now: datetime) -> None:
        symbol = event.symbol.strip().upper()
        precheck = self.coordinator.precheck(event)
        self.trade_journal.write(
            'market_data_event_received',
            {
                'symbol': symbol,
                'source': event.source.value,
                'message_id': event.message_id,
                'price_rate_id': event.price_rate_id,
                'connection_id': event.connection_id,
                'price_changed': event.price_changed,
                'state_reconstructed': event.state_reconstructed,
                'received_at': event.received_at,
                'snapshot': event.snapshot,
                'precheck': precheck.reason,
                'loop_id': self.loop_id,
            },
        )
        if not precheck.accepted:
            self._record_precheck_rejection(symbol, event, precheck.reason)
            return

        snapshot = event.snapshot
        if snapshot is None:
            return
        config = self._market_data_quality_config(symbol)
        validation = self.market_data_validator.validate(
            snapshot,
            config,
            now=now,
        )
        if validation.status != MarketDataStatus.ACCEPTED:
            event_type = (
                'market_data_quarantined'
                if validation.status == MarketDataStatus.QUARANTINED
                else 'market_data_rejected'
            )
            self.trade_journal.write(
                event_type,
                {
                    'symbol': symbol,
                    'validation': validation,
                    'source': event.source.value,
                    'loop_id': self.loop_id,
                },
            )
            return

        accepted = self.coordinator.mark_accepted(event)
        self.latest_snapshots[symbol] = snapshot
        self.market_journal.write(
            'market_snapshot_received',
            {
                'symbol': symbol,
                'snapshot': snapshot,
                'source': event.source.value,
                'loop_id': self.loop_id,
            },
        )

        if symbol not in self.active_symbols:
            return

        session_decision = self.session_decisions.get(symbol)
        if session_decision is None:
            return

        current_bucket = _minute_bucket(snapshot.timestamp)
        previous_bucket = self._last_bucket_by_symbol.get(symbol)
        closing_bucket = (
            previous_bucket
            if previous_bucket is not None and current_bucket > previous_bucket
            else None
        )
        if event.source == MarketDataSource.REST_FALLBACK:
            self._degraded_buckets.add((symbol, current_bucket))

        entry_allowed = accepted.entry_allowed
        if closing_bucket is not None and (symbol, closing_bucket) in self._degraded_buckets:
            entry_allowed = False
        effective_session_decision = (
            session_decision
            if entry_allowed
            else session_decision._replace(
                new_entries_allowed=False,
                reason='market_data_degraded',
            )
        )

        builder = self.candle_builders[symbol]
        candidate = None
        if event.price_changed:
            builder.prepare_event(event)
            candidate = process_symbol(
                symbol=symbol,
                broker=self.execution_broker,
                strategy=self.strategies[symbol],
                risk_manager=self.risk_manager,
                executor=self.executor,
                position_tracker=self.position_tracker,
                candle_builder=builder,
                trade_journal=self.trade_journal,
                market_journal=self.market_journal,
                candle_journal=self.candle_journal,
                is_broker_authorization_error=self.is_broker_authorization_error,
                position_store=self.position_store,
                cooldown_store=self.cooldown_store,
                snapshot=snapshot,
                session_decision=effective_session_decision,
                loop_id=self.loop_id,
                pending_entry_manager=self.pending_entry_manager,
                cooldown_guard=self.cooldown_guard,
                market_context_service=self.market_context_service,
                multi_timeframe_service=self.multi_timeframe_service,
                run_id=self.run_id,
            )
        else:
            builder.prepare_event(event)
            closed_candle = builder.on_snapshot(snapshot)
            if closed_candle is not None:
                candidate = process_closed_candle(
                    symbol=symbol,
                    snapshot=snapshot,
                    closed_candle=closed_candle,
                    strategy=self.strategies[symbol],
                    risk_manager=self.risk_manager,
                    trade_journal=self.trade_journal,
                    candle_journal=self.candle_journal,
                    session_decision=effective_session_decision,
                    loop_id=self.loop_id,
                    pending_entry_manager=self.pending_entry_manager,
                    cooldown_guard=self.cooldown_guard,
                    market_context_service=self.market_context_service,
                    multi_timeframe_service=self.multi_timeframe_service,
                    run_id=self.run_id,
                )

        if previous_bucket is None or current_bucket >= previous_bucket:
            self._last_bucket_by_symbol[symbol] = current_bucket

        closed_result = builder.take_last_closed_result()
        if closed_result is None:
            return
        self.candle_journal.write(
            'candle_quality',
            {
                'symbol': symbol,
                'candle': closed_result.candle,
                'quality': closed_result.quality,
                'entry_allowed': entry_allowed,
                'feed_state': self.coordinator.state_for(symbol).value,
                'loop_id': self.loop_id,
            },
        )
        self.decision_windows.record(
            closed_at=closed_result.candle.closed_at,
            symbol=symbol,
            expected_symbols=self.active_symbols,
            candidate=candidate,
        )
        self._degraded_buckets.discard((symbol, closed_result.candle.opened_at))

    def _record_precheck_rejection(
        self,
        symbol: str,
        event: MarketDataEvent,
        reason: str,
    ) -> None:
        if reason == 'strict_out_of_order_timestamp' and symbol in self.candle_builders:
            self.candle_builders[symbol].record_out_of_order_drop()
            bucket = self._last_bucket_by_symbol.get(symbol)
            if bucket is not None:
                self._degraded_buckets.add((symbol, bucket))
        self.trade_journal.write(
            'market_data_event_ignored',
            {
                'symbol': symbol,
                'source': event.source.value,
                'reason': reason,
                'message_id': event.message_id,
                'loop_id': self.loop_id,
            },
        )

    def _market_data_quality_config(self, symbol: str):
        if symbol in self.symbols:
            return self.instrument_registry.config_for(symbol).market_data_quality
        asset_class = self.context_asset_classes.get(symbol)
        if asset_class is None:
            for candidate_asset, configured_symbols in (
                self.settings.benchmark_symbols_by_asset_class().items()
            ):
                if symbol in configured_symbols:
                    asset_class = candidate_asset
                    break
        if asset_class is None:
            asset_class = self.instrument_registry.resolve(symbol).asset_class
        return self.strategy_profile.instrument_config_for_asset_class(
            asset_class
        ).market_data_quality


def _minute_bucket(value: datetime) -> datetime:
    actual = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    return actual.astimezone(timezone.utc).replace(second=0, microsecond=0)
