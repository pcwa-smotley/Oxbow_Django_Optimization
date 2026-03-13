# ABAY Reservoir Optimization System

A Django-based water reservoir optimization system that uses MILP linear programming to optimize the Oxbow Powerhouse (OXPH) generation schedule while maintaining reservoir levels and meeting recreational rafting requirements.

## Table of Contents
- [Overview](#overview)
- [Features](#features)
- [System Requirements](#system-requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Running the System](#running-the-system)
- [Usage](#usage)
- [Optimization Approaches](#optimization-approaches)
- [Troubleshooting](#troubleshooting)
- [Development](#development)

## Overview

The ABAY Reservoir Optimization System manages water flow through the Afterbay (ABAY) reservoir by optimizing the Oxbow Powerhouse (OXPH) generation schedule. It balances multiple objectives:
- Maintaining reservoir elevation between 1168-0.5' Below Float
- Meeting summer recreational rafting requirements
- Avoiding water spillage
- Maximizing power generation efficiency
- Minimizing operational changes

## Features

### Core Capabilities
- **MILP Optimization**: Mixed-Integer Linear Programming via PuLP/CBC with automatic fallback for robustness
- **Real-time Data Integration**: Connects to PI System for live reservoir data
- **Forecast Integration**: Uses river flow forecasts from Upstream API (HydroForecast/CNRFC)
- **Historical Bias Correction**: 24-hour rolling bias applied additively to forecast net inflow
- **CAISO DA Awards Integration**: Fetch Day Ahead market awards for Middle Fork (MFP1) from CAISO B2B API to replace persistence-based MFRA forecasts with scheduled generation data
- **Multi-channel Alerts**: Email, SMS (Twilio), voice, and browser notifications for critical events (SMS/voice pending Twilio API approval)
- **Web Dashboard**: Mission-control-grade real-time monitoring and control interface

### Dashboard UI
- **Neon Control Room Theme**: Dark mode with cyan/magenta/lime/amber accents, glassmorphism cards, animated mesh gradient background
- **Apache ECharts 5**: Interactive charts with synced crosshairs, DataZoom sliders, day dividers, and smooth animations
- **KPI Gauge Strip**: Five animated gauges (ABAY Elevation, OXPH Output, Spill Risk, Revenue Rate, Forecast Confidence)
- **Live System Schematic**: Animated SVG water flow diagram with particle animations showing real-time flow through MFRA, R30, R4, ABAY, OXPH, and Spillway
- **7-Day Operations Timeline**: Bar chart overview of OXPH setpoints with rafting window highlights and day boundaries
- **Editable Data Table**: Handsontable grid with physics-parity recalculation — edit setpoints and see ABAY forecast impact immediately via ramp + head-limit physics
- **Command Palette**: Ctrl+K quick-action palette with fuzzy search, keyboard shortcuts (1-8 for tabs, D for dark mode, ? for help)
- **Smart Alert Toasts**: Slide-in notifications with severity icons, audio chimes for critical alerts, stacking with overflow badge
- **MFRA Source Indicator**: Badge showing whether MFRA forecast uses "DA Awards" (green) or "Persistence" (amber), plus a "Fetch DA Awards" button on the power chart
- **Cinematic Boot Sequence**: System initialization animation with real status checks (skipped on repeat visits)
- **Real-Time Status Bar**: Live indicators for PI System, ABAY elevation, OXPH output, last optimization run, and WebSocket status

### Optimization Features
- 168-hour (7-day) forecast horizon
- Piecewise linear approximation for non-linear relationships
- Head loss constraints based on reservoir elevation
- Ramp rate limitations (0.042 MW/min)
- Summer rafting schedule compliance
- Automatic fallback to simpler optimization when primary fails

### Alerting System
- **Multi-channel delivery**: Email, SMS, voice call, browser notification
- **Category-based thresholds**: Flow, Afterbay, Rafting, Generation
- **Cooldown logic**: Prevents alert fatigue with configurable cooldown windows
- **Per-user preferences**: Each operator configures their own channels and phone number
- **Voice escalation**: Critical unacknowledged alerts trigger voice calls
- **Status**: Backend fully implemented. SMS/voice delivery pending Twilio API approval. Email and browser alerts are operational now.

## System Requirements

### Software
- Python 3.12 or higher
- Django 4.2+
- Redis (optional, for Celery background tasks)
- Modern web browser (Chrome, Firefox, Safari, Edge)

### Frontend Libraries (CDN)
- Apache ECharts 5 (interactive charts and gauges)
- Handsontable 14.3.0 (editable forecast data table)

### Python Dependencies
```
django>=4.2
djangorestframework
pandas>=1.5.0
numpy>=1.23.0
pulp>=2.7.0
scipy>=1.9.0
pytz
requests
websockets
channels
redis (optional)
celery (optional)
twilio (optional, for SMS/voice alerts — pending API approval)
caisopy-b2b (optional, for CAISO DA awards)
lxml (optional, for CAISO XML parsing)
```

### Network Requirements
- VPN access for PI System integration (production)
- Internet access for forecast APIs
- Port 8000 for Django development server
- Port 6379 for Redis (if using Celery)

## Installation

### 1. Clone the Repository
```bash
git clone https://github.com/your-org/Oxbow_Django_Optimization.git
cd Oxbow_Django_Optimization
```

### 2. Create Virtual Environment
```bash
# Windows
python -m venv venv312
venv312\Scripts\activate

# Linux/Mac (or Git Bash on Windows)
python3 -m venv venv312
source venv312/Scripts/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure API Credentials
Create the configuration directory and add your API credentials:
```bash
mkdir abay_opt/config

# Create API credentials file and edit with your actual keys
# abay_opt/config/api_credentials.json
```

Required credential sections:
- `pi_system` — PI Web API URL, username, password
- `upstream_api` — Upstream API key and base URL
- `yes_energy` — YES Energy API key (optional)
- `twilio` — Account SID, auth token, from number (pending API approval)

### 5. Initialize Database
```bash
cd django_backend
python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser  # Create admin user
```

### 6. Collect Static Files
```bash
python manage.py collectstatic --noinput
```

## Configuration

### Django Settings
Edit `django_backend/django_backend/settings.py`:

```python
# Development settings
DEBUG = True  # Set to False for production

# Optimization settings
ABAY_OPTIMIZATION = {
    'USE_SIMULATED_DATA': True,  # False to use real PI data
    'USE_HYBRID_OPTIMIZER': True,
    'FORECAST_HORIZON_DAYS': 7,
    'SIMULATION_INTERVAL_MINUTES': 60,
}
```

### Operational Constants
Edit `abay_opt/constants.py` for system parameters:

```python
# Physical constraints
ABAY_MIN_ELEV_FT = 1167.0
OXPH_MIN_MW = 0.7
OXPH_MAX_MW = 5.8
OXPH_RAMP_RATE_MW_PER_MIN = 0.042

# Optimization priorities (1=highest, 5=lowest)
PRIORITY_AVOID_SUMMER_SPILL = 1
PRIORITY_AVOID_SPILL = 2
PRIORITY_SUMMER_RAFTING = 2
PRIORITY_SMOOTH_OPERATION = 3
PRIORITY_MIDPOINT_ELEVATION = 4
```

## Running the System

### Quick Start (Development)
```bash
source venv312/Scripts/activate
cd django_backend
python manage.py runserver

# Open browser to: http://localhost:8000
```

### Full System Startup (Production-like)

#### Terminal 1: Django Server
```bash
cd django_backend
python manage.py runserver 0.0.0.0:8000
```

#### Terminal 2: Alert Monitoring (Optional)
```bash
cd django_backend
python manage.py monitor_alerts --interval 60
```

#### Terminal 3: Celery Worker (Optional, for background tasks)
```bash
cd django_backend
celery -A django_backend worker -l info
```

#### Terminal 4: Redis Server (Optional, if using Celery)
```bash
redis-server
```

### Running Optimization Standalone
```bash
# Run optimizer from CLI (writes CSV)
python -m abay_opt.cli --horizon 72 --outfile ./abay_schedule.csv

# Historical scenario (uses actuals when historical_start is set)
python -m abay_opt.cli --historical-start "2025-06-28T00:00" --outfile ./abay_schedule_hist.csv

# Test entry (Python runner)
python -m abay_opt.test_entry
```

## Current Project Structure

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

## Usage

### Web Dashboard

1. **Login**: Navigate to http://localhost:8000 and login with your credentials

2. **Main Dashboard** shows:
   - Current reservoir elevation with KPI gauges
   - OXPH generation status
   - 7-day optimization forecast with interactive ECharts
   - Animated system schematic with real-time flow
   - Real-time alerts and system status indicators

3. **Controls**:
   - **Run Optimization**: Generate a new schedule
   - **Optimization Settings**: Adjust priorities and parameters
   - **Alert Settings**: Configure notification thresholds and channels
   - **Export Results**: Download optimization results as CSV
   - **Command Palette (Ctrl+K)**: Quick navigation and actions

### CAISO Day Ahead Awards (MFRA Forecast)

By default the optimizer assumes Middle Fork will produce the same MW tomorrow as it did yesterday ("persistence"). When CAISO Day Ahead awards are available, they provide a more accurate hourly schedule.

**Fetching DA Awards:**
1. Click the **"Fetch DA Awards"** button next to the power chart mode selector
2. The system calls the CAISO B2B API to retrieve DAM awards for the MFP1 scheduling coordinator
3. A notification confirms how many hours of awards were loaded and the average MW

**How it works in the optimizer:**
- When you click **Run Optimization**, `build_inputs()` first checks for stored DA awards covering the forecast window
- If DA awards cover at least 50% of the forecast hours, they are used as the MFRA forecast
- If no DA awards are available (or coverage is too low), the optimizer silently falls back to persistence
- The **MFRA source badge** shows which method was used:
  - Green **"MFRA: DA Awards"** — scheduled generation from CAISO
  - Amber **"MFRA: Persistence"** — yesterday's generation pattern

**When to fetch:**
- CAISO typically publishes DA awards after ~1 PM Pacific for the next delivery day
- You can fetch at any time — if awards aren't posted yet, the system gracefully falls back to persistence

**Requirements:**
- `caisopy-b2b` and `lxml` packages installed (`pip install caisopy-b2b lxml`)
- Valid CAISO client certificate at `caiso_config/caiso_cert.pem`
- If the certificate or packages are missing, the system logs a warning and uses persistence — it never crashes

### API Endpoints

#### Core Operations
```bash
# Get system status
curl http://localhost:8000/api/system-status/

# Run optimization
curl -X POST http://localhost:8000/api/run-optimization/ \
  -H "Content-Type: application/json" \
  -d '{"use_hybrid": true}'

# Get latest optimization results
curl http://localhost:8000/api/optimization-results/latest/

# Simulate operator edits (recalc from edited hour forward)
curl -X POST http://localhost:8000/api/simulate/ \
  -H "Content-Type: application/json" \
  -d '{"overrides": [...]}'
```

#### CAISO DA Awards
```bash
# Fetch awards for the next delivery day
curl -X POST http://localhost:8000/api/caiso-da-awards/

# Fetch awards for a specific date
curl -X POST http://localhost:8000/api/caiso-da-awards/ \
  -H "Content-Type: application/json" \
  -d '{"trade_date": "2026-02-08"}'

# Get stored awards
curl http://localhost:8000/api/caiso-da-awards/?trade_date=2026-02-08
```

#### Run Management
```bash
# Save current schedule
curl -X POST http://localhost:8000/api/runs/

# List recent runs
curl http://localhost:8000/api/runs/recent?n=10

# Load a run
curl http://localhost:8000/api/runs/{id}

# Compare two runs
curl http://localhost:8000/api/runs/{id}/compare/{id2}
```

### Command-Line Management

```bash
# Database management
python manage.py dbshell
python manage.py dumpdata > backup.json
python manage.py loaddata backup.json

# User management
python manage.py createsuperuser
python manage.py changepassword username

# System monitoring
python manage.py check
python manage.py monitor_sqlite
python manage.py monitor_alerts --once --test-mode
```

## Optimization Approaches

### MILP Optimizer (Primary)
The system uses Mixed-Integer Linear Programming via PuLP with the CBC solver:
- Precise constraint handling with guaranteed feasibility when solution exists
- Solve time <2 seconds for 168-hour horizons
- Piecewise-linear stage-storage mapping for ABAY ft<->AF
- Ramp rate, head loss, and rafting window constraints
- Weighted penalty objective for elevation bounds, spill avoidance, and smooth operation

### Historical Bias Correction
The system automatically:
- Analyzes past 24 hours of predictions vs actual
- Calculates average prediction error (clipped ±2000 CFS)
- Applies bias correction to future forecasts additively

### Physics Pipeline
```
build_inputs() → build_and_solve() → recalc_abay_path()
     ↑                   ↑                    ↑
  DA awards +      MILP solver         Forward recalc
  persistence      (optimizer.py)      for operator edits
  + bias                               (no re-solve)
```

## Troubleshooting

### Common Issues

#### 1. Database Migration Error: "unexpected keyword argument 'init_command'"
**Cause**: Incompatibility with newer Python sqlite3 versions
**Solution**: SQLite optimizations moved to apps.py. Run `python manage.py check` to verify.

#### 2. Optimization Fails with "Infeasible"
**Cause**: Constraints cannot be satisfied
**Solution**: Check reservoir level vs minimum requirements. Verify inflow forecasts are reasonable.

#### 3. PI System Connection Error
**Cause**: VPN not connected or credentials invalid
**Solution**: Verify VPN connection. Check credentials in `abay_opt/config/api_credentials.json`. System will use simulated data as fallback.

#### 4. WebSocket Disconnections
**Cause**: Network issues or server restart
**Solution**: WebSockets auto-reconnect every 5 seconds.

#### 5. Database Locked Error
**Cause**: SQLite concurrent access
**Solution**: WAL mode is enabled by default. Check `logs/sqlite_locks.log`. Restart Django if persistent.

### Log Files
- Django logs: `django_backend/django.log`
- SQLite locks: `django_backend/logs/sqlite_locks.log`
- Optimization results: `django_backend/optimization_outputs/`
- LP problem files: `output/`

## Development

### Running Tests
```bash
cd django_backend

# Run all tests
python manage.py test

# Alert tests only
python -m unittest optimization_api.tests.test_alerts

# Model tests only
python -m unittest optimization_api.tests.test_models

# View tests only
python -m unittest optimization_api.tests.test_views

# Recalc tests
python -m unittest abay_opt.tests.test_recalc

# Physics tests
python -m unittest abay_opt.tests.test_physics
```

### Design Decisions
- SQLite chosen intentionally for small user base (~8 operators)
- All times in Pacific timezone
- Focus on reliability over scalability
- Vanilla JS frontend (no React/Vue/Angular)
- Apache ECharts 5 for all charting (migrated from Chart.js)

## License

[Your License Here]

## Contributors

- PCWA Engineering Team

---

**Last Updated**: February 2026
**Version**: 0.3
