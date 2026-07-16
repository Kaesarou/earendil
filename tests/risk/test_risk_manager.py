from app.config.settings import Settings
from app.instruments.instrument_registry import InstrumentRegistry
from app.instruments.models import AssetClass, RiskProfile
from app.market.models import MarketSnapshot
from app.risk.position_sizing import FixedPercentPositionSizing
from app.risk.risk_manager import RiskManager
from app.risk.trade_cost_model import TradeCostConfig
from app.strategies.signals import Signal


SESSION_A = 'EQUITY_US:session-a'
SESSION_B = 'EQUITY_US:session-b'


def risk_profile(
    asset_class: AssetClass,
    *,
    profile_key: str = 'test_fixed_v1',
    max_position_size_percent: float = 40.0,
    stop_loss_percent: float = 0.3,
    take_profit_percent: float = 0.5,
    max_spread_percent: float = 0.0,
    min_move_spread_ratio: float = 0.0,
    trade_cost: TradeCostConfig | None = None,
) -> RiskProfile:
    return RiskProfile(
        asset_class=asset_class,
        profile_key=profile_key,
        max_position_size_percent=max_position_size_percent,
        stop_loss_percent=stop_loss_percent,
        take_profit_percent=take_profit_percent,
        force_close_enabled=False,
        force_close_hour=23,
        force_close_minute=59,
        max_spread_percent=max_spread_percent,
        min_move_spread_ratio=min_move_spread_ratio,
        trade_cost=trade_cost or TradeCostConfig(include_spread_cost=False),
    )


def build_risk_manager(
    max_open_positions: int = 2,
    max_open_positions_per_symbol: int = 1,
    max_trades_per_session: int = 10,
    trade_cost: TradeCostConfig | None = None,
    max_spread_percent: float = 0.0,
    min_move_spread_ratio: float = 0.0,
    crypto_symbols: str = '',
    crypto_max_position_size_percent: float = 0.75,
    crypto_stop_loss_percent: float = 1.5,
    crypto_take_profit_percent: float = 3.0,
    crypto_trade_cost: TradeCostConfig | None = None,
    crypto_max_spread_percent: float = 0.0,
    crypto_min_move_spread_ratio: float = 0.0,
) -> RiskManager:
    settings = Settings(
        MAX_OPEN_POSITIONS=max_open_positions,
        MAX_OPEN_POSITIONS_PER_SYMBOL=max_open_positions_per_symbol,
        MAX_TRADES_PER_SESSION=max_trades_per_session,
        EQUITY_US_SYMBOLS='AAPL,MSFT',
        CRYPTO_SYMBOLS=crypto_symbols,
    )
    risk_profiles = {
        AssetClass.EQUITY_US: risk_profile(
            AssetClass.EQUITY_US,
            profile_key='us_test_fixed_v1',
            trade_cost=trade_cost,
            max_spread_percent=max_spread_percent,
            min_move_spread_ratio=min_move_spread_ratio,
        ),
        AssetClass.CRYPTO: risk_profile(
            AssetClass.CRYPTO,
            profile_key='crypto_test_fixed_v1',
            max_position_size_percent=crypto_max_position_size_percent,
            stop_loss_percent=crypto_stop_loss_percent,
            take_profit_percent=crypto_take_profit_percent,
            trade_cost=crypto_trade_cost,
            max_spread_percent=crypto_max_spread_percent,
            min_move_spread_ratio=crypto_min_move_spread_ratio,
        ),
    }
    return RiskManager(
        settings=settings,
        position_sizing_strategy=FixedPercentPositionSizing(),
        instrument_registry=InstrumentRegistry(
            settings,
            risk_profiles=risk_profiles,
        ),
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
    metadata = (
        {'atr_percent': atr_percent}
        if atr_percent is not None
        else None
    )
    return Signal(
        action='BUY',
        setup_quality=0.65,
        reason='test_buy',
        metadata=metadata,
    )


def sell_signal() -> Signal:
    return Signal(
        action='SELL',
        setup_quality=0.65,
        reason='test_sell',
    )


def evaluate(
    risk_manager: RiskManager,
    *,
    signal: Signal,
    snapshot: MarketSnapshot,
    account_equity: float,
    session_key: str = SESSION_A,
):
    return risk_manager.evaluate(
        signal=signal,
        snapshot=snapshot,
        account_equity=account_equity,
        session_key=session_key,
    )


def record_open(
    risk_manager: RiskManager,
    symbol: str = 'AAPL',
    session_key: str = SESSION_A,
) -> None:
    risk_manager.record_open_position(symbol, session_key=session_key)


def test_risk_manager_approves_fixed_buy():
    plan = evaluate(
        build_risk_manager(),
        signal=buy_signal(atr_percent=3.0),
        snapshot=snapshot('AAPL'),
        account_equity=100.0,
    )
    assert plan.approved
    assert plan.symbol == 'AAPL'
    assert plan.amount == 40.0
    assert plan.stop_loss == 99.7
    assert plan.take_profit == 100.5
    assert plan.profile_key == 'us_test_fixed_v1'
    assert plan.sl_tp_mode == 'fixed'
    assert plan.expected_net_profit_percent == 0.5


def test_risk_manager_uses_crypto_fixed_profile():
    manager = build_risk_manager(
        crypto_symbols='DOGE',
        crypto_max_position_size_percent=1.0,
        crypto_stop_loss_percent=1.5,
        crypto_take_profit_percent=3.0,
        crypto_trade_cost=TradeCostConfig(
            fixed_open_fee=0.05,
            include_spread_cost=False,
        ),
    )
    plan = evaluate(
        manager,
        signal=buy_signal(),
        snapshot=snapshot('DOGE'),
        account_equity=1000.0,
    )
    assert plan.approved
    assert plan.amount == 10.0
    assert plan.stop_loss == 98.5
    assert plan.take_profit == 103.0
    assert plan.profile_key == 'crypto_test_fixed_v1'
    assert plan.expected_net_profit == 0.25


def test_risk_manager_rejects_spread_above_profile_limit():
    plan = evaluate(
        build_risk_manager(max_spread_percent=0.5),
        signal=buy_signal(),
        snapshot=snapshot('AAPL', bid=99.0, ask=101.0),
        account_equity=100.0,
    )
    assert not plan.approved
    assert plan.reason == 'spread_too_high'
    assert plan.spread_percent == 2.0


def test_low_move_to_spread_ratio_is_not_a_standalone_reject():
    plan = evaluate(
        build_risk_manager(
            max_spread_percent=5.0,
            min_move_spread_ratio=4.0,
        ),
        signal=buy_signal(),
        snapshot=snapshot('AAPL', bid=99.9, ask=100.1),
        account_equity=100.0,
    )
    assert plan.approved
    assert plan.min_required_move_percent == 0.8


def test_total_position_limit_rejects():
    manager = build_risk_manager(max_open_positions=1)
    record_open(manager, 'AAPL')
    plan = evaluate(
        manager,
        signal=buy_signal(),
        snapshot=snapshot('MSFT'),
        account_equity=100.0,
    )
    assert not plan.approved
    assert plan.reason == 'max_open_positions_reached'


def test_symbol_position_limit_rejects():
    manager = build_risk_manager(
        max_open_positions=2,
        max_open_positions_per_symbol=1,
    )
    record_open(manager, ' aapl ')
    plan = evaluate(
        manager,
        signal=buy_signal(),
        snapshot=snapshot('AAPL'),
        account_equity=100.0,
    )
    assert not plan.approved
    assert plan.reason == 'max_open_positions_per_symbol_reached'


def test_closing_position_releases_symbol_limit():
    manager = build_risk_manager()
    record_open(manager, 'AAPL')
    manager.record_close_position('AAPL')
    plan = evaluate(
        manager,
        signal=buy_signal(),
        snapshot=snapshot('AAPL'),
        account_equity=100.0,
    )
    assert plan.approved
    assert manager.open_positions == 0


def test_trade_quota_is_scoped_by_session_and_resettable():
    manager = build_risk_manager(max_trades_per_session=1)
    record_open(manager, 'AAPL', SESSION_A)
    manager.record_close_position('AAPL')
    rejected = evaluate(
        manager,
        signal=buy_signal(),
        snapshot=snapshot('MSFT'),
        account_equity=100.0,
        session_key=SESSION_A,
    )
    assert rejected.reason == 'max_trades_per_session_reached'
    allowed = evaluate(
        manager,
        signal=buy_signal(),
        snapshot=snapshot('MSFT'),
        account_equity=100.0,
        session_key=SESSION_B,
    )
    assert allowed.approved
    manager.reset_session_trades(SESSION_A)
    assert manager.trades_for_session(SESSION_A) == 0


def test_fees_must_leave_required_net_profit():
    manager = build_risk_manager(
        trade_cost=TradeCostConfig(
            fixed_open_fee=0.25,
            include_spread_cost=False,
        )
    )
    plan = evaluate(
        manager,
        signal=buy_signal(),
        snapshot=snapshot('AAPL'),
        account_equity=100.0,
    )
    assert not plan.approved
    assert plan.reason == 'expected_profit_too_low_after_fees'


def test_percentage_fees_are_included():
    manager = build_risk_manager(
        trade_cost=TradeCostConfig(
            open_fee_percent=0.05,
            close_fee_percent=0.05,
            include_spread_cost=False,
        )
    )
    plan = evaluate(
        manager,
        signal=buy_signal(),
        snapshot=snapshot('AAPL'),
        account_equity=100.0,
    )
    assert plan.approved
    assert plan.expected_net_profit_percent == 0.4


def test_sell_is_supported_by_fixed_profile():
    plan = evaluate(
        build_risk_manager(),
        signal=sell_signal(),
        snapshot=snapshot('AAPL'),
        account_equity=100.0,
    )
    assert plan.approved
    assert plan.side == 'SELL'
