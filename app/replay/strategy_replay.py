from collections import Counter, defaultdict
from datetime import datetime
from typing import Any

from app.config.settings import Settings
from app.execution.candidate_ranking import build_trade_candidate
from app.execution.trade_candidate import TradeCandidate
from app.instruments.instrument_registry import InstrumentRegistry
from app.journal.run_manifest import resolve_code_fingerprint, resolve_git_commit
from app.market.candle_builder import CandleBuilder
from app.market.models import MarketSnapshot
from app.replay.dataset import MarketReplayEvent, ReplayDataset
from app.risk.position_sizing import FixedPercentPositionSizing
from app.risk.risk_manager import RiskManager
from app.runtime.candidate_flow import select_trade_candidates_with_strategy_profile
from app.runtime.trading_session_window import trading_session_service_from_settings
from app.strategies.strategy import TrendStrategy, strategy_profile_from_name


class StrategyReplayRunner:
    def __init__(self, dataset: ReplayDataset):
        self.dataset = dataset
        settings_payload = dataset.manifest.get('runtime', {}).get('settings', {})
        self.settings = Settings(**settings_payload)
        self.symbols = list(dataset.manifest.get('runtime', {}).get('watchlist') or [])
        self.profile = strategy_profile_from_name(
            dataset.manifest.get('strategy', {}).get('profile')
            or self.settings.strategy_aggressiveness
        )
        self.instrument_registry = InstrumentRegistry(
            self.settings,
            instrument_configs=self.profile.instrument_configs,
        )
        self.session_service = trading_session_service_from_settings(self.settings)
        self.risk_manager = RiskManager(
            settings=self.settings,
            position_sizing_strategy=FixedPercentPositionSizing(),
            instrument_registry=self.instrument_registry,
        )

    def run(self) -> dict[str, Any]:
        events = self.dataset.market_events()
        strategies = {
            symbol: TrendStrategy(self.instrument_registry.config_for(symbol).trend)
            for symbol in self.symbols
        }
        candle_builders = {
            symbol: CandleBuilder(timeframe_seconds=self.settings.candle_timeframe_seconds)
            for symbol in self.symbols
        }
        active_session_keys: dict[str, str | None] = {}
        hold_reasons: Counter[str] = Counter()
        candidates: list[dict[str, Any]] = []
        candidates_by_loop: dict[int, list[TradeCandidate]] = defaultdict(list)
        snapshots_by_symbol: dict[str, list[MarketReplayEvent]] = defaultdict(list)
        loop_grouping_complete = True

        for event in events:
            snapshot = event.snapshot
            if snapshot.symbol not in strategies:
                continue
            snapshots_by_symbol[snapshot.symbol].append(event)
            asset_class = self.instrument_registry.resolve(snapshot.symbol).asset_class
            session_decision = self.session_service.evaluate(
                asset_class=asset_class,
                now=snapshot.timestamp,
            )
            previous_session_key = active_session_keys.get(snapshot.symbol)
            if session_decision.session_key != previous_session_key:
                strategies[snapshot.symbol] = TrendStrategy(
                    self.instrument_registry.config_for(snapshot.symbol).trend
                )
                candle_builders[snapshot.symbol] = CandleBuilder(
                    timeframe_seconds=self.settings.candle_timeframe_seconds
                )
                active_session_keys[snapshot.symbol] = session_decision.session_key

            strategy = strategies[snapshot.symbol]
            strategy.on_snapshot(snapshot)
            candle = candle_builders[snapshot.symbol].on_snapshot(snapshot)
            if candle is None:
                continue

            signal = strategy.on_candle(candle)
            if signal.action == 'HOLD':
                hold_reasons[signal.reason] += 1
                continue
            if not session_decision.new_entries_allowed or session_decision.session_key is None:
                hold_reasons[session_decision.reason] += 1
                continue

            candidate = build_trade_candidate(
                symbol=snapshot.symbol,
                snapshot=snapshot,
                candle=candle,
                signal=signal,
                session_key=session_decision.session_key,
            )
            key = _candidate_key(
                symbol=candidate.symbol,
                side=candidate.signal.action,
                closed_at=candidate.candle.closed_at,
            )
            loop_key = event.loop_id if event.loop_id is not None else event.sequence
            if event.loop_id is None:
                loop_grouping_complete = False
            candidates_by_loop[loop_key].append(candidate)
            candidates.append(
                {
                    'key': key,
                    'symbol': candidate.symbol,
                    'side': candidate.signal.action,
                    'score': candidate.score,
                    'reason': candidate.rank_reason,
                    'signal_reason': candidate.signal.reason,
                    'closed_at': candidate.candle.closed_at.isoformat(),
                    'market_sequence': event.sequence,
                    'loop_id': event.loop_id,
                    'session_key': candidate.session_key,
                    'entry_price': candidate.snapshot.last,
                    'pre_economics_selection': None,
                    'pre_economics_rejection_reason': None,
                }
            )

        selected_keys: set[str] = set()
        rejection_reason_by_key: dict[str, str] = {}
        for loop_candidates in candidates_by_loop.values():
            result = select_trade_candidates_with_strategy_profile(
                loop_candidates,
                self.risk_manager,
                self.profile,
            )
            selected_keys.update(
                _candidate_key(
                    symbol=candidate.symbol,
                    side=candidate.signal.action,
                    closed_at=candidate.candle.closed_at,
                )
                for candidate in result.selected_candidates
            )
            for rejection in result.rejected_candidates:
                rejection_key = _candidate_key(
                    symbol=rejection.candidate.symbol,
                    side=rejection.candidate.signal.action,
                    closed_at=rejection.candidate.candle.closed_at,
                )
                rejection_reason_by_key[rejection_key] = rejection.reason

        for candidate in candidates:
            candidate['pre_economics_selection'] = candidate['key'] in selected_keys
            candidate['pre_economics_rejection_reason'] = rejection_reason_by_key.get(
                candidate['key']
            )
            candidate['counterfactual_outcome'] = self._evaluate_static_outcome(
                candidate,
                snapshots_by_symbol[candidate['symbol']],
            )

        manifest_code = self.dataset.manifest.get('code', {})
        manifest_commit = manifest_code.get('git_commit')
        manifest_fingerprint = manifest_code.get('source_sha256')
        current_commit = resolve_git_commit()
        current_fingerprint = resolve_code_fingerprint()
        commit_matches = (
            manifest_commit is not None
            and current_commit is not None
            and manifest_commit == current_commit
        )
        fingerprint_matches = (
            manifest_fingerprint is not None
            and current_fingerprint is not None
            and manifest_fingerprint == current_fingerprint
        )
        return {
            'schema_version': 1,
            'run_id': self.dataset.run_id,
            'source': 'market.jsonl replay',
            'integrity': self.dataset.validate(),
            'reproducibility': {
                'manifest_git_commit': manifest_commit,
                'current_git_commit': current_commit,
                'git_commit_matches': commit_matches,
                'manifest_source_sha256': manifest_fingerprint,
                'current_source_sha256': current_fingerprint,
                'source_fingerprint_matches': fingerprint_matches,
                'exact_code_match': fingerprint_matches or commit_matches,
                'profile': self.profile.name,
                'candle_timeframe_seconds': self.settings.candle_timeframe_seconds,
                'loop_grouping_complete': loop_grouping_complete,
            },
            'decisions': {
                'hold_total': sum(hold_reasons.values()),
                'hold_reasons': dict(hold_reasons),
                'candidate_total': len(candidates),
                'pre_economics_selected_total': len(selected_keys),
            },
            'candidates': candidates,
            'outcome_assumptions': {
                'price_source': 'snapshot.last',
                'sl_tp_mode': 'static risk profile percentages',
                'fees_included': False,
                'position_overlap_enforced': False,
                'selection_stage': (
                    'score/min-score/top-n before economics, TP feasibility and cooldown'
                ),
                'purpose': (
                    'screening missed strategy opportunities, not broker PnL accounting'
                ),
            },
        }

    def _evaluate_static_outcome(
        self,
        candidate: dict[str, Any],
        events: list[MarketReplayEvent],
    ) -> dict[str, Any]:
        risk_profile = self.instrument_registry.risk_profile_for(candidate['symbol'])
        entry_price = float(candidate['entry_price'])
        side = candidate['side']
        if side == 'BUY':
            take_profit = entry_price * (1 + risk_profile.take_profit_percent / 100)
            stop_loss = entry_price * (1 - risk_profile.stop_loss_percent / 100)
        else:
            take_profit = entry_price * (1 - risk_profile.take_profit_percent / 100)
            stop_loss = entry_price * (1 + risk_profile.stop_loss_percent / 100)

        for event in events:
            if event.sequence <= candidate['market_sequence']:
                continue
            session_decision = self.session_service.evaluate(
                asset_class=self.instrument_registry.resolve(candidate['symbol']).asset_class,
                now=event.snapshot.timestamp,
            )
            if session_decision.session_key != candidate['session_key']:
                break
            price = event.snapshot.last
            if side == 'BUY':
                if price >= take_profit:
                    return _outcome('TP', event.snapshot, risk_profile.take_profit_percent)
                if price <= stop_loss:
                    return _outcome('SL', event.snapshot, -risk_profile.stop_loss_percent)
            else:
                if price <= take_profit:
                    return _outcome('TP', event.snapshot, risk_profile.take_profit_percent)
                if price >= stop_loss:
                    return _outcome('SL', event.snapshot, -risk_profile.stop_loss_percent)

        return {
            'status': 'UNRESOLVED',
            'closed_at': None,
            'gross_percent': None,
        }


def _candidate_key(*, symbol: str, side: str, closed_at: datetime) -> str:
    return f'{symbol}|{side}|{closed_at.isoformat()}'


def _outcome(
    status: str,
    snapshot: MarketSnapshot,
    gross_percent: float,
) -> dict[str, Any]:
    return {
        'status': status,
        'closed_at': snapshot.timestamp.isoformat(),
        'exit_price': snapshot.last,
        'gross_percent': round(gross_percent, 4),
    }
