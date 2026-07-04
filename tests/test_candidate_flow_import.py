def test_candidate_flow_runtime_module_imports():
    from app.runtime.candidate_flow import execute_ranked_candidates

    assert callable(execute_ranked_candidates)


def test_position_lifecycle_runtime_module_imports():
    from app.runtime.position_lifecycle import (
        reconcile_externally_closed_positions,
        register_trade_cooldown_for_closed_position,
        restore_persisted_positions,
    )

    assert callable(reconcile_externally_closed_positions)
    assert callable(register_trade_cooldown_for_closed_position)
    assert callable(restore_persisted_positions)


def test_main_imports_after_runtime_extractions():
    import app.main

    assert callable(app.main.process_symbol)
    assert callable(app.main.main)
