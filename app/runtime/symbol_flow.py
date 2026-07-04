import logging

from app.execution.candidate_ranking import build_trade_candidate
from app.execution.trade_candidate import TradeCandidate
from app.journal.jsonl_journal import JsonlJournal
from app.market.models import Candle, MarketSnapshot
from app.risk.models import TradePlan
from app.risk.risk_manager import RiskManager
from app.strategies.strategy import TrendStrategy

logger = logging.getLogger(__name__)


def process_closed_candle(
    *,
    symbol: str,
    snapshot: MarketSnapshot,
    closed_candle: Candle,
    strategy: TrendStrategy,
    risk_manager: RiskManager,
    trade_journal: JsonlJournal,
    candle_journal: JsonlJournal,
) -> TradeCandidate | None:
    candle_journal.write('candle_closed', {'symbol': symbol, 'candle': closed_candle})

    logger.info(
        'Candle closed | symbol=%s | open=%s | high=%s | low=%s | close=%s | opened_at=%s | closed_at=%s',
        closed_candle.symbol,
        closed_candle.open,
        closed_candle.high,
        closed_candle.low,
        closed_candle.close,
        closed_candle.opened_at.isoformat(),
        closed_candle.closed_at.isoformat(),
    )

    signal = strategy.on_candle(closed_candle)
    logger.info(
        'Strategy signal | symbol=%s | action=%s | confidence=%s | reason=%s | candle_close=%s',
        symbol,
        signal.action,
        signal.confidence,
        signal.reason,
        closed_candle.close,
    )

    if signal.action == 'HOLD':
        plan = TradePlan(
            approved=False,
            reason=signal.reason,
            symbol=symbol,
            side=signal.action,
        )
        trade_journal.write(
            'decision',
            {
                'symbol': symbol,
                'snapshot': snapshot,
                'candle': closed_candle,
                'signal': signal,
                'equity': None,
                'trade_plan': plan,
                'instrument_profile': risk_manager.instrument_profile_for(symbol),
                'risk_profile': risk_manager.risk_profile_for(symbol),
            },
        )
        logger.info('Trade rejected: %s', plan.reason)
        return None

    candidate = build_trade_candidate(
        symbol=symbol,
        snapshot=snapshot,
        candle=closed_candle,
        signal=signal,
    )

    trade_journal.write(
        'candidate_detected',
        {
            'symbol': symbol,
            'snapshot': snapshot,
            'candle': closed_candle,
            'signal': signal,
            'candidate': candidate,
            'instrument_profile': risk_manager.instrument_profile_for(symbol),
            'risk_profile': risk_manager.risk_profile_for(symbol),
        },
    )

    logger.info(
        'Trade candidate detected | symbol=%s | action=%s | score=%s | reason=%s',
        symbol,
        signal.action,
        candidate.score,
        candidate.rank_reason,
    )

    return candidate
