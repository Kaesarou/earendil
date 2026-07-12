from tests.risk.test_risk_manager import SESSION_A, build_risk_manager, record_open


def test_risk_manager_returns_session_key_when_position_closes():
    risk_manager = build_risk_manager()
    record_open(risk_manager, 'AAPL', SESSION_A)

    closed_session_key = risk_manager.record_close_position('AAPL')

    assert closed_session_key == SESSION_A


def test_restored_position_without_session_returns_none_on_close():
    risk_manager = build_risk_manager()
    risk_manager.restore_open_position('AAPL')

    closed_session_key = risk_manager.record_close_position('AAPL')

    assert closed_session_key is None
