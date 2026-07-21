from app.brokers.etoro.etoro_client import EtoroClient
from app.config.settings import Settings


def build_client() -> EtoroClient:
    return EtoroClient(
        settings=Settings(
            BROKER='etoro_demo',
            ETORO_API_KEY='test-api-key',
            ETORO_USER_KEY='test-user-key',
        )
    )


def test_etoro_client_get_account_equity_uses_portfolio_payload(monkeypatch):
    client = build_client()
    monkeypatch.setattr(
        client,
        'get_portfolio',
        lambda: {'clientPortfolio': {'balance': 43210.0}},
    )

    assert client.get_account_equity() == 43210.0
