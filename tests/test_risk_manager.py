from app.config.settings import Settings
from app.market.models import MarketSnapshot
from app.risk.position_sizing import FixedPercentPositionSizing
from app.risk.risk_manager import RiskManager
from app.strategies.signals import Signal


def build_risk_manager(
    max_open_positions: int = 2,
    max_open_positions_per_symbol: int = 1,
    max_trades_per_day: int = 10,
    estimated_round_trip_fees: float = 0.0,
    min_expected_net_profit: float = 0.0,
) -> RiskManager:
    settings = Settings(
        MAX_OPEN_POSITIONS=max_open_positions,
        MAX_OPEN_POSITIONS_PER_SYMBOL=max_open_positions_per_symbol,
        MAX_TRADES_PER_DAY=max_trades_per_day,
        MAX_POSITION_SIZE_PERCENT=40.0,
        STOP_LOSS_PERCENT=0.3,
        TAKE_PROFIT_PERCENT=0.5,
        ESTIMATED_ROUND_TRIP_FEES=estimated_round_trip_fees,
        MIN_EXPECTED_NET_PROFIT=min_expected_net_profit,
        FORCE_CLOSE_HOUR=23,
        FORCE_CLOSE_MINUTE=59,
    )

    return RiskManager(
        settings=settings,
        position_sizing_strategy=FixedPercentPositionSizing(),
    )


def snapshot(symbol: str = 'AAPL') -> MarketSnapshot:
    return MarketSnapshot.now(
        symbol=symbol,
        bid=99.0,
        ask=101.0,
        last=100.0,
    )


def buy_signal() -> Signal:
    return Signal(
        action='BUY',
        confidence=0.65,
        reason='test_buy',
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