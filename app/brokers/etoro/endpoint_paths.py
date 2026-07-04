def open_order_path(env: str) -> str:
    if env == 'demo':
        return '/api/v2/trading/execution/demo/orders'

    return '/api/v2/trading/execution/orders'


def close_position_path(env: str, position_id: str) -> str:
    if env == 'demo':
        return f'/api/v1/trading/execution/demo/market-close-orders/positions/{position_id}'

    return f'/api/v1/trading/execution/market-close-orders/positions/{position_id}'


def demo_order_details_path(order_id: str) -> str:
    return f'/api/v1/trading/info/demo/orders/{order_id}'


def real_order_lookup_path() -> str:
    return '/api/v2/trading/info/orders:lookup'


def demo_portfolio_path() -> str:
    return '/api/v1/trading/info/demo/portfolio'


def real_portfolio_path() -> str:
    return '/api/v1/trading/info/portfolio'


def instrument_search_path() -> str:
    return '/api/v1/market-data/search'


def instrument_rates_path(instrument_ids: list[int]) -> str:
    joined_instrument_ids = ','.join(
        str(instrument_id)
        for instrument_id in instrument_ids
    )

    return f'/api/v1/market-data/instruments/rates?instrumentIds={joined_instrument_ids}'
