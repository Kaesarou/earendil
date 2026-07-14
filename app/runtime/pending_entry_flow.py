from app.execution.candidate_ranking import build_trade_candidate
from app.execution.trade_candidate import TradeCandidate
from app.instruments.models import EntryDecisionConfig
from app.journal.jsonl_journal import JsonlJournal
from app.market.market_context import CandidateMarketContext, ContextAlignment
from app.market.models import Candle, MarketSnapshot
from app.market.session_rules import TradingSessionDecision
from app.risk.risk_manager import RiskManager
from app.risk.trade_cooldown_guard import TradeCooldownGuard
from app.runtime.pending_entry import PendingEntryEvent, PendingEntryManager
from app.strategies.signals import Signal
from app.utils.commons import spread_percent


def advance_pending_entry(
    *,
    symbol: str,
    snapshot: MarketSnapshot,
    candle: Candle,
    signal: Signal,
    session_decision: TradingSessionDecision | None,
    risk_manager: RiskManager,
    pending_manager: PendingEntryManager,
    cooldown_guard: TradeCooldownGuard | None,
    trade_journal: JsonlJournal,
    market_context: CandidateMarketContext | None = None,
    entry_decision_config: EntryDecisionConfig | None = None,
    run_id: str = '',
) -> TradeCandidate | None:
    active_pending = next(
        (item for item in pending_manager.snapshot() if item.symbol == symbol),
        None,
    )
    if active_pending is None:
        return None

    if market_context is not None and market_context.alignment == ContextAlignment.OPPOSED:
        write_pending_events(
            trade_journal,
            pending_manager.invalidate_symbol(symbol, 'market_context_opposed'),
        )
        return None

    risk_profile = risk_manager.risk_profile_for(symbol)
    cooldown_active = False
    if cooldown_guard is not None:
        cooldown_active = not cooldown_guard.check(
            symbol=symbol,
            side=active_pending.side,
            config=risk_profile.trade_cooldown,
            now=candle.closed_at,
        ).allowed

    observation = pending_manager.observe(
        symbol=symbol,
        candle=candle,
        snapshot=snapshot,
        signal=signal,
        session_key=session_decision.session_key if session_decision else None,
        session_tradable=bool(
            session_decision
            and session_decision.new_entries_allowed
            and session_decision.session_key
        ),
        spread_percent=spread_percent(snapshot),
        max_spread_percent=risk_profile.max_spread_percent,
        config=risk_profile.entry_confirmation,
        cooldown_active=cooldown_active,
    )
    write_pending_events(trade_journal, observation.events)
    if observation.confirmed_pending is None or observation.confirmation_signal is None:
        return None

    candidate = build_trade_candidate(
        symbol=symbol,
        snapshot=snapshot,
        candle=candle,
        signal=observation.confirmation_signal,
        session_key=observation.confirmed_pending.session_key,
        run_id=run_id,
        market_context=market_context,
        entry_decision_config=entry_decision_config,
    )
    trade_journal.write(
        'candidate_detected',
        {
            'candidate_id': candidate.candidate_id,
            'symbol': symbol,
            'snapshot': snapshot,
            'candle': candle,
            'signal': observation.confirmation_signal,
            'candidate': candidate,
            'market_context': market_context,
            'session_decision': session_decision,
            'instrument_profile': risk_manager.instrument_profile_for(symbol),
            'risk_profile': risk_profile,
            'entry_origin': 'pending_confirmation',
        },
    )
    return candidate


def write_pending_events(
    trade_journal: JsonlJournal,
    events: tuple[PendingEntryEvent, ...],
) -> None:
    for event in events:
        trade_journal.write(
            event.event_type,
            {
                'symbol': event.pending.symbol,
                'side': event.pending.side,
                'session_key': event.pending.session_key,
                'pending_entry': event.pending,
                'reason': event.reason,
                'observed_candles': event.pending.observed_candles,
                'confirmation_type': event.pending.confirmation_type,
                'structural_invalidation_price': (
                    event.pending.structural_invalidation_price
                ),
            },
        )
