from datetime import datetime, timezone

from app.execution.scoring.multi_timeframe_scorer import score_multi_timeframe
from app.market.multi_timeframe import (
    MultiTimeframeContext,
    OpeningRangeFeatures,
    TimeframeFeatures,
)
from app.market.timeframes import (
    MultiTimeframeAlignment,
    SamplingQuality,
    TimeframeDirection,
    TimeframeMaturity,
)


NOW = datetime(2026, 7, 15, 14, 0, tzinfo=timezone.utc)


def feature(
    timeframe: str,
    direction: TimeframeDirection,
    maturity: TimeframeMaturity,
) -> TimeframeFeatures:
    return TimeframeFeatures(
        timeframe=timeframe,
        maturity=maturity,
        as_of=NOW,
        latest_bar_closed_at=NOW,
        bar_count=20,
        covered_seconds=1200,
        direction=direction,
        sampling_quality=SamplingQuality.ACCEPTABLE,
        close=100.0,
        ema_fast=100.0,
        ema_slow=99.0,
        return_1_bar_percent=0.1,
        return_sample_percent=1.0,
        velocity_percent_per_bar=0.1,
    )


def context(features):
    maturities = {
        name: item.maturity for name, item in features.items()
    }
    return MultiTimeframeContext(
        model_version='multi_timeframe_features_v2',
        as_of=NOW,
        side='BUY',
        features_by_timeframe=features,
        maturity_by_timeframe=maturities,
        opening_ranges=OpeningRangeFeatures(None, {}),
        ready_aligned_timeframes=(),
        ready_opposed_timeframes=(),
        inclusive_aligned_timeframes=(),
        inclusive_opposed_timeframes=(),
        unavailable_timeframes=(),
        ready_alignment=MultiTimeframeAlignment.MIXED,
        alignment_including_provisional=MultiTimeframeAlignment.MIXED,
    )


def test_only_ready_m5_contributes_to_live_score():
    result = score_multi_timeframe(
        context=context(
            {
                'm5': feature(
                    'm5', TimeframeDirection.UP, TimeframeMaturity.READY
                ),
                'm15': feature(
                    'm15', TimeframeDirection.UP, TimeframeMaturity.READY
                ),
                'm30': feature(
                    'm30', TimeframeDirection.DOWN, TimeframeMaturity.READY
                ),
            }
        ),
        side='BUY',
    )

    assert result.components == {'m5': 3.0, 'm15': 0.0, 'm30': 0.0}
    assert result.score == 3.0


def test_provisional_and_h1_do_not_change_live_score():
    result = score_multi_timeframe(
        context=context(
            {
                'm5': feature(
                    'm5',
                    TimeframeDirection.DOWN,
                    TimeframeMaturity.PROVISIONAL,
                ),
                'h1': feature(
                    'h1', TimeframeDirection.UP, TimeframeMaturity.READY
                ),
            }
        ),
        side='BUY',
    )

    assert result.score == 0.0
    assert result.components == {'m5': 0.0, 'm15': 0.0, 'm30': 0.0}
    assert result.diagnostics['provisional_timeframes_ignored'] == ['m5']


def test_sell_direction_inverts_ready_timeframe_contributions():
    mtf_context = context(
        {
            'm5': feature(
                'm5', TimeframeDirection.DOWN, TimeframeMaturity.READY
            ),
            'm15': feature(
                'm15', TimeframeDirection.DOWN, TimeframeMaturity.READY
            ),
        }
    )
    buy = score_multi_timeframe(context=mtf_context, side='BUY')
    sell = score_multi_timeframe(context=mtf_context, side='SELL')

    assert buy.score == -3.0
    assert sell.score == 3.0


def test_missing_context_is_neutral():
    result = score_multi_timeframe(context=None, side='BUY')
    assert result.score == 0.0
