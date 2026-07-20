# Runtime startup settings regression

The position-only REST fallback migration renamed the runtime settings used by
Market Data V2:

- `ws_symbol_silence_seconds` became `ws_position_silence_seconds`;
- `rest_fallback_cooldown_seconds` became
  `position_fallback_interval_seconds`.

The environment-variable aliases remain backward compatible, but application
code must use the new Python attribute names. The run manifest now records
`position_silence_seconds` and `position_fallback_interval_seconds`.
