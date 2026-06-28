from app.config.settings import Settings
from app.instruments.instrument_registry import InstrumentRegistry
from app.instruments.models import AssetClass, RiskProfile
from app.market.models import MarketSnapshot
from app.risk.position_sizing import FixedPercentPositionSizing
from app.risk.risk_manager import RiskManager
from app.strategies.signals import Signal


def risk_profile(
    asset_class: AssetClass,
    max_position_size_percent: float = 40.0,
    stop_loss_percent: float = 0.3,
    take_profit_percent: float = 0.5,
    estimated_round_trip_fees: float = 0.0,
    min_expected_net_profit: float = 0.0,
    max_spread_percent: float = 0.0,
    min_move_spread_ratio: float = 0.0,
    dynamic_sl_tp_enabled: bool = False,
    stop_loss_atr_multiplier: float = 1.5,
    take_profit_atr_multiplier: float = 2.5,
    min_stop_loss_percent: float = 0.0,
    max_stop_loss_percent: float = 0.0,
    min_take_profit_percent: float = 0.0,
    max_take_profit_percent: float = 0.0,
) -> RiskProfile:
    return RiskProfile(
        asset_class=asset_class,
        max_position_size_percent=max_position_size_percent,
        stop_loss_percent=stop_loss_percent,
        take_profit_percent=take_profit_percent,
        estimated_round_trip_fees=estimated_round_trip_fees,
        min_expected_net_profit=min_expected_net_profit,
        force_close_enabled=False,
        force_close_hour=23,
        force_close_minute=59,
        max_spread_percent=max_spread_percent,
        min_move_spread_ratio=min_move_spread_ratio,
        dynamic_sl_tp_enabled=dynamic_sl_tp_enabled,
        stop_loss_atr_multiplier=stop_loss_atr_multiplier,
        take_profit_atr_multiplier=take_profit_atr_multiplier,
        min_stop_loss_percent=min_stop_loss_percent,
        max_stop_loss_percent=max_stop_loss_percent,
        min_take_profit_percent=min_take_profit_percent,
        max_take_profit_percent=max_take_profit_percent,
    )


def build_risk_manager(
    max_open_positions: int = 2,
    max_open_positions_per_symbol: int = 1,
    max_trades_per_day: int = 10,
    estimated_round_trip_fees: float = 0.0,
    min_expected_net_profit: float = 0.0,
    max_spread_percent: float = 0.0,
    min_move_spread_ratio: float = 0.0,
    dynamic_sl_tp_enabled: bool = False,
    stop_loss_atr_multiplier: float = 1.5,
    take_profit_atr_multiplier: float = 2.5,
    min_stop_loss_percent: float = 0.0,
    max_stop_loss_percent: float = 0.0,
    min_take_profit_percent: float = 0.0,
    max_take_profit_percent: float = 0.0,
    short_selling_enabled: bool = False,
    crypto_symbols: str = '',
    crypto_max_position_size_percent: float = 0.75,
    crypto_stop_loss_percent: float = 1.5,
    crypto_take_profit_percent: float = 3.0,
    crypto_estimated_round_trip_fees: float = 3.0,
    crypto_min_expected_net_profit: float = 8.0,
    crypto_force_close_enabled: bool = False,
    crypto_max_spread_percent: float = 0.0,
    crypto_min_move_spread_ratio: float = 0.0,
) -> RiskManager:
    settings = Settings(
        MAX_OPEN_POSITIONS=max_open_positions,
        MAX_OPEN_POSITIONS_PER_SYMBOL=max_open_positions_per_symbol,
        MAX_TRADES_PER_DAY=max_trades_per_day,
        CRYPTO_SYMBOLS=crypto_symbols,
    )

    risk_profiles = {
        AssetClass.UNKNOWN: risk_profile(
            asset_class=AssetClass.UNKNOWN,
            estimated_round_trip_fees=estimated_round_trip_fees,
            min_expected_net_profit=min_expected_net_profit,
            max_spread_percent=max_spread_percent,
            min_move_spread_ratio=min_move_spread_ratio,
            dynamic_sl_tp_enabled=dynamic_sl_tp_enabled,
            stop_loss_atr_multiplier=stop_loss_atr_multiplier,
            take_profit_atr_multiplier=take_profit_atr_multiplier,
            min_stop_loss_percent=min_stop_loss_percent,
            max_stop_loss_percent=max_stop_loss_percent,
            min_take_profit_percent=min_take_profit_percent,
            max_take_profit_percent=max_take_profit_percent,
        ),
        AssetClass.CRYPTO: risk_profile(
            asset_class=AssetClass.CRYPTO,
            max_position_size_percent=crypto_max_position_size_percent,
            stop_loss_percent=crypto_stop_loss_percent,
            take_profit_percent=crypto_take_profit_percent,
            estimated_round_trip_fees=crypto_estimated_round_trip_fees,
            min_expected_net_profit=crypto_min_expected_net_profit,
            max_spread_percent=crypto_max_spread_percent,
            min_move_spread_ratio=crypto_min_move_spread_ratio,
        ),
    }

    return RiskManager(
        settings=settings,
        position_sizing_strategy=FixedPercentPositionSizing(),
        instrument_registry=InstrumentRegistry(settings, risk_profiles=risk_profiles),
    )


def snapshot(
    symbol: str = 'AAPL',
    bid: float = 99.0,
    ask: float = 101.0,
    last: float = 100.0,
) -> MarketSnapshot:
    return MarketSnapshot.now(
        symbol=symbol,
        bid=bid,
        ask=ask,
        last=last,
    )


def buy_signal(atr_percent: float | None = None) -> Signal:
    metadata = None
    if atr_percent is not None:
        metadata = {'atr_percent': atr_percent}

    return Signal(
        action='BUY',
        confidence=0.65,
        reason='test_buy',
        metadata=metadata,
    )


def sell_signal() -> Signal:
    return Signal(
        action='SELL',
        confidence=0.65,
        reason='test_sell',
    )


def test_risk_manager_approves_buy_when_no_position_is_open():
    risk_manager = build_risk_manager()

    plan = risk_manager.evaluate(
        signal=buy_signal(),
        snapshot=snapshot('AAPL'),
        account_equity=100.0,
    )

    assert plan.approved
    assert plan.symbol == 'AAPL'
    assert plan.amount == 40.0
    assert plan.stop_loss == 99.7
    assert plan.take_profit == 100.5
    assert plan.expected_gross_profit == 0.2
    assert plan.estimated_fees == 0.0
    assert plan.expected_net_profit == 0.2
    assert plan.dynamic_sl_tp_enabled is False


def test_risk_manager_uses_crypto_risk_profile_for_crypto_symbol():
    risk_manager = build_risk_manager(
        crypto_symbols='DOGE',
        crypto_max_position_size_percent=1.0,
        crypto_stop_loss_percent=1.5,
        crypto_take_profit_percent=3.0,
        crypto_estimated_round_trip_fees=0.05,
        crypto_min_expected_net_profit=0.0,
    )

    plan = risk_manager.evaluate(
        signal=buy_signal(),
        snapshot=snapshot('DOGE'),
        account_equity=1000.0,
    )

    assert plan.approved
    assert plan.symbol == 'DOGE'
    assert plan.amount == 10.0
    assert plan.stop_loss == 98.5
    assert plan.take_profit == 103.0
    assert plan.expected_gross_profit == 0.3
    assert plan.estimated_fees == 0.05
    assert plan.expected_net_profit == 0.25


def test_risk_manager_uses_atr_dynamic_stop_loss_and_take_profit():
    risk_manager = build_risk_manager(
        dynamic_sl_tp_enabled=True,
        stop_loss_atr_multiplier=1.5,
        take_profit_atr_multiplier=2.5,
        min_stop_loss_percent=0.5,
        max_stop_loss_percent=2.0,
        min_take_profit_percent=1.0,
        max_take_profit_percent=4.0,
    )

    plan = risk_manager.evaluate(
        signal=buy_signal(atr_percent=0.8),
        snapshot=snapshot('AAPL'),
        account_equity=100.0,
    )

    assert plan.approved
    assert plan.stop_loss == 98.8
    assert plan.take_profit == 102.0
    assert plan.expected_gross_profit == 0.8
    assert plan.expected_net_profit == 0.8
    assert plan.atr_percent == 0.8
    assert plan.dynamic_sl_tp_enabled is True
    assert plan.effective_stop_loss_percent == 1.2
    assert plan.effective_take_profit_percent == 2.0


def test_risk_manager_clamps_atr_dynamic_stop_loss_and_take_profit():
    risk_manager = build_risk_manager(
        dynamic_sl_tp_enabled=True,
        stop_loss_atr_multiplier=1.5,
        take_profit_atr_multiplier=2.5,
        min_stop_loss_percent=0.5,
        max_stop_loss_percent=2.0,
        min_take_profit_percent=1.0,
        max_take_profit_percent=4.0,
    )

    plan = risk_manager.evaluate(
        signal=buy_signal(atr_percent=3.0),
        snapshot=snapshot('AAPL'),
        account_equity=100.0,
    )

    assert plan.approved
    assert plan.stop_loss == 98.0
    assert plan.take_profit == 104.0
    assert plan.effective_stop_loss_percent == 2.0
    assert plan.effective_take_profit_percent == 4.0


def test_risk_manager_rejects_when_spread_is_too_high():
    risk_manager = build_risk_manager(
        max_spread_percent=0.5,
    )

    plan = risk_manager.evaluate(
        signal=buy_signal(),
        snapshot=snapshot('AAPL', bid=99.0, ask=101.0, last=100.0),
        account_equity=100.0,
    )

    assert not plan.approved
    assert plan.reason == 'spread_too_high'
    assert plan.spread_percent == 2.0
    assert plan.max_spread_percent == 0.5


def test_risk_manager_rejects_when_expected_move_is_too_low_vs_spread():
    risk_manager = build_risk_manager(
        max_spread_percent=5.0,
        min_move_spread_ratio=4.0,
    )

    plan = risk_manager.evaluate(
        signal=buy_signal(),
        snapshot=snapshot('AAPL', bid=99.9, ask=100.1, last=100.0),
        account_equity=100.0,
    )

    assert not plan.approved
    assert plan.reason == 'expected_move_too_low_vs_spread'
    assert plan.spread_percent == 0.2
    assert plan.expected_move_percent == 0.5
    assert plan.min_required_move_percent == 0.8
    assert plan.min_move_spread_ratio == 4.0


def test_risk_manager_rejects_when_total_open_positions_limit_is_reached():
    risk_manager = build_risk_manager(
        max_open_positions=1,
        max_open_positions_per_symbol=1,
    )
    risk_manager.record_open_position('AAPL')

    plan = risk_manager.evaluate(
        signal=buy_signal(),
        snapshot=snapshot('MSFT'),
        account_equity=100.0,
    )

    assert not plan.approved
    assert plan.reason == 'max_open_positions_reached'


def test_risk_manager_rejects_when_symbol_open_positions_limit_is_reached():
    risk_manager = build_risk_manager(
        max_open_positions=2,
        max_open_positions_per_symbol=1,
    )
    risk_manager.record_open_position('AAPL')

    plan = risk_manager.evaluate(
        signal=buy_signal(),
        snapshot=snapshot('AAPL'),
        account_equity=100.0,
    )

    assert not plan.approved
    assert plan.reason == 'max_open_positions_per_symbol_reached'


def test_risk_manager_allows_another_symbol_when_total_limit_is_not_reached():
    risk_manager = build_risk_manager(
        max_open_positions=2,
        max_open_positions_per_symbol=1,
    )
    risk_manager.record_open_position('AAPL')

    plan = risk_manager.evaluate(
        signal=buy_signal(),
        snapshot=snapshot('MSFT'),
        account_equity=100.0,
    )

    assert plan.approved
    assert plan.symbol == 'MSFT'


def test_risk_manager_decrements_symbol_count_when_position_is_closed():
    risk_manager = build_risk_manager(
        max_open_positions=2,
        max_open_positions_per_symbol=1,
    )
    risk_manager.record_open_position('AAPL')
    risk_manager.record_close_position('AAPL')

    plan = risk_manager.evaluate(
        signal=buy_signal(),
        snapshot=snapshot('AAPL'),
        account_equity=100.0,
    )

    assert plan.approved
    assert risk_manager.open_positions == 0
    assert risk_manager.open_positions_by_symbol == {}


def test_risk_manager_normalizes_symbol_when_tracking_positions():
    risk_manager = build_risk_manager(
        max_open_positions=2,
        max_open_positions_per_symbol=1,
    )
    risk_manager.record_open_position(' aapl ')

    plan = risk_manager.evaluate(
        signal=buy_signal(),
        snapshot=snapshot('AAPL'),
        account_equity=100.0,
    )

    assert not plan.approved
    assert plan.reason == 'max_open_positions_per_symbol_reached'


def test_risk_manager_rejects_when_max_trades_per_day_is_reached():
    risk_manager = build_risk_manager(
        max_open_positions=2,
        max_open_positions_per_symbol=2,
        max_trades_per_day=1,
    )
    risk_manager.record_open_position('AAPL')
    risk_manager.record_close_position('AAPL')

    plan = risk_manager.evaluate(
        signal=buy_signal(),
        snapshot=snapshot('MSFT'),
        account_equity=100.0,
    )

    assert not plan.approved
    assert plan.reason == 'max_trades_per_day_reached'


def test_risk_manager_rejects_when_expected_profit_does_not_cover_fees():
    risk_manager = build_risk_manager(
        estimated_round_trip_fees=0.25,
        min_expected_net_profit=0.0,
    )

    plan = risk_manager.evaluate(
        signal=buy_signal(),
        snapshot=snapshot('AAPL'),
        account_equity=100.0,
    )

    assert not plan.approved
    assert plan.reason == 'expected_profit_too_low_after_fees'
    assert plan.amount == 40.0
    assert plan.expected_gross_profit == 0.2
    assert plan.estimated_fees == 0.25
    assert plan.expected_net_profit == -0.05


def test_risk_manager_rejects_when_expected_net_profit_is_below_minimum():
    risk_manager = build_risk_manager(
        estimated_round_trip_fees=0.05,
        min_expected_net_profit=0.2,
    )

    plan = risk_manager.evaluate(
        signal=buy_signal(),
        snapshot=snapshot('AAPL'),
        account_equity=100.0,
    )

    assert not plan.approved
    assert plan.reason == 'expected_profit_too_low_after_fees'
    assert plan.expected_gross_profit == 0.2
    assert plan.estimated_fees == 0.05
    assert plan.expected_net_profit == 0.15


def test_risk_manager_approves_when_expected_net_profit_matches_minimum():
    risk_manager = build_risk_manager(
        estimated_round_trip_fees=0.05,
        min_expected_net_profit=0.15,
    )

    plan = risk_manager.evaluate(
        signal=buy_signal(),
        snapshot=snapshot('AAPL'),
        account_equity=100.0,
    )

    assert plan.approved
    assert plan.expected_gross_profit == 0.2
    assert plan.estimated_fees == 0.05
    assert plan.expected_net_profit == 0.15


def test_risk_manager_approves_sell_when_short_selling_is_enabled():
    risk_manager = build_risk_manager(short_selling_enabled=True)

    plan = risk_manager.evaluate(
        signal=sell_signal(),
        snapshot=snapshot('AAPL'),
        account_equity=100.0,
    )

    assert plan.approved
    assert plan.symbol == 'AAPL'
    assert plan.side == 'SELL'
    assert plan.amount == 40.0
    assert plan.stop_loss == 100.3
    assert plan.take_profit == 99.5
    assert plan.expected_gross_profit == 0.2
    assert plan.estimated_fees == 0.0
    assert plan.expected_net_profit == 0.2
