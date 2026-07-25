# Invest dashboard skin (item 31)

## Goal
Modern visual language for invest executive surfaces without breaking Vuexy/Bootstrap layout.

## Scope
Pages: `/invest/cockpit/`, `/invest/dashboard/`, `/invest/kanban/`, `/invest/inbox/`.

## Approach
- Shared CSS: `src/assets/css/invest-dashboard-skin.css`
- Root wrapper: `.invest-dash`
- Markers: `.invest-dash__hero`, `.invest-dash__kpi`, `.invest-dash__panel`, `.invest-dash__kanban-col`, `.invest-dash__inbox-card`
- Load via `{% block page_css %}` + `{% static 'css/invest-dashboard-skin.css' %}`
- Direction: slate/teal atmosphere + amber accent; micro fade/slide; mobile-first
- Avoid: purple-indigo AI gradients, cream+terracotta serif, OSM/Leaflet leftovers

## Control / audit
1. Pytest asserts skin CSS linked + markers on all four pages.
2. CSS file asserts required tokens and bans purple-indigo hero gradient strings.
3. Audit note checklist signed after green tests.
