Task 15 report

- Added `delayu/tests/test_invest_e2e.py`.
- Covered booking/package/handoff/roadmap, MO scope, booking conflict, and overdue dashboard scenarios.
- Ran with `POSTGRES_USER=delau POSTGRES_PASSWORD=delau POSTGRES_DB=newsystem`.
- Command: `pytest delayu/tests/test_invest_*.py -v` pattern plus `test_seed_invest_kk.py` via PowerShell expansion.
- Result: 61 passed, 23 warnings in 190.65s.
