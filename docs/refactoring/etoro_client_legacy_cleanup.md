# eToroClient legacy cleanup

## Goal

Reduce `EtoroClient` to a thin broker facade by removing legacy inline implementations that are already covered by pure helper modules and parity tests.

This cleanup is strictly technical refactoring. It must not change trading behaviour, strategy scoring, risk management, cooldown logic, candidate selection, or order semantics.

## Current status

The helper modules and focused tests are now largely in place. The eToro test suite has also been reorganized by concern for the main pure-helper areas:

- `tests/brokers/etoro/helpers/`
- `tests/brokers/etoro/helpers/http/`
- `tests/brokers/etoro/portfolio/`
- `tests/brokers/etoro/instrument/`
- `tests/brokers/etoro/market_data/`
- `tests/brokers/etoro/orders/`

A few old root-level test files could not be deleted through the GitHub connector safety filter. They are intentionally ignored from collection through `tests/brokers/etoro/conftest.py` once their moved replacement exists.

`EtoroClient` still contains inline legacy logic for several responsibilities that now have dedicated helper modules:

- scalar extraction
- side normalization and validation
- endpoint path construction
- HTTP URL and response payload conventions
- GET retry policy
- order response parsing
- portfolio position parsing
- instrument cache management
- instrument search parsing
- close order payload building
- broker environment resolution

The remaining major step is progressive delegation from `EtoroClient` to those modules, followed by removal of local legacy implementations when no longer used.

## Refactoring rules

1. Keep every patch small and reversible.
2. Keep all tests green after every patch.
3. Prefer one responsibility per commit.
4. Do not change public broker behaviour.
5. Do not change trading strategy or runtime flow.
6. Keep parity tests while migrating.
7. Remove parity tests only after the legacy methods have been deleted or reduced to trivial delegation.
8. Keep moved test files on unique basenames when the old root file cannot be deleted immediately.
9. Delete this temporary cleanup note when the refactor is complete.

## Delegation checklist

### 1. Scalar extractors

Replace local implementations with delegation to `app.brokers.etoro.scalar_extractors`:

- `_extract_float`
- `_extract_optional_float`
- `_extract_int`
- `_extract_optional_int`

Expected result: remove duplicated parsing logic from `EtoroClient`.

### 2. Trade side helpers

Replace local implementations with delegation to `app.brokers.etoro.trade_side`:

- `_normalize_side`
- `_ensure_side_is_allowed`

Expected result: single source of truth for supported eToro sides.

### 3. Endpoint paths

Replace local endpoint path methods with delegation to `app.brokers.etoro.endpoint_paths`:

- `_open_order_path`
- `_close_position_path`
- `_demo_order_details_path`
- `_real_order_lookup_path`
- `_demo_portfolio_path`
- `_real_portfolio_path`
- `_get_market_rates` path construction
- `_find_instrument_id` search path usage

Expected result: no hard-coded endpoint paths inside `EtoroClient` except through helpers.

### 4. Order response parser

Replace local order parsing and state helpers with delegation to `app.brokers.etoro.order_response_parser`:

- `_extract_order_id`
- `_extract_reference_id`
- `_extract_position_id_from_order_details`
- `_extract_order_error_code`
- `_extract_order_error_message`
- `_is_order_executed`
- `_is_order_rejected`
- `_is_close_response_accepted`

Expected result: remove duplicated order-state parsing from `EtoroClient`.

### 5. Portfolio position parser

Replace local portfolio parsing with delegation to `app.brokers.etoro.portfolio_position_parser`:

- `_extract_open_positions`
- `_contains_open_position`

Expected result: portfolio shape handling lives outside the client facade.

### 6. HTTP helpers

Replace inline HTTP conventions with helper modules:

- URL construction -> `http_url_builder.build_http_url`
- response payload parsing -> `http_response_payload.response_payload`
- retry policy -> `http_retry_policy.default_get_max_attempts` and `http_retry_policy.is_retryable_http_status`

Expected result: `_get` and `_post` keep transport orchestration only.

### 7. Instrument helpers

Replace inline cache/search details with:

- `instrument_cache.cached_instrument_id`
- `instrument_cache.remember_instrument_id`
- `instrument_search_parser.extract_items`
- `instrument_search_parser.resolve_exact_instrument_id`
- `instrument_search_parser.candidate_summaries`
- `instrument_search_parser.extract_instrument_id`

Expected result: `_find_instrument_id` becomes a short orchestration method.

### 8. Close order payload

Replace inline close payload construction with `close_order_payload_builder.build_close_order_payload`.

Expected result: no eToro payload schema duplicated inside `close_position`.

### 9. Broker environment

Replace inline environment extraction in `__init__` with `broker_environment.broker_environment_from_name`.

Expected result: broker name parsing has one source of truth.

## Test reorganization status

Done or mostly done:

- pure helper tests
- HTTP helper tests, except `test_http_headers_builder.py`, which the connector currently blocks when moved
- portfolio/account tests
- market-data tests
- instrument/cache tests
- order response parser tests

Known connector leftovers:

- `tests/brokers/etoro/test_portfolio_position_parser.py`
- `tests/brokers/etoro/test_instrument_search_parser.py`
- `tests/brokers/etoro/test_instrument_cache.py`

These files should be deleted manually or through a later connector-safe patch. Until then, `tests/brokers/etoro/conftest.py` prevents duplicated collection.

## Deletion criteria

A legacy method or block can be removed when:

- all call sites use the pure helper directly, or
- the method has become a one-line compatibility wrapper and no tests depend on its internal implementation, or
- the public broker API no longer needs the method.

## Definition of done

- `EtoroClient` is significantly smaller.
- `EtoroClient` mostly orchestrates broker calls instead of parsing payloads directly.
- No extracted helper has duplicated logic still living in `EtoroClient` except temporary compatibility wrappers.
- eToro tests are reorganized by concern and no longer mirror obsolete legacy methods unnecessarily.
- The temporary `docs/refactoring/etoro_client_legacy_cleanup.md` note is deleted.
- Full test suite is green.
