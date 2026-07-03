from dataclasses import replace

from app.instruments.models import InstrumentConfig


def with_overrides(
    config: InstrumentConfig,
    *,
    trend: dict | None = None,
    risk: dict | None = None,
) -> InstrumentConfig:
    return replace(
        config,
        trend=replace(config.trend, **(trend or {})),
        risk=replace(config.risk, **(risk or {})),
    )


def with_trend_overrides(config: InstrumentConfig, **trend_overrides) -> InstrumentConfig:
    return with_overrides(config, trend=trend_overrides)


def with_risk_overrides(config: InstrumentConfig, **risk_overrides) -> InstrumentConfig:
    return with_overrides(config, risk=risk_overrides)
