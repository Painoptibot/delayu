"""Patch delayu-dashboard-analytics.js: Materio chart styles + DELAYU_DASHBOARD data."""
from pathlib import Path

p = Path(__file__).resolve().parents[1] / "src" / "assets" / "js" / "delayu-dashboard-analytics.js"
src = p.read_text(encoding="utf-8")

if "tailN(delayu" in src:
    print("already patched")
    raise SystemExit(0)

if "(function () {" not in src:
    raise SystemExit("unexpected file format")

src = src.replace(
    "(function () {\n  let cardColor,",
    "(function () {\n  const delayu = window.DELAYU_DASHBOARD || null;\n"
    "  const tailN = function (arr, n) {\n"
    "    if (!arr || !arr.length) return null;\n"
    "    return arr.slice(Math.max(0, arr.length - n));\n"
    "  };\n\n  let cardColor,",
    1,
)

src = src.replace(
    "data: [0, 20, 5, 30, 15, 45]",
    "data: tailN(delayu && delayu.cases_trend ? delayu.cases_trend.series : null, 6) || [0, 20, 5, 30, 15, 45]",
    1,
)
src = src.replace(
    "series: [64],\n      labels: ['Progress']",
    "series: [delayu && delayu.completion_pct != null ? delayu.completion_pct : 64],\n      labels: ['Progress']",
    1,
)
src = src.replace(
    "data: [17165, 13850, 12375, 9567, 7880]",
    "data: (delayu && delayu.status_chart && delayu.status_chart.series && delayu.status_chart.series.length)\n"
    "            ? delayu.status_chart.series\n"
    "            : [17165, 13850, 12375, 9567, 7880]",
    1,
)
src = src.replace(
    "data: [38, 55, 48, 65, 80, 38, 48]",
    "data: (delayu && delayu.tasks_priority && delayu.tasks_priority.series && delayu.tasks_priority.series.length)\n"
    "            ? delayu.tasks_priority.series\n"
    "            : [38, 55, 48, 65, 80, 38, 48]",
    1,
)

# Подписи оси для дел по статусам
src = src.replace(
    "categories: ['US', 'IN', 'JA', 'CA', 'AU']",
    "categories: (delayu && delayu.status_chart && delayu.status_chart.labels && delayu.status_chart.labels.length)\n"
    "          ? delayu.status_chart.labels\n"
    "          : ['US', 'IN', 'JA', 'CA', 'AU']",
    1,
)

p.write_text(src, encoding="utf-8")
print("patched", p.stat().st_size)
