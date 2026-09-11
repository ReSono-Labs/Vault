from pathlib import Path


def test_browser_and_pytest_database_names_remain_separate() -> None:
    root = Path(__file__).resolve().parents[2]
    browser_harness = (root / "scripts" / "internet_test_env.py").read_text(encoding="utf-8")
    pytest_harness = (root / "scripts" / "test_env.py").read_text(encoding="utf-8")
    conftest = (root / "tests" / "conftest.py").read_text(encoding="utf-8")
    assert 'BROWSER_TEST_DATABASE = "resono_vault_browser_test"' in browser_harness
    assert '"VAULT_TEST_POSTGRES_DB": "resono_vault_test"' in pytest_harness
    assert 'database_name != "resono_vault_test"' in conftest
