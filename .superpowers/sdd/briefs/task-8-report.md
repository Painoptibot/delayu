Status: complete
Files: delayu/forms_invest.py, delayu/views_invest.py, delayu/urls.py, templates/invest/*.html, delayu/tests/test_invest_views.py
Implemented InvestSubsystemMixin for active invest memberships and M22-gated hub/project screens.
Project list/detail/edit querysets use projects_for_membership.
Project create/edit form excludes funnel and displays the current/default funnel read-only.
Tests added for authenticated GET 200s, no funnel input, and viewer POST create 403.
Verification: python -m pytest delayu/tests/test_invest_views.py -q --tb=short
Verification: python -m pytest delayu/tests -k invest -q --tb=short
Concerns: test output has existing warnings for missing staticfiles directory and Django 6 URLField scheme change.

Follow-up: fixed Important finding by adding funnel-specific InvestProjectForm stage transitions, select-only allowed stages, and clean_stage validation.
Tests: added create-stage choice coverage and invalid transition rejection for lead -> site_pick.
Verification: python -m pytest delayu/tests/test_invest_views.py -q --tb=short
Verification: python -m pytest delayu/tests -k invest -q --tb=short
Concerns: same existing warnings for missing staticfiles directory and Django 6 URLField scheme change.
