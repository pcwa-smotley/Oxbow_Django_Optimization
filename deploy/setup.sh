#!/bin/bash
# ABAY Optimization Dashboard — First-Time Server Setup
# Run as root or with sudo: sudo bash deploy/setup.sh
#
# Prerequisites:
#   - Ubuntu 22.04+ server
#   - Git clone of the repo at /home/abay/abay-app
#   - .env file configured (copy from deploy/.env.example)
#   - API credentials in abay_opt/config/

set -e

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DEPLOY_DIR="$APP_DIR/deploy"
DJANGO_DIR="$APP_DIR/django_backend"

echo "=== ABAY First-Time Setup ==="
echo "App directory: $APP_DIR"

# 1. System packages
echo ""
echo "--- Installing system packages ---"
apt update
apt install -y python3.12 python3.12-venv python3.12-dev \
    redis-server nginx git build-essential libffi-dev libssl-dev

# 2. Enable Redis
echo ""
echo "--- Enabling Redis ---"
systemctl enable redis-server
systemctl start redis-server

# 3. Python venv + dependencies
echo ""
echo "--- Setting up Python environment ---"
if [ ! -d "$APP_DIR/venv" ]; then
    python3.12 -m venv "$APP_DIR/venv"
fi
source "$APP_DIR/venv/bin/activate"
pip install --upgrade pip
pip install -r "$APP_DIR/requirements.txt"

# 4. Django setup
echo ""
echo "--- Django setup ---"
cd "$DJANGO_DIR"
mkdir -p logs optimization_outputs
python manage.py migrate --noinput
python manage.py collectstatic --noinput

# 5. Install systemd services
echo ""
echo "--- Installing systemd services ---"
for svc in abay-daphne abay-celery abay-celerybeat abay-alerts; do
    cp "$DEPLOY_DIR/$svc.service" /etc/systemd/system/
    echo "  Installed $svc.service"
done

systemctl daemon-reload
for svc in abay-daphne abay-celery abay-celerybeat abay-alerts; do
    systemctl enable $svc
    systemctl start $svc
    echo "  Started $svc"
done

# 6. Install nginx config
echo ""
echo "--- Configuring nginx ---"
cp "$DEPLOY_DIR/nginx-abay.conf" /etc/nginx/sites-available/abay
ln -sf /etc/nginx/sites-available/abay /etc/nginx/sites-enabled/abay
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl restart nginx

# 7. Firewall
echo ""
echo "--- Configuring firewall ---"
ufw allow 'Nginx Full'
ufw allow OpenSSH
echo "  (Run 'ufw enable' manually if not already enabled)"

# 8. Status check
echo ""
echo "--- Service Status ---"
for svc in redis-server nginx abay-daphne abay-celery abay-celerybeat abay-alerts; do
    status=$(systemctl is-active $svc 2>/dev/null || echo "inactive")
    echo "  $svc: $status"
done

echo ""
echo "=== Setup complete ==="
echo ""
echo "Next steps:"
echo "  1. Edit /etc/nginx/sites-available/abay — replace YOUR_DOMAIN_OR_IP"
echo "  2. For HTTPS: sudo apt install certbot python3-certbot-nginx && sudo certbot --nginx"
echo "  3. Create a Django superuser: cd $DJANGO_DIR && python manage.py createsuperuser"
echo "  4. Visit http://YOUR_SERVER_IP/ to verify"
