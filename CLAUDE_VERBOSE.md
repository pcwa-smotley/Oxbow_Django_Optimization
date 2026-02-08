# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview
This is the ABAY Reservoir Optimization system - a Django-based web application for optimizing water reservoir operations at the Afterbay (ABAY) facility. The system integrates real-time monitoring, predictive optimization, alert management, and PI System integration for approximately 8 users.

## Key Commands

### Development Setup
```bash
# Install dependencies
pip install -r requirements.txt

# Database setup (from django_backend directory)
cd django_backend
python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser  # Optional for admin access

# Run development server
python manage.py runserver
```

### Running the Full System
The system requires multiple processes running simultaneously:
```bash
# Terminal 1: Django server
cd django_backend
python manage.py runserver

# Terminal 2: Alert monitoring service (if working with alerts)
cd django_backend
python manage.py monitor_alerts --interval 60

# Terminal 3: Celery worker (if using background tasks)
cd django_backend
celery -A django_backend worker -l info

# Terminal 4: Redis server (if not running as service)
redis-server
```

### Testing
```bash
# Run Django tests
cd django_backend
python manage.py test

# Test alert system
python manage.py monitor_alerts --once --test-mode --verbose

# Django shell for interactive testing
python manage.py shell

# Check Django configuration
python manage.py check
```

### Common Development Tasks
```bash
# Create new Django app
python manage.py startapp <app_name>

# Make and apply database migrations
python manage.py makemigrations
python manage.py migrate

# Collect static files (for production)
python manage.py collectstatic

# Database shell
python manage.py dbshell
```

## Architecture Overview

### System Components
1. **Django Backend** (`/django_backend/`) - Web application and API
   - REST API for optimization requests
   - WebSocket support for real-time alerts
   - User authentication and session management
   - Background task processing with Celery

2. **Optimization Engine** (`/abay_opt/`) - Core calculations
   - Linear programming optimization
   - PI System data integration
   - Electricity price fetching (YES Energy)
   - Hydrological calculations

3. **Alert System** - Multi-channel notifications
   - Email, SMS (Twilio), Voice, Browser notifications
   - Category-based thresholds (Flow, Afterbay, Rafting, Generation)
   - Real-time monitoring with configurable intervals

### Key Integration Points
- **PI System**: Real-time operational data (requires VPN/network access)
- **YES Energy API**: Electricity pricing data
- **Twilio**: SMS and voice alerts
- **DreamFlows**: External rafting schedule integration

### Database Design
- SQLite with WAL mode (intentional choice for ~8 users)
- Key models: OptimizationRun, ParameterSet, AlertThreshold, AlertLog
- Session-based authentication with 7-day "Remember Me" option

## Important Context

### Current State
- Optimizer works well and is stable.
- Frontend enhancements need additional work. 
- Backend is the current priority, especially the ability to identify and handle errors in the optimization process
- The linear optimizer is the core of the optimization engine, with data fetching from the PI System being critical for real-time operations

### Design Decisions
- SQLite chosen intentionally for small user base (~8 users max)
- Focus on reliability over scalability
- All times in Pacific timezone
- User prefers functional UI over complex features
- Test messages should be generic (no fake data)

### Common Issues and Solutions
- **"alertsList is null" error**: Old UI code, can be ignored
- **Optimization in simulation mode**: Normal when PI System unavailable
- **SQLite locks**: WAL mode helps, monitor with monitor_sqlite.py
- **WebSocket reconnection**: Auto-reconnects every 5 seconds
