Task 10: Handoff + package UI

Implemented:
- Added handoff list plus request/accept/return POST views with InvestHandoffError surfaced via messages.error.
- Added package detail UI with checklist status update and file upload.
- Linked handoffs/package actions from invest hub and project detail.
- Added focused view tests for routes, handoff request/error gate, and package item upload.

Verification:
- RED: python -m pytest delayu/tests/test_invest_views.py -q --tb=short -> 5 missing-route failures.
- GREEN: python -m pytest delayu/tests/test_invest_views.py -q --tb=short -> 18 passed.
- Regression: python -m pytest delayu/tests -k invest -q --tb=short -> 50 passed.
