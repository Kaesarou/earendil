from datetime import datetime, timezone

from app.execution.scoring.market_context_scorer import score_market_context
from app.instruments.models import AssetClass
from app.market.market_context import (
    BenchmarkContext,
    BreadthContext,
    CandidateMarketContext,
    ContextAlignment,
    MarketDirection,
    MarketRegime,
    SectorContext,
)


NOW = datetime(2026, 7, 15, 14, 0, tzinfo=timezone.utc)


def context(
    *,
    asset_class=AssetClass.EQUITY_US,
    benchmark_return=-1.0,
    benchmark_momentum=-0.2,
    breadth_ratio=0.25,
    sector_ratio=0.30,
    relative_strength=0.0,
):
    return CandidateMarketContext(
        version='market_context_v2',
        as_of=NOW,
        asset_class=asset_class,
        regime=MarketRegime.RISK_OFF,
        alignment=ContextAlignment.OPPOSED,
        benchmark=BenchmarkContext(
            'SPX500', True, MarketDirection.BEARISH,
            benchmark_return, benchmark_momentum, 0.02, 0.0,
        ),
        breadth=BreadthContext(
            True, MarketDirection.BEARISH, 20, 20, 1.0,
            int(breadth_ratio * 20),
            int((1.0 - breadth_ratio) * 20),
            0, breadth_ratio, benchmark_return,
        ),
        sector=SectorContext(
            'TECHNOLOGY', True, MarketDirection.BEARISH,
            10, 10, sector_ratio, benchmark_return,
        ),
        symbol_session_return_percent=(
            benchmark_return + relative_strength
        ),
        symbol_relative_strength_percent=relative_strength,
        reasons=('test',),
    )


def test_strong_fresh_relative_strength_can_overcome_bearish_background():
    weak = score_market_context(
        context=context(relative_strength=0.2),
        side='BUY',
        entry_freshness_score=100.0,
    )
    strong = score_market_context(
        context=context(relative_strength=3.5),
        side='BUY',
        entry_freshness_score=100.0,
    )

    assert weak.score < 0
    assert strong.score > 0
    assert strong.components['relative_strength_raw'] > 10.0
    assert strong.components['relative_strength_adjustment'] < (
        strong.components['relative_strength_raw']
    )


def test_relative_strength_compensation_is_progressive_before_its_cap():
    results = [
        score_market_context(
            context=context(relative_strength=value),
            side='BUY',
            entry_freshness_score=100.0,
        )
        for value in (0.1, 0.3, 0.6)
    ]
    adjustments = [
        result.components['relative_strength_adjustment']
        for result in results
    ]
    assert adjustments[0] < adjustments[1] < adjustments[2]
    assert results[0].score < results[1].score < results[2].score


def test_consumed_move_limits_positive_relative_strength_compensation():
    fresh = score_market_context(
        context=context(relative_strength=3.5),
        side='BUY',
        entry_freshness_score=100.0,
    )
    consumed = score_market_context(
        context=context(relative_strength=3.5),
        side='BUY',
        entry_freshness_score=10.0,
    )
    preliminary = score_market_context(
        context=context(relative_strength=3.5),
        side='BUY',
    )

    assert fresh.score > consumed.score
    assert consumed.score < 0
    assert preliminary.components['relative_strength_adjustment'] == 0.0


def test_sell_direction_inverts_background_and_relative_strength():
    bullish_for_buy = context(
        benchmark_return=1.0,
        benchmark_momentum=0.2,
        breadth_ratio=0.75,
        sector_ratio=0.70,
        relative_strength=2.0,
    )
    buy = score_market_context(
        context=bullish_for_buy,
        side='BUY',
        entry_freshness_score=100.0,
    )
    sell = score_market_context(
        context=bullish_for_buy,
        side='SELL',
        entry_freshness_score=100.0,
    )

    assert buy.score > 0
    assert sell.score < 0
    assert buy.components['relative_strength_adjustment'] > 0
    assert sell.components['relative_strength_adjustment'] < 0


def test_context_score_is_bounded_and_missing_context_is_neutral():
    extreme = score_market_context(
        context=context(relative_strength=100.0),
        side='BUY',
        entry_freshness_score=100.0,
    )
    missing = score_market_context(context=None, side='BUY')

    assert -15.0 <= extreme.score <= 15.0
    assert missing.score == 0.0
    assert all(value == 0.0 for value in missing.components.values())
