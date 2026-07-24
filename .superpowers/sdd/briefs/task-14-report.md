Task 14 report: seed_invest_kk

- Added `delayu/management/commands/seed_invest_kk.py`.
- Seeds catalog, invest-kk subsystem, orgs, roles, users, modules M02/M03/M15/M22.
- Seeds 3 projects, 4 sites, booked link, requested handoff, packages, support roadmap.
- Added schema-aware role creation for live DB `is_subsystem_admin`.
- Added `delayu/tests/test_seed_invest_kk.py` smoke test.
- Verified: `python -m pytest delayu/tests/test_seed_invest_kk.py` passes.
- Verified: `python manage.py seed_invest_kk` passes with delau DB env.
- Verified: `python -m pytest delayu/tests -k invest` passes.
