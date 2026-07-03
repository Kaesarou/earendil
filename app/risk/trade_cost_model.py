from dataclasses import dataclass


@dataclass(frozen=True)
class TradeCostConfig:
    open_fee_percent: float = 0.0
    close_fee_percent: float = 0.0
    fixed_open_fee: float = 0.0
    fixed_close_fee: float = 0.0
    include_spread_cost: bool = True
    min_expected_net_profit: float = 0.0


@dataclass(frozen=True)
class TradeCostEstimate:
    position_value: float
    expected_gross_profit: float
    open_fee: float
    close_fee: float
    fixed_fees: float
    spread_cost: float
    total_estimated_cost: float
    total_estimated_cost_percent: float
    expected_net_profit: float
    min_expected_net_profit: float


class TradeCostModel:
    def estimate(
        self,
        *,
        position_value: float,
        expected_move_percent: float,
        spread_percent: float | None,
        config: TradeCostConfig,
    ) -> TradeCostEstimate:
        if position_value <= 0:
            return TradeCostEstimate(
                position_value=position_value,
                expected_gross_profit=0.0,
                open_fee=0.0,
                close_fee=0.0,
                fixed_fees=0.0,
                spread_cost=0.0,
                total_estimated_cost=0.0,
                total_estimated_cost_percent=0.0,
                expected_net_profit=0.0,
                min_expected_net_profit=config.min_expected_net_profit,
            )

        expected_gross_profit = position_value * (expected_move_percent / 100)

        open_fee = position_value * (config.open_fee_percent / 100)
        close_fee = position_value * (config.close_fee_percent / 100)
        fixed_fees = config.fixed_open_fee + config.fixed_close_fee
        spread_cost = 0.0
        if config.include_spread_cost and spread_percent is not None:
            spread_cost = position_value * (spread_percent / 100)

        total_estimated_cost = open_fee + close_fee + fixed_fees + spread_cost

        return self._build_estimate(
            position_value=position_value,
            expected_gross_profit=expected_gross_profit,
            open_fee=open_fee,
            close_fee=close_fee,
            fixed_fees=fixed_fees,
            spread_cost=spread_cost,
            total_estimated_cost=total_estimated_cost,
            min_expected_net_profit=config.min_expected_net_profit,
        )

    def _build_estimate(
        self,
        *,
        position_value: float,
        expected_gross_profit: float,
        open_fee: float,
        close_fee: float,
        fixed_fees: float,
        spread_cost: float,
        total_estimated_cost: float,
        min_expected_net_profit: float,
    ) -> TradeCostEstimate:
        return TradeCostEstimate(
            position_value=position_value,
            expected_gross_profit=expected_gross_profit,
            open_fee=open_fee,
            close_fee=close_fee,
            fixed_fees=fixed_fees,
            spread_cost=spread_cost,
            total_estimated_cost=total_estimated_cost,
            total_estimated_cost_percent=(total_estimated_cost / position_value) * 100,
            expected_net_profit=expected_gross_profit - total_estimated_cost,
            min_expected_net_profit=min_expected_net_profit,
        )
