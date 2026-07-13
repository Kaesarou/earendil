from datetime import datetime, timezone

from app.config.settings import Settings
from app.execution.candidate_economics import CandidateEconomics, EvaluatedTradeCandidate
from app.execution.trade_candidate import TradeCandidate
from app.instruments.instrument_registry import InstrumentRegistry
from app.market.models import Candle, MarketSnapshot
from app.risk.position_sizing import FixedPercentPositionSizing
from app.risk.risk_manager import RiskManager
from app.runtime.candidate_flow import (
    select_evaluated_trade_candidates_with_strategy_profile,
    select_trade_candidates_with_strategy_profile,
)
from app.strategies.balanced_strategy_config import BalancedStrategyConfig
from app.strategies.signals import Signal


def make_candidate(symbol: str, score: float) -> TradeCandidate:
    now = datetime(2026, 7, 4, 18, 0, tzinfo=timezone.utc)
    snapshot = MarketSnapshot(
        symbol=symbol,
        bid=99.95,
        ask=100.05,
        last=100.0,
        timestamp=now,
    )
    candle = Candle(
        symbol=symbol,
        timeframe_seconds=60,
        open=99.5,
        high=100.2,
        low=99.4,
        close=100.0,
        volume=None,
        opened_at=now,
        closed_at=now,
    )
    signal = Signal(
        action='BUY',
        setup_quality=0.8,
        reason='test_signal',
        metadata={
            'session_move_percent': 1.0,
            'trend_strength_percent': 0.2,
            'breakout_percent': 0.1,
            'candle_range_percent': 0.8,
            'close_position_percent': 85.0,
        },
    )

    return TradeCandidate(
        symbol=symbol,
        snapshot=snapshot,
        candle=candle,
        signal=signal,
        score=score,
        rank_reason=f'test_score={score}',
    )


def make_evaluated_candidate(symbol: str, score: float) -> EvaluatedTradeCandidate:
    return EvaluatedTradeCandidate(
        candidate=make_candidate(symbol=symbol, score=score),
        economics=CandidateEconomics(
            position_value=100.0,
            expected_gross_profit=2.0,
            expected_net_profit=1.0,
            expected_net_profit_percent=0.5,
            estimated_total_cost=1.0,
            estimated_total_cost_percent=1.0,
            min_expected_net_profit_percent=0.1,
            required_min_expected_net_profit_amount=0.1,
        ),
    )


def build_risk_manager() -> RiskManager:
    settings = Settings(EQUITY_US_SYMBOLS='AAPL,MSFT,NVDA')
    return RiskManager(
        settings=settings,
        position_sizing_strategy=FixedPercentPositionSizing(),
        instrument_registry=InstrumentRegistry(settings),
    )


def build_strategy_profile() -> BalancedStrategyConfig:
    return BalancedStrategyConfig(
        candidate_selection_top_n=2,
        candidate_selection_min_score=0.0,
    )


def test_profile_candidate_selection_rejects_raw_overflow_with_top_n_reason():
    result = select_trade_candidates_with_strategy_profile(
        candidates=[
            make_candidate('NVDA', score=110.0),
            make_candidate('AAPL', score=130.0),
            make_candidate('MSFT', score=120.0),
        ],
        risk_manager=build_risk_manager(),
        strategy_profile=build_strategy_profile(),
    )

    assert [candidate.symbol for candidate in result.selected_candidates] == [
        'AAPL',
        'MSFT',
    ]
    assert len(result.rejected_candidates) == 1
    assert result.rejected_candidates[0].candidate.symbol == 'NVDA'
    assert result.rejected_candidates[0].reason == 'candidate_selection_outside_top_n'


def test_profile_candidate_selection_rejects_evaluated_overflow_with_top_n_reason():
    result = select_evaluated_trade_candidates_with_strategy_profile(
        evaluated_candidates=[
            make_evaluated_candidate('NVDA', score=110.0),
            make_evaluated_candidate('AAPL', score=130.0),
            make_evaluated_candidate('MSFT', score=120.0),
        ],
        risk_manager=build_risk_manager(),
        strategy_profile=build_strategy_profile(),
    )

    assert [
        evaluated_candidate.candidate.symbol
        for evaluated_candidate in result.selected_candidates
    ] == [
        'AAPL',
        'MSFT',
    ]
    assert len(result.rejected_candidates) == 1
    assert result.rejected_candidates[0].evaluated_candidate.candidate.symbol == 'NVDA'
    assert result.rejected_candidates[0].reason == 'candidate_selection_outside_top_n'
