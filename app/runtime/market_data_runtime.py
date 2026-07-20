import logging
import time
from datetime import datetime, timezone

from app.execution.candidate_economics import CandidateEconomicsEstimator
from app.execution.position_tracker import PositionTracker
from app.execution.trade_executor import TradeExecutor
from app.instruments.instrument_registry import InstrumentRegistry
from app.journal.jsonl_journal import JsonlJournal
from app.market.data_quality import MarketDataValidator
from app.market.market_context import MarketContextService
from app.market.session_timeframe_service import FullSessionMultiTimeframeService
from app.market_data.candle_stream import QualityAwareCandleBuilder
from app.market_data.contracts import LiveMarketDataFeed, RestMarketDataClient
from app.market_data.coordinator import MarketDataCoordinator
from app.persistence.position_store import PositionStore
from app.persistence.trade_cooldown_store import TradeCooldownStore
from app.risk.risk_manager import RiskManager
from app.risk.trade_cooldown_guard import TradeCooldownGuard
from app.runtime.decision_window import DecisionWindowCoordinator
from app.runtime.market_data_event_flow import MarketDataEventFlow
from app.runtime.market_data_maintenance import MarketDataMaintenance
from app.runtime.market_data_session_flow import MarketDataSessionFlow
from app.runtime.pending_entry import PendingEntryManager
from app.runtime.position_lifecycle import BrokerAuthorizationErrorChecker
from app.runtime.runtime_heartbeat import RuntimeHeartbeat
from app.runtime.trading_session_window import TradingSessionState
from app.strategies.balanced_strategy_config import BalancedStrategyConfig
from app.strategies.strategy import TrendStrategy


logger = logging.getLogger(__name__)


class EventDrivenMarketRuntime(
    MarketDataSessionFlow,
    MarketDataEventFlow,
    MarketDataMaintenance,
):
    def __init__(
        self,
        *,
        settings,
        symbols: list[str],
        run_id: str,
        strategy_profile: BalancedStrategyConfig,
        instrument_registry: InstrumentRegistry,
        execution_broker,
        rest_market_data: RestMarketDataClient,
        live_market_data: LiveMarketDataFeed,
        strategies: dict[str, TrendStrategy],
        candle_builders: dict[str, QualityAwareCandleBuilder],
        trading_session_service,
        trading_session_state: TradingSessionState,
        risk_manager: RiskManager,
        candidate_economics_estimator: CandidateEconomicsEstimator,
        executor: TradeExecutor,
        position_tracker: PositionTracker,
        position_store: PositionStore,
        cooldown_store: TradeCooldownStore,
        cooldown_guard: TradeCooldownGuard,
        pending_entry_manager: PendingEntryManager,
        market_data_validator: MarketDataValidator,
        market_context_service: MarketContextService,
        multi_timeframe_service: FullSessionMultiTimeframeService,
        trade_journal: JsonlJournal,
        market_journal: JsonlJournal,
        candle_journal: JsonlJournal,
        heartbeat: RuntimeHeartbeat,
        is_broker_authorization_error: BrokerAuthorizationErrorChecker,
    ) -> None:
        self.settings = settings
        self.symbols = symbols
        self.run_id = run_id
        self.strategy_profile = strategy_profile
        self.instrument_registry = instrument_registry
        self.execution_broker = execution_broker
        self.rest_market_data = rest_market_data
        self.live_market_data = live_market_data
        self.strategies = strategies
        self.candle_builders = candle_builders
        self.trading_session_service = trading_session_service
        self.trading_session_state = trading_session_state
        self.risk_manager = risk_manager
        self.candidate_economics_estimator = candidate_economics_estimator
        self.executor = executor
        self.position_tracker = position_tracker
        self.position_store = position_store
        self.cooldown_store = cooldown_store
        self.cooldown_guard = cooldown_guard
        self.pending_entry_manager = pending_entry_manager
        self.market_data_validator = market_data_validator
        self.market_context_service = market_context_service
        self.multi_timeframe_service = multi_timeframe_service
        self.trade_journal = trade_journal
        self.market_journal = market_journal
        self.candle_journal = candle_journal
        self.heartbeat = heartbeat
        self.is_broker_authorization_error = is_broker_authorization_error
        self.coordinator = MarketDataCoordinator(
            websocket_required=live_market_data.requires_websocket_health,
            symbol_silence_seconds=settings.ws_symbol_silence_seconds,
            fallback_cooldown_seconds=settings.rest_fallback_cooldown_seconds,
        )
        self.decision_windows = DecisionWindowCoordinator(
            grace_seconds=settings.decision_window_grace_seconds
        )
        self.latest_snapshots = {}
        self.session_decisions = {}
        self.active_symbols: list[str] = []
        self.context_asset_classes = {}
        self.loop_id = 0
        self._last_session_refresh = 0.0
        self._last_context_update = 0.0
        self._last_rest_control = 0.0
        self._last_position_reconciliation = 0.0

    def run(self) -> str:
        monitored_symbols = self._all_monitored_symbols()
        started_at = datetime.now(timezone.utc)
        self.coordinator.initialize_symbols(monitored_symbols, now=started_at)
        self.live_market_data.start(monitored_symbols)
        started_monotonic = time.monotonic()
        self._last_rest_control = started_monotonic
        self._last_position_reconciliation = started_monotonic
        self.trade_journal.write(
            'market_data_runtime_started',
            {
                'market_data_version': 'market_data_v2_ws_1',
                'primary_source': (
                    'websocket'
                    if self.live_market_data.requires_websocket_health
                    else 'polling'
                ),
                'monitored_symbols': monitored_symbols,
                'rest_control_interval_seconds': (
                    self.settings.rest_control_interval_seconds
                ),
                'symbol_silence_seconds': (
                    self.settings.ws_symbol_silence_seconds
                ),
            },
        )
        try:
            while True:
                self.loop_id += 1
                now = datetime.now(timezone.utc)
                monotonic_now = time.monotonic()
                self._refresh_sessions_if_due(now, monotonic_now)
                self._reconcile_positions_if_due(now, monotonic_now)
                event = self.live_market_data.next_event(timeout_seconds=0.25)
                now = datetime.now(timezone.utc)
                monotonic_now = time.monotonic()
                if event is not None:
                    self._handle_event(event, now)
                self._update_context_if_due(monotonic_now)
                self._run_fallback_if_needed(now)
                self._run_rest_control_if_due(now, monotonic_now)
                self._flush_decision_windows(now)
                self.heartbeat.maybe_emit(
                    journal=self.trade_journal,
                    logger=logger,
                    metrics=self.trade_journal.runtime_metrics(),
                    open_positions=len(
                        self.position_tracker.open_positions_snapshot()
                    ),
                    active_symbols=len(self.active_symbols),
                )
        except KeyboardInterrupt:
            self.trade_journal.write(
                'runtime_interrupted',
                {'run_id': self.run_id, 'loop_id': self.loop_id},
            )
            logger.info('Stopping Goblin!')
            return 'stopped'
        finally:
            self.live_market_data.stop()
            self.trade_journal.write(
                'market_data_runtime_stopped',
                {
                    'coordinator_metrics': self.coordinator.metrics,
                    'feed_diagnostics': self.live_market_data.diagnostics(),
                    'symbol_states': self.coordinator.snapshot(),
                    'loop_id': self.loop_id,
                },
            )
