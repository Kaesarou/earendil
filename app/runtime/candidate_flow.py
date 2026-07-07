import logging
from collections.abc import Callable
from datetime import datetime, timezone
from typing import TypeVar

from app.brokers.base import BrokerClient
from app.execution.candidate_economics import CandidateEconomicsEstimator, EvaluatedTradeCandidate
from app.execution.candidate_ranking import rank_trade_candidates
from app.execution.candidate_selector import CandidateSelectionResult, EvaluatedCandidateSelectionResult, RejectedCandidateSelection, RejectedEvaluatedCandidateSelection, rank_evaluated_trade_candidates, select_evaluated_trade_candidates, select_trade_candidates
from app.execution.position_tracker import PositionTracker
from app.execution.scoring.tp_feasibility import CandidateTpFeasibilityEvaluator
from app.execution.sl_tp_profile import EffectiveSlTp, EffectiveSlTpResolver
from app.execution.trade_candidate import TradeCandidate
from app.execution.trade_executor import TradeExecutor
from app.journal.jsonl_journal import JsonlJournal
from app.persistence.position_store import PositionStore
from app.risk.models import TradePlan
from app.risk.risk_manager import RiskManager
from app.risk.trade_cooldown_guard import TradeCooldownGuard
from app.strategies.strategy import StrategyProfileConfig

logger = logging.getLogger(__name__)
BrokerAuthorizationErrorChecker = Callable[[Exception], bool]
SelectedItem = TypeVar('SelectedItem')
RejectedItem = TypeVar('RejectedItem')


def _smallest_positive_top_n(top_n_limits: list[int]) -> int:
    positive_top_n_limits = [limit for limit in top_n_limits if limit > 0]
    return min(positive_top_n_limits) if positive_top_n_limits else 0


def _apply_top_n_limit(*, selected_items: list[SelectedItem], rejected_items: list[RejectedItem], top_n_limits: list[int], build_rejection: Callable[[SelectedItem], RejectedItem]) -> tuple[list[SelectedItem], list[RejectedItem]]:
    top_n = _smallest_positive_top_n(top_n_limits)
    if top_n <= 0 or len(selected_items) <= top_n:
        return selected_items, rejected_items
    kept_items = selected_items[:top_n]
    rejected_items.extend(build_rejection(item) for item in selected_items[top_n:])
    return kept_items, rejected_items


def select_trade_candidates_with_strategy_profile(candidates: list[TradeCandidate], risk_manager: RiskManager, strategy_profile: StrategyProfileConfig) -> CandidateSelectionResult:
    selected_candidates: list[TradeCandidate] = []
    rejected_candidates: list[RejectedCandidateSelection] = []
    top_n_limits: list[int] = []
    for candidate in rank_trade_candidates(candidates):
        asset_class = risk_manager.instrument_profile_for(candidate.symbol).asset_class
        config = strategy_profile.candidate_selection_config_for_asset_class(asset_class)
        top_n_limits.append(config.top_n)
        result = select_trade_candidates([candidate], config)
        if result.selected_candidates:
            selected_candidates.append(candidate)
        else:
            rejected_candidates.extend(result.rejected_candidates)
    selected_candidates, rejected_candidates = _apply_top_n_limit(
        selected_items=selected_candidates,
        rejected_items=rejected_candidates,
        top_n_limits=top_n_limits,
        build_rejection=lambda candidate: RejectedCandidateSelection(candidate=candidate, reason='candidate_selection_outside_top_n'),
    )
    return CandidateSelectionResult(selected_candidates=selected_candidates, rejected_candidates=rejected_candidates)


def select_evaluated_trade_candidates_with_strategy_profile(evaluated_candidates: list[EvaluatedTradeCandidate], risk_manager: RiskManager, strategy_profile: StrategyProfileConfig) -> EvaluatedCandidateSelectionResult:
    selected_candidates: list[EvaluatedTradeCandidate] = []
    rejected_candidates: list[RejectedEvaluatedCandidateSelection] = []
    top_n_limits: list[int] = []
    for evaluated_candidate in rank_evaluated_trade_candidates(evaluated_candidates):
        candidate = evaluated_candidate.candidate
        asset_class = risk_manager.instrument_profile_for(candidate.symbol).asset_class
        config = strategy_profile.candidate_selection_config_for_asset_class(asset_class)
        top_n_limits.append(config.top_n)
        result = select_evaluated_trade_candidates([evaluated_candidate], config)
        if result.selected_candidates:
            selected_candidates.append(evaluated_candidate)
        else:
            rejected_candidates.extend(result.rejected_candidates)
    selected_candidates, rejected_candidates = _apply_top_n_limit(
        selected_items=selected_candidates,
        rejected_items=rejected_candidates,
        top_n_limits=top_n_limits,
        build_rejection=lambda evaluated_candidate: RejectedEvaluatedCandidateSelection(evaluated_candidate=evaluated_candidate, reason='candidate_selection_outside_top_n'),
    )
    return EvaluatedCandidateSelectionResult(selected_candidates=selected_candidates, rejected_candidates=rejected_candidates)


def _legacy_selection_result_from_evaluated(selection_result: EvaluatedCandidateSelectionResult) -> CandidateSelectionResult:
    return CandidateSelectionResult(
        selected_candidates=[item.candidate for item in selection_result.selected_candidates],
        rejected_candidates=[RejectedCandidateSelection(candidate=item.evaluated_candidate.candidate, reason=item.reason) for item in selection_result.rejected_candidates],
    )


def apply_trade_cooldown_guard(*, candidates: list[TradeCandidate], risk_manager: RiskManager, cooldown_guard: TradeCooldownGuard, trade_journal: JsonlJournal) -> list[TradeCandidate]:
    now = datetime.now(timezone.utc)
    cooldown_guard.store.delete_expired(now)
    result = cooldown_guard.filter_candidates(candidates=candidates, risk_manager=risk_manager, now=now)
    if not result.rejected_candidates:
        return result.selected_candidates
    trade_journal.write('trade_cooldown_guard', {'selected_candidates': result.selected_candidates, 'rejected_candidates': result.rejected_candidates})
    for rejected in result.rejected_candidates:
        candidate = rejected.candidate
        decision = rejected.decision
        plan = TradePlan(approved=False, reason=decision.reason or 'trade_cooldown_active', symbol=candidate.symbol, side=candidate.signal.action)
        trade_journal.write('decision', {'symbol': candidate.symbol, 'snapshot': candidate.snapshot, 'candle': candidate.candle, 'signal': candidate.signal, 'candidate': candidate, 'equity': None, 'trade_plan': plan, 'cooldown': decision.active_cooldown, 'cooldown_remaining_seconds': decision.remaining_seconds, 'instrument_profile': risk_manager.instrument_profile_for(candidate.symbol), 'risk_profile': risk_manager.risk_profile_for(candidate.symbol)})
        logger.info('Trade rejected by cooldown | symbol=%s | action=%s | reason=%s | remaining_seconds=%s', candidate.symbol, candidate.signal.action, plan.reason, decision.remaining_seconds)
    return result.selected_candidates


def apply_tp_feasibility_to_evaluated_candidates(*, evaluated_candidates: list[EvaluatedTradeCandidate], risk_manager: RiskManager, evaluator: CandidateTpFeasibilityEvaluator | None = None) -> list[EvaluatedTradeCandidate]:
    actual_evaluator = evaluator or CandidateTpFeasibilityEvaluator()
    return [
        actual_evaluator.evaluate(evaluated_candidate=evaluated_candidate, risk_profile=risk_manager.risk_profile_for(evaluated_candidate.candidate.symbol))
        for evaluated_candidate in evaluated_candidates
    ]


def _slippage_percent(*, planned_entry_price: float, effective_entry_price: float) -> float | None:
    if planned_entry_price <= 0:
        return None
    return round(((effective_entry_price - planned_entry_price) / planned_entry_price) * 100, 4)


def _risk_profile_supports_effective_sl_tp(risk_profile: object) -> bool:
    return hasattr(risk_profile, 'dynamic_sl_tp_enabled')


def _resolve_runtime_effective_sl_tp(*, candidate: TradeCandidate, risk_profile: object, resolver: EffectiveSlTpResolver) -> EffectiveSlTp | None:
    if not _risk_profile_supports_effective_sl_tp(risk_profile):
        return None
    return resolver.resolve(candidate=candidate, risk_profile=risk_profile)


def _evaluate_risk_manager(*, risk_manager: RiskManager, candidate: TradeCandidate, equity: float, effective_sl_tp: EffectiveSlTp | None) -> TradePlan:
    if effective_sl_tp is None:
        return risk_manager.evaluate(signal=candidate.signal, snapshot=candidate.snapshot, account_equity=equity, session_key=candidate.session_key)
    return risk_manager.evaluate(signal=candidate.signal, snapshot=candidate.snapshot, account_equity=equity, session_key=candidate.session_key, effective_sl_tp=effective_sl_tp)


def execute_ranked_candidates(
    candidates: list[TradeCandidate], execution_broker: BrokerClient, risk_manager: RiskManager, executor: TradeExecutor, position_tracker: PositionTracker, trade_journal: JsonlJournal, position_store: PositionStore | None = None, strategy_profile: StrategyProfileConfig | None = None, cooldown_guard: TradeCooldownGuard | None = None, candidate_economics_estimator: CandidateEconomicsEstimator | None = None, is_broker_authorization_error: BrokerAuthorizationErrorChecker | None = None,
) -> None:
    if not candidates:
        return
    if cooldown_guard is not None:
        candidates = apply_trade_cooldown_guard(candidates=candidates, risk_manager=risk_manager, cooldown_guard=cooldown_guard, trade_journal=trade_journal)
        if not candidates:
            return
    selected_evaluated_candidates: list[EvaluatedTradeCandidate] | None = None
    rejected_evaluated_candidates: list[RejectedEvaluatedCandidateSelection] | None = None
    if candidate_economics_estimator is None:
        if strategy_profile is None:
            ranked_candidates = rank_trade_candidates(candidates)
            selection_result = CandidateSelectionResult(selected_candidates=ranked_candidates, rejected_candidates=[])
        else:
            selection_result = select_trade_candidates_with_strategy_profile(candidates, risk_manager, strategy_profile)
            ranked_candidates = selection_result.selected_candidates
    else:
        selection_equity = execution_broker.get_account_equity()
        evaluated_candidates = [candidate_economics_estimator.evaluate(candidate=candidate, account_equity=selection_equity) for candidate in candidates]
        trade_journal.write('candidate_economics', {'equity': selection_equity, 'evaluated_candidates': evaluated_candidates})
        evaluated_candidates = apply_tp_feasibility_to_evaluated_candidates(evaluated_candidates=evaluated_candidates, risk_manager=risk_manager)
        trade_journal.write('candidate_tp_feasibility', {'equity': selection_equity, 'evaluated_candidates': evaluated_candidates})
        if strategy_profile is None:
            evaluated_selection = EvaluatedCandidateSelectionResult(selected_candidates=rank_evaluated_trade_candidates(evaluated_candidates), rejected_candidates=[])
        else:
            evaluated_selection = select_evaluated_trade_candidates_with_strategy_profile(evaluated_candidates, risk_manager, strategy_profile)
        selected_evaluated_candidates = evaluated_selection.selected_candidates
        rejected_evaluated_candidates = evaluated_selection.rejected_candidates
        selection_result = _legacy_selection_result_from_evaluated(evaluated_selection)
        ranked_candidates = selection_result.selected_candidates
    trade_journal.write('candidate_selection', {'strategy_profile': strategy_profile.name if strategy_profile else None, 'selected_candidates': selection_result.selected_candidates, 'rejected_candidates': selection_result.rejected_candidates, 'selected_evaluated_candidates': selected_evaluated_candidates, 'rejected_evaluated_candidates': rejected_evaluated_candidates})
    logger.info('Candidate selection | profile=%s | selected=%s | rejected=%s', strategy_profile.name if strategy_profile else None, [c.symbol for c in selection_result.selected_candidates], [{'symbol': r.candidate.symbol, 'reason': r.reason} for r in selection_result.rejected_candidates])
    if not ranked_candidates:
        return
    economics_by_id = {id(item.candidate): item.economics for item in selected_evaluated_candidates or []}
    feasibility_by_id = {id(item.candidate): item.tp_feasibility for item in selected_evaluated_candidates or []}
    effective_sl_tp_by_id = {id(item.candidate): item.effective_sl_tp for item in selected_evaluated_candidates or []}
    sl_tp_resolver = EffectiveSlTpResolver()
    trade_journal.write('candidate_ranking', {'candidates': ranked_candidates, 'evaluated_candidates': selected_evaluated_candidates})
    logger.info('Candidate ranking | candidates=%s', [
        {
            'symbol': candidate.symbol,
            'action': candidate.signal.action,
            'score': candidate.score,
            'expected_net_profit': round(economics_by_id[id(candidate)].expected_net_profit, 4) if id(candidate) in economics_by_id else None,
            'expected_net_profit_percent': round(economics_by_id[id(candidate)].expected_net_profit_percent, 4) if id(candidate) in economics_by_id else None,
            'effective_take_profit_percent': effective_sl_tp_by_id[id(candidate)].take_profit_percent if id(candidate) in effective_sl_tp_by_id and effective_sl_tp_by_id[id(candidate)] is not None else None,
            'effective_stop_loss_percent': effective_sl_tp_by_id[id(candidate)].stop_loss_percent if id(candidate) in effective_sl_tp_by_id and effective_sl_tp_by_id[id(candidate)] is not None else None,
            'sl_tp_mode': effective_sl_tp_by_id[id(candidate)].mode if id(candidate) in effective_sl_tp_by_id and effective_sl_tp_by_id[id(candidate)] is not None else None,
            'sl_tp_source': effective_sl_tp_by_id[id(candidate)].source if id(candidate) in effective_sl_tp_by_id and effective_sl_tp_by_id[id(candidate)] is not None else None,
            'tp_feasibility_penalty': candidate.tp_feasibility_penalty,
            'tp_feasibility_score_cap': candidate.tp_feasibility_score_cap,
            'tp_feasibility_hard_rejection_reason': candidate.tp_feasibility_hard_rejection_reason,
            'score_before_tp_feasibility': feasibility_by_id[id(candidate)].score_before_tp_feasibility if id(candidate) in feasibility_by_id and feasibility_by_id[id(candidate)] is not None else None,
            'score_after_tp_penalty': feasibility_by_id[id(candidate)].score_after_tp_penalty if id(candidate) in feasibility_by_id and feasibility_by_id[id(candidate)] is not None else None,
            'tp_feasibility_runway_score': feasibility_by_id[id(candidate)].runway_score if id(candidate) in feasibility_by_id and feasibility_by_id[id(candidate)] is not None else None,
            'reason': candidate.rank_reason,
        }
        for candidate in ranked_candidates
    ])
    for candidate in ranked_candidates:
        try:
            equity = execution_broker.get_account_equity()
            instrument_profile = risk_manager.instrument_profile_for(candidate.symbol)
            risk_profile = risk_manager.risk_profile_for(candidate.symbol)
            effective_sl_tp = effective_sl_tp_by_id.get(id(candidate)) or _resolve_runtime_effective_sl_tp(candidate=candidate, risk_profile=risk_profile, resolver=sl_tp_resolver)
            plan = _evaluate_risk_manager(risk_manager=risk_manager, candidate=candidate, equity=equity, effective_sl_tp=effective_sl_tp)
            candidate_economics = economics_by_id.get(id(candidate))
            trade_journal.write('decision', {'symbol': candidate.symbol, 'snapshot': candidate.snapshot, 'candle': candidate.candle, 'signal': candidate.signal, 'candidate': candidate, 'candidate_economics': candidate_economics, 'effective_sl_tp': effective_sl_tp, 'equity': equity, 'trade_plan': plan, 'instrument_profile': instrument_profile, 'risk_profile': risk_profile})
            execution_result = executor.execute(plan)
            if not execution_result:
                continue
            planned_entry_price = candidate.snapshot.last
            executed_entry_price = execution_result.executed_entry_price
            effective_entry_price = executed_entry_price if executed_entry_price is not None else planned_entry_price
            entry_price_source = 'broker_execution' if executed_entry_price is not None else 'snapshot_fallback'
            adjusted_plan = risk_manager.adjust_trade_plan_to_entry_price(trade_plan=plan, entry_price=effective_entry_price)
            tracked_position = position_tracker.record_open_position(position_id=execution_result.position_id, trade_plan=adjusted_plan, entry_price=effective_entry_price)
            risk_manager.record_open_position(candidate.symbol, session_key=candidate.session_key)
            if position_store is not None:
                try:
                    position_store.save_open_position(tracked_position)
                except Exception as exc:
                    logger.exception('Position persistence save error | position_id=%s | symbol=%s | error=%s', tracked_position.position_id, tracked_position.symbol, exc)
                    trade_journal.write('position_persistence_error', {'symbol': tracked_position.symbol, 'position_id': tracked_position.position_id, 'position': tracked_position, 'message': str(exc)})
            trade_journal.write('position_opened', {'symbol': candidate.symbol, 'position_id': execution_result.position_id, 'position': tracked_position, 'candidate': candidate, 'candidate_economics': candidate_economics, 'effective_sl_tp': effective_sl_tp, 'trade_plan': adjusted_plan, 'original_trade_plan': plan, 'adjusted_trade_plan': adjusted_plan, 'planned_entry_price': planned_entry_price, 'executed_entry_price': executed_entry_price, 'effective_entry_price': effective_entry_price, 'entry_price_source': entry_price_source, 'execution_slippage_percent': _slippage_percent(planned_entry_price=planned_entry_price, effective_entry_price=effective_entry_price), 'instrument_profile': instrument_profile, 'risk_profile': risk_profile})
        except Exception as exc:
            if is_broker_authorization_error is not None and is_broker_authorization_error(exc):
                raise
            logger.exception('Candidate execution error | symbol=%s | action=%s | score=%s | error=%s', candidate.symbol, candidate.signal.action, candidate.score, exc)
            trade_journal.write('candidate_execution_error', {'symbol': candidate.symbol, 'candidate': candidate, 'message': str(exc)})
            continue
