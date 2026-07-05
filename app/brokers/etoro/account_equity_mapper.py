from app.brokers.etoro.scalar_extractors import extract_optional_float


ACCOUNT_EQUITY_KEYS = (
    'equity',
    'Equity',
    'accountEquity',
    'AccountEquity',
    'netLiquidationValue',
    'NetLiquidationValue',
    'netLiq',
    'NetLiq',
    'balance',
    'Balance',
    'cash',
    'Cash',
    'credit',
    'Credit',
    'availableBalance',
    'AvailableBalance',
    'availableCash',
    'AvailableCash',
)

NESTED_ACCOUNT_EQUITY_KEYS = (
    'clientPortfolio',
    'ClientPortfolio',
    'portfolio',
    'Portfolio',
    'account',
    'Account',
    'cashAvailable',
    'CashAvailable',
    'data',
    'Data',
)


def extract_account_equity(payload: dict) -> float:
    equity = extract_optional_account_equity(payload)

    if equity is None:
        raise ValueError(f'Unable to extract account equity from eToro portfolio: {payload}')

    if equity <= 0:
        raise ValueError(f'Invalid eToro account equity={equity}. Portfolio={payload}')

    return equity


def extract_optional_account_equity(payload: dict) -> float | None:
    direct_equity = extract_optional_float(payload, ACCOUNT_EQUITY_KEYS)
    if direct_equity is not None:
        return direct_equity

    for key in NESTED_ACCOUNT_EQUITY_KEYS:
        value = payload.get(key)

        if isinstance(value, dict):
            nested_equity = extract_optional_account_equity(value)
            if nested_equity is not None:
                return nested_equity

    return None
