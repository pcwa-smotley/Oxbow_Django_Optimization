# Agent Onboarding Guide

Welcome to the ABAY Reservoir Optimization project. This file orients future AI agents so every session starts with shared context, priorities, and conventions.

## 1. Know the Landscape First
- **Read the README** for a system-level refresher before coding. It summarizes how the Django web app, optimization engine, and alerting stack fit together, and which external services (PI System, Upstream API, YES Energy, Twilio) we depend on.
- **Two major code pillars**:
  - `abay_opt/`: core optimization, physics, data prep, and CLI helpers. The MILP solver and rafting constraints live in `optimizer.py`. Start there when touching optimization logic; however, changes to these files should be avoided if possible.
  - `django_backend/`: Django project containing REST APIs, Channels/WebSockets, Celery tasks, templates, and static assets.
- **Key documentation** (in order of usefulness):
  - `CLAUDE.md` — project structure, API endpoints, testing commands, architecture overview, doc index (start here)
  - `PRD.md` — product requirements, technical specs, phased delivery plan
  - `TASKS.md` — current backlog with status tracking

## 2. Current Focus Areas (February 2026)

1. **SMS/Voice Alert Deployment (Priority 0)** — The alerting backend is fully implemented in `optimization_api/alerting.py` with Twilio SMS, voice, email, and browser channels. `AlertingService` handles cooldowns, per-user preferences, and category-based thresholds. **Deployment is blocked on Twilio API approval.** Once approved, verify credentials, run `monitor_alerts --once --test-mode`, and deploy. Do not modify the alerting architecture — it is ready to go.

2. **Data Table Regression Testing (DT-5)** — DT-1 through DT-4 (ABAY forecast visibility, physics-parity setpoint editing, timestamp semantics, R20 editing) are complete. The remaining task is building regression tests to validate these before release.

3. **Phase A: Instrumentation & Provenance** — Next development phase. Persist per-hour forecast provenance, DA freshness indicators, and run tracking skeleton. See `TASKS.md` items A-1 through A-4.

## 3. Technology Stack

### Backend
- **Django 4.2+** with Django REST Framework
- **SQLite** with WAL mode (intentional for ~8 user base)
- **Celery + Redis** (optional) for background tasks
- **Channels** for WebSocket real-time alerts
- **Twilio** for SMS/voice alerts (pending API approval)
- **PuLP/CBC** for MILP optimization (solve time <2s for 168-hour horizon)

### Frontend
- **Apache ECharts 5** — all charts, gauges, and timeline (migrated from Chart.js in Feb 2026)
  - Custom themes registered: `oxbow-light` and `oxbow-dark` in `echart-theme.js`
  - Use `initEChart(domId)` to create themed instances, `destroyEChart(instance)` for disposal
  - Elevation + OXPH charts synced via `echarts.connect('dashboardSync')`
  - `setOption()` for all chart updates (not `.update()` — that was Chart.js)
- **Handsontable 14.3.0** — editable forecast data table
- **Vanilla JS** — no React/Vue/Angular framework; all logic in modular JS files under `static/js/`

### UI Theme
- Neon control room dark mode with glassmorphism
- Accent palette: cyan `#00d4ff`, magenta `#ff006e`, lime `#00ff88`, amber `#ffbe0b`
- Background: deep navy `#0a0e1a`
- Reuse `.btn`, `.icon-button`, `.tab-*`, and glassmorphism card styles from `dashboard.css`

## 4. Working with the Codebase

### Front-end updates
- Charts use **ECharts**, not Chart.js. All `<canvas>` elements have been replaced with `<div>` containers. When creating new charts, use `initEChart(domId)` from `echart-theme.js` and call `registerChartReinit(callback)` for theme-change re-rendering.
- Keep scripts modular. Dashboard charts depend on API responses; coordinate template changes with corresponding JS modules under `static/js/` (if you add or rename IDs/classes, update the JS).
- Maintain keyboard navigation and descriptive labels when adding buttons, tabs, or modal dialogs.
- The command palette (`command-palette.js`) registers keyboard shortcuts — update it if adding new navigable tabs or actions.
- When extending price or alert tabs, check the backing API views to ensure endpoints deliver the data shape the UI expects.

### Backend/API work
- Use existing serializers/models (`OptimizationRun`, `ParameterSet`, `OptimizationResult`, etc.) to persist optimization artifacts rather than inventing new stores.
- Follow the established pattern of dynamically appending the project root to `sys.path` for entry points that run outside Django's default context (see `alerting.py` and price views) to keep `abay_opt` imports reliable.
- When touching optimization logic, prefer adding configuration hooks through `ParameterSet`/`OptimizationParameters` so operators can tune values through the UI instead of hard-coding.

## 5. Alerting Platform Guidance
- Alert definitions, logs, and user notification preferences live in the Django models — extend these rather than duplicating state. Respect cooldowns and per-user channels provided by `AlertingService` when implementing new alert checks or delivery paths.
- Any UI enhancements to the "Alert Settings" tab should mirror the categories and metadata surfaced by the alert API responses for consistency.
- **Twilio credentials are not yet active** (pending API approval). The code wraps Twilio usage defensively so local development works without those secrets. Do not remove the defensive wrapping.
- Once Twilio is approved, the only steps are: add credentials to `settings.py` (or env vars), verify with test mode, and enable the `monitor_alerts` management command on a schedule.

## 6. Execution Checklist Each Session
1. Skim `README.md` and `CLAUDE.md` to refresh goals and constraints.
2. Check `TASKS.md` for current priorities and blocked items.
3. Confirm local entry points (custom scripts, Celery tasks, alerts) add the repo root to `sys.path` before importing `abay_opt` to avoid `ModuleNotFoundError` surprises.
4. Run relevant tests before handing work back. At minimum execute `python manage.py test` from `django_backend/`, and add targeted suites when modifying specific areas.
5. Ensure Django is running when testing front-end changes: `python manage.py runserver` (default port 8000).
6. Document UX or alert changes clearly in PR summaries so operators understand user-facing impacts.

## 7. Common Patterns Reference

| Pattern | Usage |
|---------|-------|
| `initEChart(domId)` | Create a themed ECharts instance |
| `destroyEChart(instance)` | Safe disposal (returns null) |
| `getBaseChartOption(labels, yAxisName, yMin)` | Shared chart config |
| `buildDayDividers(labels)` | MarkLine data for day boundaries |
| `registerChartReinit(callback)` | Re-render on theme change |
| `echarts.connect('dashboardSync')` | Sync crosshairs across charts |

## 8. Ideation Backlog
- **Forecast Intelligence**: Tiered MFRA strategy, decaying bias, confidence bands, forecast tracking dashboard — all specified in `PRD.md` Section 8, scheduled after Phase A/B.
- **UX Enhancements**: Inline validation in data grid, richer chart annotations (rafting windows, alert markers), saved layout presets per `UserProfile`.
- **Alerting Evolution**: Forecast deviation alerts, DA staleness alerts, spill risk alerts, WebSocket acknowledgment workflows, alert history filters in dashboard.
- **Data Persistence**: Finish Phase A/B from `TASKS.md` to unlock comparisons and historical scenario replay for operators.

Use this guide to stay consistent with prior work, communicate priorities, and keep the experience cohesive as the project evolves.
