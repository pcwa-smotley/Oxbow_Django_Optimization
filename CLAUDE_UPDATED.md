
# CLAUDE.md — Operator UX & Django Integration (updated for `abay_opt/`)

This replaces the older notes that referenced the legacy `abay_optimization` package. The **only** engine now is `abay_opt/` (see structure below). The Django front‑end calls a thin set of views that import from `abay_opt` and return JSON for the grid and charts. 

> Physics, rules, and constants follow the goal spec (ABAY net‑flow identity, GEN/SPILL logic, MFRA side‑water reduction, OXPH linear MW→cfs, quadratic ft↔AF, rafting windows, head‑limit). Bias is 24h actual−expected and is applied additively to the forecast net inflow. 


## Current Project Structure

```
Oxbow_Django_Optimization/
├── abay_opt/                          # Core engine (single source of truth)
│   ├── bias.py
│   ├── build_inputs.py                # assembles lookback+forecast (supports historical)
│   ├── cli.py                         # CLI (CSV writer + annotations)
│   ├── config/                        # API credentials (not in Git)
│   ├── constants.py
│   ├── data_fetcher.py
│   ├── optimizer.py
│   ├── physics.py
│   ├── recalc.py                      # forward recalc for operator edits (no MILP)
│   ├── schedule.py                    # rafting window logic
│   ├── test_entry.py                  # convenience runner for QA/historical testing
│   ├── utils.py
│   └── yes_energy_grab.py             # optional energy prices
│
├ django_backend/
│   ├── manage.py              # Django management script
│   ├── db.sqlite3            # SQLite database
│   │
│   ├── django_backend/       # Django settings
│   │   ├── settings.py      # Main configuration
│   │   ├── urls.py         # Root URL config
│   │   └── celery.py       # Background task config
│   │
│   ├── optimization_api/     # Main Django app
│   │   ├── views.py         # API endpoints
│   │   ├── models.py        # Data models
│   │   ├── alerting.py      # Alert engine
│   │   ├── tasks.py         # Background tasks
│   │   ├── consumers.py     # WebSocket handlers
│   │   └── management/commands/
│   │       ├── monitor_alerts.py   # Alert monitoring
│   │       └── monitor_sqlite.py   # DB lock monitoring
│   │
│   ├── templates/
│   │   ├── dashboard.html   # Main UI
│   │   └── profile.html     # User settings
│   │
│   ├── static/js/
│   │   ├── dashboard.js     # Frontend logic
│   │   ├── auth-alerts.js   # Auth & WebSocket
│   │   └── session-manager.js
│   │
│   └── optimization_outputs/  # CSV results storage
│
├── output/                    # LP problem files
└── debug_lp_problem.py       # Standalone LP debugger
```

## How the pieces interact

1) **Run optimization** from Django: call `build_inputs(...)` then `build_and_solve(...)` (from `optimizer.py`). After solve, compute hour‑average generation & `setpoint_change_time` using the helper in `cli.py` and prepare JSON for the front‑end grid.  
2) **Operator edits**: the grid posts overrides to `/api/simulate`, which calls `recalc.recalc_abay_path(...)` to recompute **ABAY path from the edited hour forward** without re‑solving. Only changed rows are returned.  
3) **Save**: POST the current schedule to `/api/runs` to write originals and (optionally) adjustments to SQLite (Django ORM).  
4) **Compare**: GET `/api/runs/{id}/compare/{id2}` to retrieve aligned series for overlay and tabular diff.  

### Historical analysis

- Default: when you pass a `historical_start`, `build_inputs()` uses **actual PI series** as the “forecast” block for the forward window; bias still uses the prior 24h lookback. This mirrors running “as if” on that day.  
- `test_entry.py` demonstrates running the full pipeline in historical mode without touching the CLI. 


## Key commands

```bash
# Run the optimizer from CLI (writes CSV)
python -m abay_opt.cli --horizon 72 --outfile ./abay_schedule.csv

# Historical scenario (uses actuals by default when historical_start is set)
python -m abay_opt.cli --historical-start "2025-06-28T00:00" --outfile ./abay_schedule_hist.csv

# Test entry (Python runner)
python -m abay_opt.test_entry
```

## Django endpoints (minimal)

- `POST /api/optimize` → run a new optimization (optional `historical_start`, `horizon`, `forecast_source`); returns JSON rows for the grid.  
- `POST /api/simulate` → apply per‑hour overrides and return only the edited hour **and later** rows with new `ABAY_ft`, `ABAY_af`, `OXPH_outflow_cfs`, `MF_1_2_*`, `violates_min/float/head`.  
- `POST /api/runs` → save the current schedule to SQLite (originals).  
- `POST /api/runs/{id}/adjustments` → persist operator edits for that run.  
- `GET /api/runs/recent?n=10` → list recent runs for a user.  
- `GET /api/runs/{id}` → load a run.  
- `GET /api/runs/{id}/compare/{id2}` → aligned comparison.  


## Testing- Run all tests: `python manage.py test`  
- Alert tests only: `python -m unittest optimization_api.tests.test_alerts`  
- Model tests only: `python -m unittest optimization_api.tests.test_models`  
- View tests only: `python -m unittest optimization_api.tests.test_views`  
- Recalc tests only: `python -m unittest abay_opt.tests.test_recalc`  
- Physics tests only: `python -m unittest abay_opt.tests.test_physics`

