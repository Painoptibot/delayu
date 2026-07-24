# Task 13 Report

- Added invest subsystem menu entries for hub, projects, sites, handoffs, imports, and dashboard.
- Added invest labels in the subsystem switcher and redirect mapping to `invest-hub`.
- Registered invest domain models in Django admin.
- Added regression coverage for switching into an invest membership.
- Verified: `python -m pytest delayu/tests/test_invest_template.py delayu/tests/test_invest_views.py; python manage.py check` with `POSTGRES_USER=delau POSTGRES_PASSWORD=delau POSTGRES_DB=newsystem`.
