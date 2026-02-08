# Agent Onboarding Guide

Welcome to the ABAY Reservoir Optimization project. This file orients future AI agents so every session starts with shared context, priorities, and conventions.

## 1. Know the Landscape First
- **Read the README** for a system-level refresher before coding. It summarizes how the Django web app, optimization engine, and alerting stack fit together, and which external services (PI System, Upstream API, YES Energy, Twilio) we depend on.【F:README.md†L1-L125】
- **Two major code pillars**:
  - `abay_opt/`: core optimization, physics, data prep, and CLI helpers. The MILP solver and rafting constraints live in `optimizer.py`. Start there when touching optimization logic; however, changes to these files should be avoided if possible.【F:abay_opt/optimizer.py†L1-L186】
  - `django_backend/`: Django project containing REST APIs, Channels/WebSockets, Celery tasks, templates, and static assets.【F:django_backend/optimization_api/views.py†L1-L40】【F:django_backend/templates/dashboard.html†L1-L146】

## 2. Current Focus Areas
1. **Operator UX polish** – The dashboard template and `dashboard.css` define the multi-tab UI built on Chart.js and Handsontable.js. Any front-end changes should preserve accessibility, responsive layout, and the polished visual language already in place.【F:django_backend/templates/dashboard.html†L50-L145】【F:django_backend/static/css/dashboard.css†L9-L160】
2. **Interactive editing & persistence** – Milestone A/B tasks require keeping server-driven recalculations (`abay_opt/recalc.py`) and Django endpoints in sync with the editable grid workflow described in the roadmap.【F:TASKS.md†L12-L46】
3. **Alerting platform maturity** – `optimization_api/alerting.py` and related models orchestrate email/SMS/voice/browser notifications, Twilio integration, and cooldown logic. Treat alert work as a first-class feature alongside UX polish.【F:django_backend/optimization_api/alerting.py†L10-L200】【F:django_backend/optimization_api/models.py†L254-L400】

## 3. Working with the Codebase
- **Front-end updates**
  - Keep scripts modular. Dashboard charts currently depend on API responses; coordinate template changes with the corresponding JS modules under `static/js` (if you add or rename IDs/classes, update the JS).
  - Maintain keyboard navigation and descriptive labels when adding buttons, tabs, or modal dialogs. Reuse `.btn`, `.icon-button`, and `.tab-*` styles to stay consistent.【F:django_backend/templates/dashboard.html†L70-L143】【F:django_backend/static/css/dashboard.css†L41-L160】
  - When extending price or alert tabs, check the backing API views (e.g., `ElectricityPriceView`) to ensure endpoints deliver the data shape the UI expects.【F:django_backend/optimization_api/views.py†L48-L195】
- **Backend/API work**
  - Use existing serializers/models (`OptimizationRun`, `ParameterSet`, `OptimizationResult`, etc.) to persist optimization artifacts rather than inventing new stores.【F:django_backend/optimization_api/views.py†L33-L39】
  - Follow the established pattern of dynamically appending the project root to `sys.path` for entry points that run outside Django’s default context (see `alerting.py` and price views) to keep `abay_opt` imports reliable.【F:django_backend/optimization_api/alerting.py†L10-L30】【F:django_backend/optimization_api/views.py†L67-L116】
  - When touching optimization logic, prefer adding configuration hooks through `ParameterSet`/`OptimizationParameters` so operators can tune values through the UI instead of hard-coding.【F:django_backend/optimization_api/models.py†L254-L400】

## 4. Alerting Platform Guidance
- Alert definitions, logs, and user notification preferences live in the Django models—extend these rather than duplicating state. Respect cooldowns and per-user channels provided by `AlertingService` when implementing new alert checks or delivery paths.【F:django_backend/optimization_api/models.py†L254-L400】【F:django_backend/optimization_api/alerting.py†L35-L153】
- Any UI enhancements to the “Alert Settings” tab should mirror the categories and metadata surfaced by the alert API responses for consistency.【F:django_backend/templates/dashboard.html†L53-L146】
- Twilio and email credentials are optional. Wrap Twilio usage defensively (as existing code does) so local development works without those secrets.【F:django_backend/optimization_api/alerting.py†L41-L151】

## 5. Execution Checklist Each Session
1. Skim `README.md` to refresh goals and constraints.【F:README.md†L1-L158】
2. Confirm local entry points (custom scripts, Celery tasks, alerts) add the repo root to `sys.path` before importing `abay_opt` to avoid `ModuleNotFoundError` surprises.【F:django_backend/optimization_api/alerting.py†L10-L30】【F:django_backend/optimization_api/views.py†L67-L116】
3. Run relevant tests before handing work back. Ensure django is installed. At minimum execute `python manage.py test`, and add targeted suites (e.g., alert tests) when you modify those areas.【F:Install_Instructions.txt†L885-L895】
4. Ensure django is running when testing front-end changes: `python manage.py runserver` (default port 8000). Refresh the browser to see template/CSS/JS updates.【F:Install_Instructions.txt†L875-L885】
5. Document UX or alert changes clearly in PR summaries so operators understand user-facing impacts.

## 6. Ideation Backlog
- **UX Enhancements**: Explore inline validation in the data grid, richer chart annotations (e.g., rafting windows, alert markers), and saved layout presets per `UserProfile` preferences.【F:django_backend/templates/dashboard.html†L65-L145】【F:django_backend/optimization_api/models.py†L254-L307】
- **Alerting Evolution**: Integrate real optimization metrics (spillage, ramp rate, rafting schedule) into the alert checks, add WebSocket acknowledgment workflows, and surface alert history filters in the dashboard.【F:django_backend/optimization_api/alerting.py†L53-L153】【F:django_backend/templates/dashboard.html†L53-L146】
- **Data Persistence Milestones**: Finish Milestones B and C from `TASKS.md` to unlock comparisons and historical scenario replay for operators.【F:TASKS.md†L31-L75】

Use this guide to stay consistent with prior work, communicate priorities, and keep the experience cohesive as the project evolves.