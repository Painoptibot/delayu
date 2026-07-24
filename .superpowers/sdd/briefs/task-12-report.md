Task 12: Dashboard

Implemented:
- Added `build_dashboard(subsystem)` service with all required dashboard keys.
- Added `InvestDashboardView`, `invest-dashboard` route, and `templates/invest/dashboard.html`.
- Covered overdue dashboard count and included the new route in invest view smoke tests.

Verification:
- Red: `python -m pytest delayu/tests/test_invest_roadmap.py -q` failed on missing `invest_dashboard`.
- Green: `python -m pytest delayu/tests/test_invest_roadmap.py delayu/tests/test_invest_views.py -q` passed, 26 tests.
