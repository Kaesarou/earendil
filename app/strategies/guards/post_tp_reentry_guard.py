from dataclasses import dataclass

CONSUMED_MOVE_AFTER_TP_REASON = 'consumed_move_after_take_profit'
POST_TP_RESET_CONFIRMED_REASON = 'post_tp_reset_confirmed'

@dataclass(frozen=True)
class PostTpReentryConfig:
    enabled: bool = True
    smart_watch_minutes: int = 60
