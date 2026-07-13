from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def write(path: str, content: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding='utf-8')


def replace_required(path: str, old: str, new: str) -> None:
    content = read(path)
    if old not in content:
        raise RuntimeError(f'Expected text not found in {path}: {old!r}')
    write(path, content.replace(old, new))


def delete(path: str) -> None:
    target = ROOT / path
    if not target.exists():
        raise RuntimeError(f'Expected file not found: {path}')
    target.unlink()


# 1. Make setup_quality the only setup-quality concept.
write(
    'app/strategies/signals.py',
    """from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Signal:
    action: str  # BUY, SELL, CLOSE, HOLD
    setup_quality: float  # Heuristic setup quality, never a win probability.
    reason: str
    metadata: dict[str, Any] | None = None

    @staticmethod
    def hold(reason: str = 'no_signal', metadata: dict[str, Any] | None = None) -> 'Signal':
        return Signal(
            action='HOLD',
            setup_quality=0.0,
            reason=reason,
            metadata=metadata,
        )
""",
)

for base in ('app', 'tests'):
    for path in (ROOT / base).rglob('*.py'):
        content = path.read_text(encoding='utf-8')
        updated = content.replace('confidence=', 'setup_quality=').replace('.confidence', '.setup_quality')
        if updated != content:
            path.write_text(updated, encoding='utf-8')

# 2. Remove the aggressive strategy and the profile-name compatibility factory.
delete('app/strategies/aggressive_strategy_config.py')
strategy_path = 'app/strategies/strategy.py'
strategy = read(strategy_path)
strategy = strategy.replace(
    'from app.strategies.aggressive_strategy_config import AggressiveStrategyConfig\n',
    '',
)
strategy = strategy.replace(
    'from app.strategies.balanced_strategy_config import BalancedStrategyConfig\n',
    '',
)
strategy = strategy.replace(
    'from app.strategies.models import StrategyProfileConfig\n',
    '',
)
strategy, count = re.subn(
    r'\n\ndef strategy_profile_from_name\(name: str\) -> StrategyProfileConfig:.*?\n\nclass TrendStrategy:',
    '\n\nclass TrendStrategy:',
    strategy,
    flags=re.DOTALL,
)
if count != 1:
    raise RuntimeError(f'Expected one strategy_profile_from_name block, found {count}')
write(strategy_path, strategy)

# 3. Keep one explicit Balanced profile in the runtime.
replace_required(
    'app/config/settings.py',
    "    strategy_aggressiveness: str = Field(default='balanced', alias='STRATEGY_AGGRESSIVENESS')\n",
    '',
)
replace_required(
    'app/main.py',
    'from app.strategies.strategy import StrategyProfileConfig, TrendStrategy, strategy_profile_from_name\n',
    'from app.strategies.balanced_strategy_config import BalancedStrategyConfig\n'
    'from app.strategies.models import StrategyProfileConfig\n'
    'from app.strategies.strategy import TrendStrategy\n',
)
replace_required(
    'app/main.py',
    'def build_strategy_profile(settings: Settings) -> StrategyProfileConfig:\n'
    '    return strategy_profile_from_name(settings.strategy_aggressiveness)\n',
    'def build_strategy_profile() -> StrategyProfileConfig:\n'
    '    return BalancedStrategyConfig()\n',
)
replace_required(
    'app/main.py',
    '    strategy_profile = build_strategy_profile(settings)\n',
    '    strategy_profile = build_strategy_profile()\n',
)
replace_required(
    'app/main.py',
    '    trade_journal = build_analysis_journal(settings, run_id=run_id)\n',
    '    trade_journal = build_analysis_journal(\n'
    '        settings,\n'
    '        run_id=run_id,\n'
    '        profile=strategy_profile.name,\n'
    '    )\n',
)

replace_required(
    'app/journal/analysis_journal.py',
    'def build_analysis_journal(settings: Settings, *, run_id: str | None = None) -> AnalysisJournal:\n',
    'def build_analysis_journal(\n'
    '    settings: Settings,\n'
    '    *,\n'
    '    run_id: str | None = None,\n'
    "    profile: str = 'balanced',\n"
    ') -> AnalysisJournal:\n',
)
replace_required(
    'app/journal/analysis_journal.py',
    '        profile=settings.strategy_aggressiveness,\n',
    '        profile=profile,\n',
)

# 4. Remove the generic override layer that existed only for the removed profile.
delete('app/instruments/config_overrides.py')
replace_required(
    'app/strategies/balanced_strategy_config.py',
    'from dataclasses import dataclass, field\n',
    'from dataclasses import dataclass, field, replace\n',
)
replace_required(
    'app/strategies/balanced_strategy_config.py',
    'from app.instruments.config_overrides import with_risk_overrides\n',
    '',
)
replace_required(
    'app/strategies/balanced_strategy_config.py',
    "BALANCED_CRYPTO_CONFIG = with_risk_overrides(\n"
    "    CRYPTO_CONFIG,\n"
    "    trade_cooldown=BALANCED_TRADE_COOLDOWN,\n"
    ")\n"
    "BALANCED_EQUITY_US_CONFIG = with_risk_overrides(\n"
    "    EQUITY_US_CONFIG,\n"
    "    dynamic_sl_tp_enabled=True,\n"
    "    trade_cooldown=BALANCED_TRADE_COOLDOWN,\n"
    ")\n"
    "BALANCED_EQUITY_EU_CONFIG = with_risk_overrides(\n"
    "    EQUITY_EU_CONFIG,\n"
    "    trade_cooldown=BALANCED_TRADE_COOLDOWN,\n"
    ")\n",
    "BALANCED_CRYPTO_CONFIG = replace(\n"
    "    CRYPTO_CONFIG,\n"
    "    risk=replace(\n"
    "        CRYPTO_CONFIG.risk,\n"
    "        trade_cooldown=BALANCED_TRADE_COOLDOWN,\n"
    "    ),\n"
    ")\n"
    "BALANCED_EQUITY_US_CONFIG = replace(\n"
    "    EQUITY_US_CONFIG,\n"
    "    risk=replace(\n"
    "        EQUITY_US_CONFIG.risk,\n"
    "        dynamic_sl_tp_enabled=True,\n"
    "        trade_cooldown=BALANCED_TRADE_COOLDOWN,\n"
    "    ),\n"
    ")\n"
    "BALANCED_EQUITY_EU_CONFIG = replace(\n"
    "    EQUITY_EU_CONFIG,\n"
    "    risk=replace(\n"
    "        EQUITY_EU_CONFIG.risk,\n"
    "        trade_cooldown=BALANCED_TRADE_COOLDOWN,\n"
    "    ),\n"
    ")\n",
)

write(
    'app/risk/profiles.py',
    """from app.instruments.models import AssetClass, RiskProfile
from app.strategies.balanced_strategy_config import BalancedStrategyConfig


DEFAULT_RISK_PROFILES: dict[AssetClass, RiskProfile] = (
    BalancedStrategyConfig().risk_profiles()
)
""",
)

# 5. Rewrite tests around the single active profile and the canonical field names.
write(
    'tests/strategies/test_signal_setup_quality.py',
    """from app.strategies.signals import Signal


def test_signal_exposes_setup_quality() -> None:
    signal = Signal(action='BUY', setup_quality=0.8, reason='trend_bullish_breakout')

    assert signal.setup_quality == 0.8


def test_hold_signal_has_no_setup_quality() -> None:
    signal = Signal.hold('no_signal')

    assert signal.setup_quality == 0.0
""",
)

strategy_test_path = 'tests/strategies/test_strategy.py'
strategy_test = read(strategy_test_path)
strategy_test = strategy_test.replace('import pytest\n\n', '')
strategy_test = strategy_test.replace('from app.instruments.models import AssetClass\n', '')
strategy_test = strategy_test.replace(
    'from app.strategies.aggressive_strategy_config import AggressiveStrategyConfig\n',
    '',
)
strategy_test = strategy_test.replace(
    'from app.strategies.balanced_strategy_config import BalancedStrategyConfig\n',
    '',
)
strategy_test = strategy_test.replace(
    'from app.strategies.strategy import TrendStrategy, strategy_profile_from_name\n',
    'from app.strategies.strategy import TrendStrategy\n',
)
marker = '\ndef test_strategy_profile_from_name_resolves_balanced_profile():'
if marker not in strategy_test:
    raise RuntimeError('Strategy profile compatibility tests marker not found')
strategy_test = strategy_test.split(marker, 1)[0].rstrip() + '\n'
write(strategy_test_path, strategy_test)

write(
    'tests/risk/test_risk_profiles.py',
    """from app.instruments.models import AssetClass
from app.risk.profiles import DEFAULT_RISK_PROFILES


def test_default_risk_profiles_use_balanced_trade_cooldown():
    cooldown = DEFAULT_RISK_PROFILES[AssetClass.EQUITY_US].trade_cooldown

    assert cooldown.after_take_profit_minutes == 30
    assert cooldown.after_stop_loss_minutes == 45
    assert cooldown.after_manual_close_minutes == 15
    assert cooldown.after_unknown_close_minutes == 15
""",
)

write(
    'tests/instrument/test_instrument_configs.py',
    """from app.instruments.base_configs import CRYPTO_CONFIG, EQUITY_US_CONFIG
from app.instruments.models import AssetClass
from app.risk.profiles import DEFAULT_RISK_PROFILES
from app.strategies.balanced_strategy_config import BalancedStrategyConfig


def test_balanced_strategy_uses_base_instrument_configs_with_profile_cooldown():
    profile = BalancedStrategyConfig()

    assert profile.crypto.trend == CRYPTO_CONFIG.trend
    assert profile.equity_us.trend == EQUITY_US_CONFIG.trend
    assert profile.crypto.risk.trade_cost == CRYPTO_CONFIG.risk.trade_cost
    assert profile.crypto.risk.trade_cooldown.after_take_profit_minutes == 30


def test_strategy_profile_exposes_instrument_configs_and_risk_profiles():
    profile = BalancedStrategyConfig()

    assert profile.instrument_config_for_asset_class(AssetClass.CRYPTO) == profile.crypto
    assert profile.trend_config_for_asset_class(AssetClass.CRYPTO) == profile.crypto.trend
    assert profile.risk_profile_for_asset_class(AssetClass.CRYPTO) == profile.crypto.risk
    assert profile.risk_profiles()[AssetClass.CRYPTO] == profile.crypto.risk


def test_default_risk_profiles_are_derived_from_balanced_strategy():
    assert DEFAULT_RISK_PROFILES[AssetClass.CRYPTO] == BalancedStrategyConfig().crypto.risk
""",
)

for path in (
    'tests/risk/test_risk_profile_trade_costs.py',
    'tests/instruments/test_stale_position_configs.py',
):
    content = read(path)
    content = content.replace(
        'from app.risk.profiles import risk_profiles_for_aggressiveness',
        'from app.risk.profiles import DEFAULT_RISK_PROFILES',
    )
    content = content.replace(
        "profiles = risk_profiles_for_aggressiveness('balanced')",
        'profiles = DEFAULT_RISK_PROFILES',
    )
    write(path, content)

profile_test_path = 'tests/strategies/test_strategy_profile_candidate_selection_top_n.py'
profile_test = read(profile_test_path)
profile_test = profile_test.replace(
    'from app.strategies.aggressive_strategy_config import AggressiveStrategyConfig\n',
    '',
)
profile_test, count = re.subn(
    r'\n\ndef test_aggressive_strategy_profile_uses_lower_candidate_selection_min_score\(\):.*?(?=\n\ndef test_strategy_profile_rejects_invalid_asset_class)',
    '',
    profile_test,
    flags=re.DOTALL,
)
if count != 1:
    raise RuntimeError(f'Expected one aggressive profile test, found {count}')
write(profile_test_path, profile_test)

# 6. Remove the historical runtime switch from documentation and configuration.
env = read('.env.example')
env = '\n'.join(
    line for line in env.splitlines() if 'STRATEGY_AGGRESSIVENESS' not in line and 'balanced | aggressive' not in line
) + '\n'
write('.env.example', env)

readme = read('README.md')
readme = '\n'.join(
    line
    for line in readme.splitlines()
    if 'STRATEGY_AGGRESSIVENESS' not in line and 'balanced` or `aggressive' not in line
) + '\n'
readme = readme.replace(
    'Goblin currently includes:\n',
    'Goblin currently includes:\n\n- one active, versioned `BalancedStrategyConfig`;\n',
)
write('README.md', readme)

# 7. Run CI for both the stable and integration branches.
replace_required(
    '.github/workflows/tests.yml',
    '      - main\n  pull_request:\n    branches:\n      - main\n',
    '      - main\n      - develop\n  pull_request:\n    branches:\n      - main\n      - develop\n',
)

# 8. Fail fast if any deleted compatibility concept remains in active code/tests/config docs.
for forbidden in (
    'AggressiveStrategyConfig',
    'strategy_profile_from_name',
    'risk_profiles_for_aggressiveness',
    'STRATEGY_AGGRESSIVENESS',
    'strategy_aggressiveness',
    'with_trend_overrides',
    'with_risk_overrides',
):
    matches: list[str] = []
    for base in ('app', 'tests'):
        for path in (ROOT / base).rglob('*.py'):
            if forbidden in path.read_text(encoding='utf-8'):
                matches.append(str(path.relative_to(ROOT)))
    for path in (ROOT / '.env.example', ROOT / 'README.md'):
        if forbidden in path.read_text(encoding='utf-8'):
            matches.append(str(path.relative_to(ROOT)))
    if matches:
        raise RuntimeError(f'Forbidden legacy concept {forbidden!r} remains in {matches}')

for path in (ROOT / 'app').rglob('*.py'):
    content = path.read_text(encoding='utf-8')
    if '.confidence' in content or 'confidence=' in content:
        raise RuntimeError(f'Legacy confidence field remains in {path.relative_to(ROOT)}')

print('PR1 structural cleanup applied successfully.')
