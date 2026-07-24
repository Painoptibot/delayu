# Task 6 Report: Import batch diff/apply

**Branch:** `feature/invest-kk`  
**Status:** DONE  
**Commit:** `feat: add invest MO CSV import with confirm apply`

## TDD

| Phase | Result |
|-------|--------|
| RED | `ImportError: InvestImportRow` missing |
| GREEN | **4 passed** import; **19 passed** all invest tests |

## Deliverables

| File | Change |
|------|--------|
| `delayu/models_invest.py` | `InvestImportBatch`, `InvestImportRow` |
| `delayu/services/invest_import.py` | `parse_mo_file`, `apply_row`, `skip_row` |
| `delayu/migrations/0073_invest_import.py` | CreateModel |
| `delayu/tests/test_invest_import.py` | Brief test + changed/skip/site |

## Behavior

- CSV columns: `code,name,stage` (+ optional `cadastral_number`, `investment_amount`).
- Actions: `new_project`, `changed_project`, `new_site`, `changed_site`, `gap`.
- Parse never writes DB records; `apply_row` / `skip_row` required per row.

## Checklist

- [x] Models + migration after 0072
- [x] No silent overwrite for `changed_*`
- [x] CSV YAGNI (no openpyxl)

## Follow-up (gap / changed_site tests)

| Test | Result |
|------|--------|
| `test_import_gap_apply_rejected` | **passed** — gap row raises; project unchanged |
| `test_import_changed_site_requires_apply` | **passed** — parse diff + apply updates site |
| All invest (`-k invest`) | **21 passed** |
