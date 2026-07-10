from datetime import datetime, timedelta, timezone
from typing import Any

from app.config.settings import Settings
from app.journal.daily_summary import DailySummaryAggregator
from app.journal.journal_policy import (
    normalize_detail_level,
    should_write_to_debug_journal,
    should_write_to_errors_journal,
    should_write_to_trade_journal,
)
from app.journal.jsonl_journal import JsonlJournal


class AnalysisJournal:
    def __init__(
        self,
        *,
        trade_journal: JsonlJournal,
        errors_journal: JsonlJournal,
        summary_path: str,
        detail_level: str = 'normal',
        debug_decisions_journal: JsonlJournal | None = None,
        partial_summary_path: str | None = None,
        partial_summary_interval_minutes: int = 15,
        write_partial_summary: bool = True,
        run_id: str | None = None,
        strategy: str | None = None,
        profile: str | None = None,
    ):
        self.run_id = run_id
        self.trade_journal = trade_journal
        self.errors_journal = errors_journal
        self.debug_decisions_journal = debug_decisions_journal
        self.summary_path = summary_path
        self.partial_summary_path = partial_summary_path
        self.write_partial_summary = write_partial_summary
        self.detail_level = normalize_detail_level(detail_level)
        self.partial_summary_interval = timedelta(minutes=max(1, partial_summary_interval_minutes))
        self._last_partial_summary_at = datetime.now(timezone.utc)
        self._session_state_by_symbol: dict[str, tuple[Any, ...]] = {}
        self.summary = DailySummaryAggregator(
            run_id=run_id,
            strategy=strategy,
            profile=profile,
            journal_detail_level=self.detail_level,
        )

    def write(self, event_type: str, payload: dict[str, Any]) -> None:
        routed = self._normalize_event(event_type, payload)
        if routed is None:
            return

        routed_event_type, routed_payload = routed
        self.summary.record(routed_event_type, routed_payload)

        if should_write_to_errors_journal(routed_event_type):
            self.errors_journal.write(routed_event_type, routed_payload)

        if self.debug_decisions_journal is not None and should_write_to_debug_journal(
            routed_event_type,
            routed_payload,
            self.detail_level,
        ):
            self.debug_decisions_journal.write(routed_event_type, routed_payload)

        if should_write_to_trade_journal(routed_event_type, routed_payload, self.detail_level):
            written = self.trade_journal.write(routed_event_type, routed_payload)
            if written is False:
                self._record_trade_journal_write_failure(
                    routed_event_type,
                    routed_payload,
                )

        self._maybe_write_partial_summary()

    def record_raw_event(
        self,
        event_type: str,
        payload: dict[str, Any],
        written: bool,
    ) -> None:
        if written:
            self.summary.record(event_type, payload)
            self._maybe_write_partial_summary()
            return

        self.write(
            'raw_journal_error',
            {
                'event_type': event_type,
                'symbol': payload.get('symbol'),
                'message': 'Raw journal event could not be written.',
            },
        )

    def runtime_metrics(self) -> dict[str, Any]:
        summary = self.summary.to_dict()
        return {
            'market_snapshots': summary['market_data']['snapshots'],
            'candles_closed': summary['market_data']['candles_closed'],
            'candidates': summary['decisions']['candidate_total'],
            'selected': summary['decisions']['selected_total'],
            'orders_submitted': summary['orders']['submitted'],
            'positions_opened': summary['positions']['opened'],
            'positions_closed': summary['positions']['closed'],
            'errors': summary['errors']['total'],
        }

    def finalize(self) -> dict[str, Any]:
        summary = self.summary.finalize()
        self.summary.write(self.summary_path)
        if self.partial_summary_path:
            self.summary.write(self.partial_summary_path)
        return summary

    def _record_trade_journal_write_failure(
        self,
        failed_event_type: str,
        payload: dict[str, Any],
    ) -> None:
        failure_payload = {
            'failed_event_type': failed_event_type,
            'symbol': payload.get('symbol'),
            'message': 'Trade journal event could not be written.',
        }
        self.summary.record('journal_write_error', failure_payload)
        self.errors_journal.write('journal_write_error', failure_payload)

    def _normalize_event(
        self,
        event_type: str,
        payload: dict[str, Any],
    ) -> tuple[str, dict[str, Any]] | None:
        if event_type != 'session_state':
            return event_type, payload
        return self._session_state_change_event(payload)

    def _session_state_change_event(
        self,
        payload: dict[str, Any],
    ) -> tuple[str, dict[str, Any]] | None:
        symbol = payload.get('symbol')
        session_decision = payload.get('session_decision')
        if symbol is None or session_decision is None:
            return 'session_state_changed', payload

        new_state = _session_state_name(session_decision)
        signature = (
            new_state,
            _attribute(session_decision, 'reason'),
            _attribute(session_decision, 'session_key'),
            _attribute(session_decision, 'session_active'),
            _attribute(session_decision, 'collect_snapshots'),
            _attribute(session_decision, 'new_entries_allowed'),
            _attribute(session_decision, 'force_close_required'),
        )
        previous_signature = self._session_state_by_symbol.get(str(symbol))
        if previous_signature == signature:
            return None

        self._session_state_by_symbol[str(symbol)] = signature
        return (
            'session_state_changed',
            {
                'symbol': symbol,
                'previous_state': previous_signature[0] if previous_signature is not None else None,
                'new_state': new_state,
                'reason': _attribute(session_decision, 'reason'),
                'session_key': _attribute(session_decision, 'session_key'),
                'session_decision': session_decision,
            },
        )

    def _maybe_write_partial_summary(self) -> None:
        if not self.write_partial_summary or not self.partial_summary_path:
            return
        now = datetime.now(timezone.utc)
        if now - self._last_partial_summary_at < self.partial_summary_interval:
            return
        self.summary.write(self.partial_summary_path)
        self._last_partial_summary_at = now


def build_analysis_journal(settings: Settings, *, run_id: str | None = None) -> AnalysisJournal:
    detail_level = normalize_detail_level(settings.journal_detail_level)
    debug_enabled = detail_level in {'debug', 'full'} or settings.journal_keep_debug_decisions
    return AnalysisJournal(
        trade_journal=JsonlJournal(
            settings.journal_path,
            run_id=run_id,
            stream_name='trades',
        ),
        errors_journal=JsonlJournal(
            settings.errors_journal_path,
            run_id=run_id,
            stream_name='errors',
        ),
        debug_decisions_journal=(
            JsonlJournal(
                settings.debug_decisions_journal_path,
                run_id=run_id,
                stream_name='debug_decisions',
            )
            if debug_enabled
            else None
        ),
        summary_path=settings.daily_summary_path,
        partial_summary_path=settings.partial_daily_summary_path,
        detail_level=detail_level,
        write_partial_summary=settings.journal_write_partial_summary,
        partial_summary_interval_minutes=settings.journal_partial_summary_interval_minutes,
        run_id=run_id,
        strategy='TrendStrategy',
        profile=settings.strategy_aggressiveness,
    )


def _session_state_name(session_decision: Any) -> str:
    if not _attribute(session_decision, 'session_active'):
        return 'closed'
    if _attribute(session_decision, 'force_close_required'):
        return 'force_close'
    if not _attribute(session_decision, 'new_entries_allowed'):
        return 'no_new_entries'
    return 'active'


def _attribute(value: Any, name: str) -> Any:
    if value is None:
        return None
    if isinstance(value, dict):
        return value.get(name)
    return getattr(value, name, None)
