Task 9 complete.

Implemented sites list/detail/create UI for invest contour.
Added scoped InvestSiteForm and M22 views using sites_for_membership.
Added book/select POST routes backed by book_site/select_site.
InvestBookingError is surfaced via messages.error on the site detail page.
Added view coverage for sites pages and booking conflict page feedback.

Verification:
python -m pytest delayu/tests/test_invest_booking.py delayu/tests/test_invest_handoff.py delayu/tests/test_invest_import.py delayu/tests/test_invest_package.py delayu/tests/test_invest_roadmap.py delayu/tests/test_invest_scope.py delayu/tests/test_invest_template.py delayu/tests/test_invest_views.py
Result: 45 passed, 13 warnings.
