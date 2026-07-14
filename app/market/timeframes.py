from enum import IntEnum, StrEnum


class Timeframe(IntEnum):
    M1 = 60
    M5 = 300
    M15 = 900
    M30 = 1800
    H1 = 3600


BASE_TIMEFRAME = Timeframe.M1
SUPPORTED_TIMEFRAMES = tuple(Timeframe)
AGGREGATED_TIMEFRAMES = tuple(
    timeframe for timeframe in SUPPORTED_TIMEFRAMES if timeframe != BASE_TIMEFRAME
)
MULTI_TIMEFRAME_MODEL_VERSION = 'multi_timeframe_features_v1'


class BarCompleteness(StrEnum):
    COMPLETE = 'complete'
    INCOMPLETE = 'incomplete'
    PARTIAL = 'partial'


class SamplingQuality(StrEnum):
    DENSE = 'dense'
    ACCEPTABLE = 'acceptable'
    SPARSE = 'sparse'


class TimeframeDirection(StrEnum):
    UP = 'up'
    DOWN = 'down'
    MIXED = 'mixed'
    UNKNOWN = 'unknown'


class MultiTimeframeAlignment(StrEnum):
    ALIGNED = 'aligned'
    MIXED = 'mixed'
    OPPOSED = 'opposed'
    UNKNOWN = 'unknown'


class OpeningRangeStatus(StrEnum):
    WARMING_UP = 'warming_up'
    READY = 'ready'
    INCOMPLETE = 'incomplete'
    NOT_APPLICABLE = 'not_applicable'
