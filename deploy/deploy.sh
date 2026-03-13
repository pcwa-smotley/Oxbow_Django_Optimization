#!/bin/bash
# ABAY Optimization Dashboard — Deployment / Update Script
# Run from the project root: bash deploy/deploy.sh
#
# First-time setup:
#   1. Copy deploy/.env.example to .env and fill in values
#   2. Copy API credentials to abay_opt/config/
#   3. Run: bash deploy/setup.sh  (installs services, nginx, etc.)
#
# Subsequent updates:
#   Just run: bash deploy/deploy.sh

set -e

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV="$APP_DIR/venv/bin"
DJANGO_DIR="$APP_DIR/django_backend"

echo "=== ABAY Deployment ==="
echo "App directory: $APP_DIR"

# Activate venv
source "$VENV/activate"

# Pull latest code
echo ""
echo "--- Pulling latest code ---"
cd "$APP_DIR"
git pull

# Install/update dependencies
echo ""
echo "--- Installing dependencies ---"
pip install -q -r requirements.txt

# Run migrations
echo ""
echo "--- Running migrations ---"
cd "$DJANGO_DIR"
python manage.py migrate --noinput

# Collect static files
echo ""
echo "--- Collecting static files ---"
python manage.py collectstatic --noinput

# Ensure logs directory exists
mkdir -p "$DJANGO_DIR/logs"

# Restart services
echo ""
echo "--- Restarting services ---"
sudo systemctl restart abay-daphne
sudo systemctl restart abay-celery
sudo systemctl restart abay-celerybeat
sudo systemctl restart abay-alerts

echo ""
echo "--- Checking service status ---"
for svc in abay-daphne abay-celery abay-celerybeat abay-alerts; do
    status=$(systemctl is-active $svc 2>/dev/null || echo "inactive")
    echo "  $svc: $status"
done

echo ""
echo "=== Deployment complete ==="
