def test_candidate_flow_runtime_module_imports():
    from app.runtime.candidate_flow import execute_ranked_candidates

    assert callable(execute_ranked_candidates)


def test_main_imports_after_candidate_flow_extraction():
    import app.main

    assert callable(app.main.process_symbol)
    assert callable(app.main.main)
