# CLAUDE.md

Quick reference for Claude Code when working with the ABAY Reservoir Optimization system.

## Project Overview

ABAY Reservoir Optimization — a Django web app that uses MILP linear programming to optimize Oxbow Powerhouse (OXPH) generation while maintaining Afterbay reservoir levels and meeting rafting requirements. Serves ~8 operators; SQLite by design.

The **only** optimization engine is `abay_opt/` (not the legacy `abay_optimization` package). The Django front-end calls a thin set of views that import from `abay_opt` and return JSON for the grid and charts.

> Physics, rules, and constants follow the goal spec (ABAY net-flow identity, GEN/SPILL logic, MFRA side-water reduction, OXPH linear MW->cfs, quadratic ft<->AF, rafting windows, head-limit). Bias is 24h actual-expected and is applied additively to the forecast net inflow.

## Quick Start

```bash
source venv312/Scripts/activate
cd django_backend
python manage.py runserver
# Visit http://localhost:8000
```

## Project Structure

```
Oxbow_Django_Optimization/
├── abay_opt/                          # Core engine (single source of truth)
│   ├── bias.py                        # 24h rolling bias computation
│   ├── build_inputs.py                # Assembles lookback+forecast (supports historical)
│   ├── caiso_da.py                    # CAISO DA awards service (fetch, aggregate, query)
│   ├── cli.py                         # CLI (CSV writer + annotations)
│   ├── config/                        # API credentials (not in Git)
│   ├── constants.py                   # Physical constants and thresholds
│   ├── data_fetcher.py                # PI System and Upstream API data retrieval
│   ├── optimizer.py                   # MILP solver (PuLP/CBC)
│   ├── physics.py                     # Water balance, stage-storage, head loss
│   ├── recalc.py                      # Forward recalc for operator edits (no MILP)
│   ├── schedule.py                    # Rafting window logic
│   ├── test_entry.py                  # Convenience runner for QA/historical testing
│   ├── utils.py
│   └── yes_energy_grab.py             # Optional energy prices
│
├── caiso_config/                      # CAISO B2B API configuration
│   ├── caiso_cert.pem                 # CAISO client certificate (not in Git)
│   └── Programs/
│       ├── caiso_api.py               # CAISO CMRI API client (SOAP/WS-Security)
│       └── CAISO_Data_grabber.py      # Envelope builder + signer
│
├── django_backend/
│   ├── manage.py
│   ├── db.sqlite3                     # SQLite database (WAL mode)
│   │
│   ├── django_backend/                # Django settings
│   │   ├── settings.py
│   │   ├── urls.py
│   │   └── celery.py
│   │
│   ├── optimization_api/              # Main Django app
│   │   ├── views.py                   # API endpoints
│   │   ├── models.py                  # Data models (runs, alerts, profiles)
│   │   ├── alerting.py                # Alert engine (email, SMS, voice, browser)
│   │   ├── tasks.py                   # Background tasks
│   │   ├── consumers.py               # WebSocket handlers
│   │   └── management/commands/
│   │       ├── monitor_alerts.py      # Alert monitoring command
│   │       └── monitor_sqlite.py      # DB lock monitoring
│   │
│   ├── templates/
│   │   ├── dashboard.html             # Main UI
│   │   └── profile.html               # User settings
│   │
│   ├── static/js/
│   │   ├── dashboard.js               # Frontend logic (ECharts charts, gauges, timeline)
│   │   ├── echart-theme.js            # Custom ECharts themes (oxbow-light, oxbow-dark)
│   │   ├── command-palette.js         # Ctrl+K palette, boot sequence, keyboard shortcuts
│   │   ├── system-schematic.js        # Animated SVG water flow diagram
│   │   ├── auth-alerts.js             # Auth, WebSocket & smart alert toasts
│   │   └── session-manager.js
│   │
│   ├── static/css/
│   │   └── dashboard.css              # Neon dark theme, glassmorphism, all component styles
│   │
│   └── optimization_outputs/          # CSV results storage
│
├── output/                            # LP problem files
└── debug_lp_problem.py                # Standalone LP debugger
```

## How the Pieces Interact

1. **Run optimization** from Django: call `build_inputs(...)` then `build_and_solve(...)` (from `optimizer.py`). After solve, compute hour-average generation & `setpoint_change_time` using the helper in `cli.py` and prepare JSON for the front-end grid.
2. **Operator edits**: the grid posts overrides to `/api/simulate`, which calls `recalc.recalc_abay_path(...)` to recompute ABAY path from the edited hour forward without re-solving. Only changed rows are returned.
3. **Save**: POST the current schedule to `/api/runs` to write originals and (optionally) adjustments to SQLite (Django ORM).
4. **Compare**: GET `/api/runs/{id}/compare/{id2}` to retrieve aligned series for overlay and tabular diff.

### Historical Analysis
- When you pass a `historical_start`, `build_inputs()` uses actual PI series as the "forecast" block for the forward window; bias still uses the prior 24h lookback. This mirrors running "as if" on that day.
- `test_entry.py` demonstrates running the full pipeline in historical mode without touching the CLI.

## Architecture Overview

### System Components
1. **Optimization Engine** (`abay_opt/`) — MILP solver, physics, data fetching, CLI helpers. The solver and rafting constraints live in `optimizer.py`.
2. **Django Backend** (`django_backend/`) — REST API, WebSocket support, Celery background tasks, user auth, templates and static assets.
3. **Alert System** (`optimization_api/alerting.py`) — Email, SMS (Twilio), voice, browser notifications. Category-based thresholds with cooldown logic. SMS/voice pending Twilio API approval.

### Key Integration Points
- **PI System**: Real-time operational data (requires VPN/network access)
- **Upstream API**: River flow forecasts (HydroForecast/CNRFC) with quantiles
- **CAISO B2B API**: Day-ahead market awards for MFRA
- **YES Energy API**: Electricity pricing data (optional)
- **Twilio**: SMS and voice alerts (pending API approval)

### Database Design
- SQLite with WAL mode (intentional choice for ~8 users)
- Key models: `OptimizationRun`, `OptimizationResult`, `ParameterSet`, `AlertThreshold`, `AlertLog`, `UserProfile`
- Session-based authentication with 7-day "Remember Me" option

### Frontend Stack
- **Apache ECharts 5** — all charts, gauges, and timeline (custom themes in `echart-theme.js`)
- **Handsontable 14.3.0** — editable forecast data table
- **Vanilla JS** — no React/Vue/Angular; modular JS files under `static/js/`
- **Neon dark theme** — glassmorphism, accents: cyan `#00d4ff`, magenta `#ff006e`, lime `#00ff88`, amber `#ffbe0b`

## Django Endpoints

- `POST /api/optimize` — run a new optimization (optional `historical_start`, `horizon`, `forecast_source`); returns JSON rows for the grid.
- `POST /api/simulate` — apply per-hour overrides and return only the edited hour and later rows with new `ABAY_ft`, `ABAY_af`, `OXPH_outflow_cfs`, `MF_1_2_*`, `violates_min/float/head`.
- `POST /api/runs` — save the current schedule to SQLite (originals).
- `POST /api/runs/{id}/adjustments` — persist operator edits for that run.
- `GET /api/runs/recent?n=10` — list recent runs for a user.
- `GET /api/runs/{id}` — load a run.
- `GET /api/runs/{id}/compare/{id2}` — aligned comparison.
- `POST /api/caiso-da-awards/` — fetch DA awards from CAISO.
- `GET /api/caiso-da-awards/?trade_date=YYYY-MM-DD` — get stored awards.
- `GET /api/system-status/` — current system health.

## Key Commands

```bash
# Activate venv (Windows / Git Bash)
source venv312/Scripts/activate

# Run dev server
cd django_backend
python manage.py runserver

# Run optimizer from CLI (writes CSV)
python -m abay_opt.cli --horizon 72 --outfile ./abay_schedule.csv

# Historical scenario
python -m abay_opt.cli --historical-start "2025-06-28T00:00" --outfile ./abay_schedule_hist.csv

# Test entry (Python runner)
python -m abay_opt.test_entry

# Full system startup
python manage.py runserver                          # Terminal 1: Django
python manage.py monitor_alerts --interval 60       # Terminal 2: Alerts
celery -A django_backend worker -l info             # Terminal 3: Celery (optional)
redis-server                                        # Terminal 4: Redis (optional)
```

## Testing

```bash
cd django_backend

# Run all tests
python manage.py test

# Targeted test suites
python -m unittest optimization_api.tests.test_alerts
python -m unittest optimization_api.tests.test_models
python -m unittest optimization_api.tests.test_views
python -m unittest abay_opt.tests.test_recalc
python -m unittest abay_opt.tests.test_physics

# Test alert system
python manage.py monitor_alerts --once --test-mode --verbose

# Check Django configuration
python manage.py check

# Database management
python manage.py makemigrations
python manage.py migrate
python manage.py collectstatic
```

## Design Decisions
- SQLite chosen intentionally for small user base (~8 users max)
- Focus on reliability over scalability
- All times in Pacific timezone
- Vanilla JS frontend — no framework
- Apache ECharts 5 for all charting (migrated from Chart.js Feb 2026)
- Test messages should be generic (no fake data)

## Common Issues and Solutions

| Issue | Solution |
|-------|----------|
| Optimization "Infeasible" | Check reservoir level vs minimum requirements; verify inflow forecasts are reasonable |
| PI System unavailable | Falls back to simulation mode automatically |
| WebSocket disconnects | Auto-reconnects every 5 seconds |
| SQLite locks | WAL mode enabled; check `logs/sqlite_locks.log`; restart Django if persistent |
| `ModuleNotFoundError: abay_opt` | Ensure project root is on `sys.path` (see pattern in `alerting.py`) |

## Key File Locations
- **Optimization Results**: `django_backend/optimization_outputs/`
- **LP Problem Files**: `output/` (for debugging)
- **API Credentials**: `abay_opt/config/` (not in Git)
- **Logs**: `django_backend/logs/`, `django_backend/django.log`
- **Database**: `django_backend/db.sqlite3`

## Current State (February 2026)
- Optimizer is stable and production-ready.
- Full UI overhaul completed: ECharts, neon theme, gauges, schematic, command palette, smart toasts.
- Data table remediation complete: physics-parity editing, ABAY forecast visibility, timestamp semantics, R20 editing.
- Alerting backend fully implemented (Twilio SMS/voice pending API approval; email and browser alerts are live).
- CAISO DA Awards integration operational.
- See `TASKS.md` for current backlog and `PRD.md` for phased delivery plan.

## Documentation Index

### Architecture & Requirements
- [README.md](README.md) — System overview, installation, features, configuration
- [AGENTS.md](AGENTS.md) — Agent onboarding guide with priorities and conventions
- [PRD.md](PRD.md) — Product requirements (v3.0), technical specs, phased delivery plan
- [TASKS.md](TASKS.md) — Planning backlog and implementation status

### Setup & Infrastructure
- [WSL_Setup.md](WSL_Setup.md) — WSL + Claude Code agent teams setup

### Optimization Engine
- [misc_files/OPTIMIZATION_IMPROVEMENTS.md](misc_files/OPTIMIZATION_IMPROVEMENTS.md) — Analysis of optimization approaches and bug fixes
- [misc_files/optimizer_plan.md](misc_files/optimizer_plan.md) — Optimizer refactoring plan (spillage fix)

### CAISO Market Integration
- [caiso_config/CAISO_MARKET_DATA.md](caiso_config/CAISO_MARKET_DATA.md) — CAISO market structure and revenue guide
- [caiso_config/DATA_MODEL.md](caiso_config/DATA_MODEL.md) — Data model for hydro market performance analyzer
- [caiso_config/README_FROM_OTHER_PROGRAM.md](caiso_config/README_FROM_OTHER_PROGRAM.md) — Related PCWA hydro analyzer overview
