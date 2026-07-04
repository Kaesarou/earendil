def extract_account_equity(payload: dict) -> float:
    equity = extract_optional_account_equity(payload)

    if equity is None:
        raise ValueError(f'Unable to extract account equity from eToro portfolio: {payload}')

    if equity <= 0:
        raise ValueError(f'Invalid eToro account equity={equity}. Portfolio={payload}')

    return equity


def extract_optional_account_equity(payload: dict) -> float | None:
    for key in (
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
    ):
        value = payload.get(key)
        if value is not None:
            return float(value)

    for key in (
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
    ):
        value = payload.get(key)

        if isinstance(value, dict):
            nested_equity = extract_optional_account_equity(value)
            if nested_equity is not None:
                return nested_equity

    return None
