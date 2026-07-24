# Final P1 fix report

## Status

Fixed both P1 findings from `final-review.md`.

## Changes

- Handoff role gates are enforced in `delayu/services/invest_handoff.py` and `delayu/views_invest.py`.
  - `request_handoff`: only `invest_agency` and `invest_admin`.
  - `accept_handoff` / `return_handoff`: only `invest_dept` and `invest_admin`.
  - Service violations raise `InvestHandoffError`; HTTP violations return `403` and add `messages.error`.
- MO organization writes are isolated in `delayu/forms_invest.py` and `delayu/views_invest.py`.
  - `invest_mo` project/site forms hide `organization` and initialize it from `membership.organization`.
  - `clean_organization()` rejects a different organization for `invest_mo`.
  - Project/site create views force `organization = membership.organization` for `invest_mo`.

## Tests

- Added service tests for invalid handoff role usage.
- Added HTTP tests for agency accept denial, MO/dept request denial, and MO foreign organization create/update denial.
- Verification command passed:

```powershell
POSTGRES_USER=delau POSTGRES_PASSWORD=delau POSTGRES_DB=newsystem python -m pytest delayu/tests -k invest -q
```

Result: `70 passed`.
