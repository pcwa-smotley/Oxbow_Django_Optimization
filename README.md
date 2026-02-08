# ABAY Reservoir Optimization System

A Django-based water reservoir optimization system that uses hybrid linear programming and model predictive control to optimize the Oxbow Powerhouse (OXPH) generation schedule while maintaining reservoir levels and meeting recreational rafting requirements.

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
- [Documentation](#documentation)

## Overview

The ABAY Reservoir Optimization System manages water flow through the Afterbay (ABAY) reservoir by optimizing the Oxbow Powerhouse (OXPH) generation schedule. It balances multiple objectives:
- Maintaining reservoir elevation between 1168-0.5' Below Float
- Meeting summer recreational rafting requirements
- Avoiding water spillage
- Maximizing power generation efficiency
- Minimizing operational changes

## Features

### Core Capabilities
- **Hybrid Optimization**: Combines MILP (Mixed-Integer Linear Programming) for precision with MPC (Model Predictive Control) fallback for robustness
- **Real-time Data Integration**: Connects to PI System for live reservoir data
- **Forecast Integration**: Uses river flow forecasts from Upstream API
- **Historical Bias Correction**: Learns from past prediction errors to improve accuracy
- **CAISO DA Awards Integration**: Fetch Day Ahead market awards for Middle Fork (MFP1) from CAISO B2B API to replace persistence-based MFRA forecasts with scheduled generation data
- **Multi-channel Alerts**: Email, SMS, and browser notifications for critical events
- **Web Dashboard**: Mission-control-grade real-time monitoring and control interface

### Dashboard UI
- **Neon Control Room Theme**: Dark mode with cyan/magenta/lime/amber accents, glassmorphism cards, animated mesh gradient background
- **Apache ECharts**: Interactive charts with synced crosshairs, DataZoom sliders, day dividers, and smooth animations (migrated from Chart.js)
- **KPI Gauge Strip**: Five animated gauges (ABAY Elevation, OXPH Output, Spill Risk, Revenue Rate, Forecast Confidence)
- **Live System Schematic**: Animated SVG water flow diagram with particle animations showing real-time flow through MFRA, R30, R4, ABAY, OXPH, and Spillway
- **7-Day Operations Timeline**: Bar chart overview of OXPH setpoints with rafting window highlights and day boundaries
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
twilio (optional, for SMS alerts)
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
python -m venv venv
venv\Scripts\activate

# Linux/Mac
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure API Credentials
Create the configuration directory and add your API credentials:
```bash
# Create config directory
mkdir abay_optimization/config

# Create API credentials file
# Edit this file with your actual API keys
cat > abay_optimization/config/api_credentials.json << EOF
{
    "pi_system": {
        "url": "https://your-pi-system.com/piwebapi",
        "username": "your_username",
        "password": "your_password"
    },
    "upstream_api": {
        "api_key": "your_upstream_api_key",
        "base_url": "https://api.upstream.tech"
    },
    "yes_energy": {
        "api_key": "your_yes_energy_key"
    },
    "twilio": {
        "account_sid": "your_twilio_sid",
        "auth_token": "your_twilio_token",
        "from_number": "+1234567890"
    }
}
EOF
```

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
    'USE_HYBRID_OPTIMIZER': True,  # Use hybrid MILP+MPC approach
    'FORECAST_HORIZON_DAYS': 7,
    'SIMULATION_INTERVAL_MINUTES': 60,
}
```

### Operational Constants
Edit `abay_optimization/constants.py` for system parameters:

```python
# Physical constraints
ABAY_MIN_ELEV_FT = 1167.0  # Minimum elevation
OXPH_MIN_MW = 0.7          # Minimum generation
OXPH_MAX_MW = 5.8          # Maximum generation
OXPH_RAMP_RATE_MW_PER_MIN = 0.042  # Ramp rate

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
# Start Django development server
cd django_backend
python manage.py runserver

# Access the dashboard
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

#### Test Optimization
```bash
# Test the hybrid optimizer
python test_hybrid_optimizer.py

# Debug LP problems
python debug_lp_problem.py

# Run optimization without Django
python run_real_optimization.py
```

## Current Project Structure

```
Oxbow_Django_Optimization/
├── abay_opt/                          # Core engine (single source of truth)
│   ├── bias.py
│   ├── build_inputs.py                # assembles lookback+forecast (supports historical)
│   ├── caiso_da.py                    # CAISO DA awards service (fetch, aggregate, query)
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
├── caiso_config/                      # CAISO B2B API configuration
│   ├── caiso_cert.pem                 # CAISO client certificate (not in Git)
│   └── Programs/
│       ├── caiso_api.py               # CAISO CMRI API client (SOAP/WS-Security)
│       └── CAISO_Data_grabber.py      # Envelope builder + signer
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
│   │   ├── dashboard.js        # Frontend logic (ECharts charts, gauges, timeline)
│   │   ├── echart-theme.js     # Custom ECharts themes (oxbow-light, oxbow-dark)
│   │   ├── command-palette.js  # Ctrl+K palette, boot sequence, keyboard shortcuts
│   │   ├── system-schematic.js # Animated SVG water flow diagram
│   │   ├── auth-alerts.js      # Auth, WebSocket & smart alert toasts
│   │   └── session-manager.js
│   │
│   ├── static/css/
│   │   └── dashboard.css       # Neon dark theme, glassmorphism, all component styles
│   │
│   └── optimization_outputs/  # CSV results storage
│
├── output/                    # LP problem files
└── debug_lp_problem.py       # Standalone LP debugger
```

## Usage

### Web Dashboard

1. **Login**: Navigate to http://localhost:8000 and login with your credentials

2. **Main Dashboard** shows:
   - Current reservoir elevation
   - OXPH generation status
   - 7-day optimization forecast
   - Real-time alerts
   - System status indicators

3. **Controls**:
   - **Run Optimization**: Click to generate new schedule
   - **Optimization Settings**: Adjust priorities and parameters
   - **Alert Settings**: Configure notification thresholds
   - **Export Results**: Download optimization results as CSV

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
- The **MFRA source badge** in the run metadata area shows which method was used:
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

#### Get Current Status
```bash
curl http://localhost:8000/api/system-status/
```

#### Run Optimization
```bash
curl -X POST http://localhost:8000/api/run-optimization/ \
  -H "Content-Type: application/json" \
  -d '{
    "use_hybrid": true,
    "priorities": {
      "avoid_spill": 1,
      "summer_rafting": 2,
      "smooth_operation": 3
    }
  }'
```

#### Get Optimization Results
```bash
curl http://localhost:8000/api/optimization-results/latest/
```

#### Fetch CAISO DA Awards
```bash
# Fetch awards for the next delivery day (auto-detected)
curl -X POST http://localhost:8000/api/caiso-da-awards/ \
  -H "Content-Type: application/json" \
  -d '{}'

# Fetch awards for a specific date
curl -X POST http://localhost:8000/api/caiso-da-awards/ \
  -H "Content-Type: application/json" \
  -d '{"trade_date": "2026-02-08"}'
```

#### Get Stored DA Awards
```bash
# Get awards for a specific date
curl http://localhost:8000/api/caiso-da-awards/?trade_date=2026-02-08

# Get awards for the default next delivery day
curl http://localhost:8000/api/caiso-da-awards/
```

### Command-Line Management

#### Database Management
```bash
# Check database status
python manage.py dbshell

# Backup database
python manage.py dumpdata > backup.json

# Restore database
python manage.py loaddata backup.json
```

#### User Management
```bash
# Create new user
python manage.py createsuperuser

# Change password
python manage.py changepassword username
```

#### System Monitoring
```bash
# Check system status
python manage.py check

# Monitor SQLite locks
python manage.py monitor_sqlite

# Test alert system
python manage.py monitor_alerts --once --test-mode
```

## Optimization Approaches

### Hybrid Optimizer (Default)
The system uses a hybrid approach combining two optimization methods:

1. **Primary: MILP (Mixed-Integer Linear Programming)**
   - Precise constraint handling
   - Guarantees feasibility when solution exists
   - Uses PuLP with CBC solver

2. **Fallback: MPC (Model Predictive Control)**
   - Activated when MILP is infeasible
   - Uses penalty-based soft constraints
   - More robust to difficult conditions

### Historical Bias Correction
The system automatically:
- Analyzes past 24 hours of predictions vs actual
- Calculates average prediction error
- Applies bias correction to future forecasts

### Switching Between Optimizers
```python
# In optimization request
{
    "use_hybrid": true,  # true for hybrid, false for MILP-only
    "optimization_params": {
        "priorities": {
            "avoid_summer_spill": 1,
            "avoid_spill": 2,
            "summer_rafting": 2,
            "smooth_operation": 3,
            "midpoint_elevation": 4
        }
    }
}
```

## Troubleshooting

### Common Issues

#### 1. Database Migration Error: "unexpected keyword argument 'init_command'"
**Cause**: Incompatibility with newer Python sqlite3 versions
**Solution**: 
- The fix has been applied - SQLite optimizations moved to apps.py
- If you encounter this, ensure you're using the latest code
- Run `python manage.py check` to verify configuration

#### 2. Optimization Fails with "Infeasible"
**Cause**: Constraints cannot be satisfied
**Solution**: 
- Check reservoir level vs minimum requirements
- Verify inflow forecasts are reasonable
- System will automatically try MPC fallback

#### 3. PI System Connection Error
**Cause**: VPN not connected or credentials invalid
**Solution**:
- Verify VPN connection
- Check credentials in config/api_credentials.json
- System will use simulated data as fallback

#### 4. WebSocket Disconnections
**Cause**: Network issues or server restart
**Solution**: WebSockets auto-reconnect every 5 seconds

#### 5. Database Locked Error
**Cause**: SQLite concurrent access
**Solution**: 
- WAL mode is enabled by default
- Check logs/sqlite_locks.log
- Restart Django if persistent

### Debug Mode
Enable detailed logging:
```python
# In settings.py
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'level': 'DEBUG',
        },
    },
    'loggers': {
        'abay_optimization': {
            'handlers': ['console'],
            'level': 'DEBUG',
        },
    },
}
```

### Log Files
- Django logs: `django_backend/django.log`
- SQLite locks: `django_backend/logs/sqlite_locks.log`
- Optimization results: `django_backend/optimization_outputs/`
- LP problem files: `output/`

## Development

### Running Tests
```bash
# Run all tests
python manage.py test

# Run specific test
python manage.py test optimization_api.tests.TestOptimization

# Test hybrid optimizer
python test_hybrid_optimizer.py

# Test with coverage
coverage run --source='.' manage.py test
coverage report
```

### Code Style
Follow PEP 8 guidelines:
```bash
# Check code style
flake8 abay_optimization/

# Auto-format code
black abay_optimization/
```

## Documentation


### API Documentation
```bash
# Generate API docs
python manage.py generateschema > openapi-schema.yml
```

### Further Help
- GitHub Issues: Report bugs and request features
- Email: support@your-org.com
- Documentation: See `/docs` directory

## License

[Your License Here]

## Contributors

- PCWA Engineering Team
- [Your Name]

---

**Last Updated**: February 2026
**Version**: 0.2