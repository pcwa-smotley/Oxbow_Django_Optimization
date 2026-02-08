// django_backend/static/js/auth-alerts.js - Updated without registration

// Global variables for authentication and alerts
let currentUser = null;
let websocket = null;
let alertsEnabled = true;
let activeAlerts = [];

// Authentication Management (No Registration)
class AuthManager {
    constructor() {
        this.checkAuthStatus();
    }

    async checkAuthStatus() {
        try {
            const response = await fetch('/api/auth-status/');
            const data = await response.json();

            if (data.authenticated) {
                this.setCurrentUser(data.user);
                await this.loadUserProfile();
                this.initializeWebSocket();
            } else {
                // Redirect to login page if not authenticated
                if (!window.location.pathname.includes('/login')) {
                    window.location.href = '/login/';
                }
            }
        } catch (error) {
            console.error('Error checking auth status:', error);
        }
    }

    setCurrentUser(user) {
        currentUser = user;
        this.updateUI();
        console.log('User authenticated:', user.username);
    }

    updateUI() {
        // Update header to show user info
        const userMenu = document.querySelector('.user-menu');
        if (userMenu && currentUser) {
            userMenu.innerHTML = `
                <span>Welcome, ${currentUser.first_name || currentUser.username}</span>
                <a href="/profile/" class="btn btn-small">Profile</a>
                <a href="/logout/" class="btn btn-small btn-secondary">Logout</a>
            `;
        }

        // Enable authenticated features
        this.enableAuthenticatedFeatures();
    }

    enableAuthenticatedFeatures() {
        // Enable parameter saving
        const saveParamBtn = document.querySelector('[onclick="saveParameters()"]');
        if (saveParamBtn) {
            saveParamBtn.disabled = false;
        }

        // Show alerts tab
        const alertsTab = document.querySelector('[onclick*="alerts"]');
        if (alertsTab) {
            alertsTab.style.display = 'block';
        }
    }

    async loadUserProfile() {
        try {
            const response = await apiCall('/api/profile/');
            if (response.status === 'success') {
                const profile = response.user.profile;

                // Apply user preferences
                if (profile.dark_mode) {
                    document.body.classList.add('dark-mode');
                }

                // Set default tab
                if (profile.default_tab && typeof switchTab === 'function') {
                    setTimeout(() => switchTab(profile.default_tab, null), 100);
                }

                // Set auto-refresh interval
                if (profile.refresh_interval && typeof startAutoRefresh === 'function') {
                    startAutoRefresh(profile.refresh_interval * 1000);
                }

                alertsEnabled = profile.browser_notifications;

                // Request notification permission if enabled
                if (alertsEnabled && 'Notification' in window) {
                    Notification.requestPermission();
                }
            }
        } catch (error) {
            console.error('Error loading user profile:', error);
        }
    }

    initializeWebSocket() {
        if (!currentUser) return;

        try {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsUrl = `${protocol}//${window.location.host}/ws/alerts/`;

            websocket = new WebSocket(wsUrl);

            websocket.onopen = () => {
                console.log('WebSocket connected for alerts');
                showNotification('Real-time alerts connected', 'success');
            };

            websocket.onmessage = (event) => {
                this.handleWebSocketMessage(JSON.parse(event.data));
            };

            websocket.onclose = () => {
                console.log('WebSocket disconnected');
                // Attempt to reconnect after 5 seconds
                setTimeout(() => {
                    if (currentUser) {
                        this.initializeWebSocket();
                    }
                }, 5000);
            };

            websocket.onerror = (error) => {
                console.error('WebSocket error:', error);
            };

        } catch (error) {
            console.error('Error initializing WebSocket:', error);
        }
    }

    handleWebSocketMessage(data) {
        switch (data.type) {
            case 'connection_established':
                console.log('WebSocket connection confirmed');
                break;

            case 'alert_notification':
                this.handleAlert(data.alert);
                break;

            case 'system_status':
                this.updateSystemStatus(data.data);
                break;

            case 'pong':
                // Keep-alive response
                break;

            default:
                console.log('Unknown WebSocket message type:', data.type);
        }
    }

    handleAlert(alert) {
        console.log('Received alert:', alert);

        // Add to active alerts
        activeAlerts.unshift(alert);

        // Show browser notification if enabled
        if (alertsEnabled && 'Notification' in window && Notification.permission === 'granted') {
            this.showBrowserNotification(alert);
        }

        // Show in-app notification
        this.showInAppAlert(alert);

        // Update alerts panel if visible
        this.updateAlertsPanel();
    }

    showBrowserNotification(alert) {
        const notification = new Notification(`ABAY Alert: ${alert.name}`, {
            body: alert.message,
            icon: '/static/img/abay-icon.png',
            tag: `alert-${alert.id}`,
            requireInteraction: alert.severity === 'critical'
        });

        notification.onclick = () => {
            window.focus();
            if (typeof switchTab === 'function') {
                switchTab('alerts', null);
            }
            notification.close();
        };

        // Auto-close after 10 seconds for non-critical alerts
        if (alert.severity !== 'critical') {
            setTimeout(() => notification.close(), 10000);
        }
    }

    showInAppAlert(alert) {
        const severityIcons = {
            critical: '<svg width="20" height="20" viewBox="0 0 20 20" fill="none"><circle cx="10" cy="10" r="9" stroke="currentColor" stroke-width="2"/><line x1="10" y1="5" x2="10" y2="11" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><circle cx="10" cy="14.5" r="1.2" fill="currentColor"/></svg>',
            warning: '<svg width="20" height="20" viewBox="0 0 20 20" fill="none"><path d="M10 2L19 18H1L10 2Z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/><line x1="10" y1="8" x2="10" y2="13" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/><circle cx="10" cy="15.5" r="1" fill="currentColor"/></svg>',
            info: '<svg width="20" height="20" viewBox="0 0 20 20" fill="none"><circle cx="10" cy="10" r="9" stroke="currentColor" stroke-width="1.5"/><circle cx="10" cy="6.5" r="1.2" fill="currentColor"/><line x1="10" y1="9" x2="10" y2="15" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>'
        };

        const alertElement = document.createElement('div');
        alertElement.className = `alert-notification alert-${alert.severity}`;
        alertElement.dataset.alertId = alert.id;
        alertElement.innerHTML = `
            <div class="alert-icon">${severityIcons[alert.severity] || severityIcons.info}</div>
            <div class="alert-body">
                <div class="alert-header">
                    <strong>${alert.name}</strong>
                    <span class="alert-time">${new Date(alert.timestamp).toLocaleTimeString()}</span>
                </div>
                <div class="alert-message">${alert.message}</div>
                <div class="alert-actions">
                    <button onclick="acknowledgeAlert(${alert.id})" class="btn-alert-ack">Acknowledge</button>
                    <button onclick="if(typeof switchTab==='function') switchTab('dashboard',null)" class="btn-alert-view">View in Chart</button>
                    <button onclick="dismissAlertToast(this)" class="btn-alert-close">&times;</button>
                </div>
            </div>
        `;

        // Add to alerts container
        let alertsContainer = document.getElementById('alertsContainer');
        if (!alertsContainer) {
            alertsContainer = document.createElement('div');
            alertsContainer.id = 'alertsContainer';
            alertsContainer.className = 'alerts-container';
            document.body.appendChild(alertsContainer);
        }

        alertsContainer.appendChild(alertElement);

        // Enforce max 3 visible, show overflow badge
        this.enforceAlertStack();

        // Audio chime for critical alerts
        if (alert.severity === 'critical') {
            this.playAlertChime();
        }

        // Auto-remove after 30s for info, 60s for warning
        const autoRemoveMs = alert.severity === 'info' ? 30000 : alert.severity === 'warning' ? 60000 : 0;
        if (autoRemoveMs > 0) {
            setTimeout(() => {
                if (alertElement.parentNode) {
                    alertElement.classList.add('alert-exiting');
                    setTimeout(() => { alertElement.remove(); this.enforceAlertStack(); }, 300);
                }
            }, autoRemoveMs);
        }
    }

    enforceAlertStack() {
        const container = document.getElementById('alertsContainer');
        if (!container) return;
        const alerts = container.querySelectorAll('.alert-notification');
        let overflowBadge = container.querySelector('.alert-overflow-badge');

        if (alerts.length > 3) {
            // Hide alerts beyond 3
            alerts.forEach((el, i) => {
                el.style.display = i < 3 ? '' : 'none';
            });
            const hiddenCount = alerts.length - 3;
            if (!overflowBadge) {
                overflowBadge = document.createElement('div');
                overflowBadge.className = 'alert-overflow-badge';
                container.appendChild(overflowBadge);
            }
            overflowBadge.textContent = `+${hiddenCount} more`;
            overflowBadge.style.display = '';
        } else {
            alerts.forEach(el => { el.style.display = ''; });
            if (overflowBadge) overflowBadge.style.display = 'none';
        }
    }

    playAlertChime() {
        try {
            const ctx = new (window.AudioContext || window.webkitAudioContext)();
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            osc.connect(gain);
            gain.connect(ctx.destination);
            osc.frequency.setValueAtTime(880, ctx.currentTime);
            osc.frequency.setValueAtTime(660, ctx.currentTime + 0.1);
            gain.gain.setValueAtTime(0.3, ctx.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.3);
            osc.start(ctx.currentTime);
            osc.stop(ctx.currentTime + 0.3);
        } catch (e) { /* Audio not available */ }
    }

    updateAlertsPanel() {
        const alertsPanel = document.getElementById('activeAlertsPanel');
        if (alertsPanel) {
            // Update the alerts display
            const alertsHtml = activeAlerts.slice(0, 10).map(alert => `
                <div class="alert-item ${alert.severity}">
                    <span class="alert-name">${alert.name}</span>
                    <span class="alert-time">${new Date(alert.timestamp).toLocaleTimeString()}</span>
                </div>
            `).join('');

            alertsPanel.innerHTML = alertsHtml || '<p>No active alerts</p>';
        }
    }

    updateSystemStatus(status) {
        const statusIndicator = document.querySelector('.status-dot');
        if (statusIndicator) {
            statusIndicator.className = `status-dot status-${status.status}`;
        }
    }
}

// Initialize auth manager
const authManager = new AuthManager();

// Alert acknowledgment
async function acknowledgeAlert(alertId) {
    try {
        if (websocket && websocket.readyState === WebSocket.OPEN) {
            websocket.send(JSON.stringify({
                type: 'acknowledge_alert',
                alert_id: alertId
            }));
        }

        // Remove from UI
        const alertElement = document.querySelector(`[data-alert-id="${alertId}"]`);
        if (alertElement) {
            alertElement.remove();
        }

        showNotification('Alert acknowledged', 'success');
    } catch (error) {
        console.error('Error acknowledging alert:', error);
    }
}

// Dismiss alert toast with exit animation
function dismissAlertToast(btn) {
    const toast = btn.closest('.alert-notification');
    if (toast) {
        toast.classList.add('alert-exiting');
        setTimeout(() => {
            toast.remove();
            if (authManager) authManager.enforceAlertStack();
        }, 300);
    }
}

// Keep WebSocket alive with periodic pings
setInterval(() => {
    if (websocket && websocket.readyState === WebSocket.OPEN) {
        websocket.send(JSON.stringify({ type: 'ping' }));
    }
}, 30000); // Ping every 30 seconds

// Add CSS for alerts
const style = document.createElement('style');
style.textContent = `
.alerts-container {
    position: fixed;
    top: 80px;
    right: 20px;
    width: 380px;
    z-index: 10000;
    display: flex;
    flex-direction: column;
    gap: 10px;
}

.alert-notification {
    display: flex;
    gap: 12px;
    background: rgba(255,255,255,0.97);
    border-radius: 10px;
    box-shadow: 0 8px 32px rgba(0,0,0,0.12);
    padding: 14px 16px;
    animation: alertSlideIn 0.35s cubic-bezier(0.34, 1.56, 0.64, 1);
    border-left: 4px solid #3498db;
    backdrop-filter: blur(8px);
    transition: transform 0.3s ease, opacity 0.3s ease;
}

.alert-notification.alert-exiting {
    transform: translateX(110%);
    opacity: 0;
}

.alert-notification .alert-icon {
    flex-shrink: 0;
    width: 28px;
    height: 28px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 50%;
    padding: 4px;
}

.alert-notification .alert-body {
    flex: 1;
    min-width: 0;
}

.alert-notification.alert-critical {
    border-left-color: #e74c3c;
    box-shadow: 0 8px 32px rgba(231,76,60,0.15);
}
.alert-notification.alert-critical .alert-icon { color: #e74c3c; background: rgba(231,76,60,0.1); }

.alert-notification.alert-warning {
    border-left-color: #f39c12;
    box-shadow: 0 8px 32px rgba(243,156,18,0.12);
}
.alert-notification.alert-warning .alert-icon { color: #f39c12; background: rgba(243,156,18,0.1); }

.alert-notification.alert-info {
    border-left-color: #3498db;
}
.alert-notification.alert-info .alert-icon { color: #3498db; background: rgba(52,152,219,0.1); }

.alert-header {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    margin-bottom: 6px;
}
.alert-header strong { font-size: 13px; }

.alert-time {
    font-size: 11px;
    color: #7f8c8d;
}

.alert-message {
    margin-bottom: 10px;
    color: #34495e;
    font-size: 12px;
    line-height: 1.4;
}

.alert-actions {
    display: flex;
    gap: 8px;
}

.btn-alert-ack, .btn-alert-view {
    padding: 4px 10px;
    background: #3498db;
    color: white;
    border: none;
    border-radius: 5px;
    cursor: pointer;
    font-size: 11px;
    font-weight: 600;
    transition: background 0.2s;
}
.btn-alert-ack:hover { background: #2980b9; }
.btn-alert-view { background: transparent; color: #3498db; border: 1px solid #3498db; }
.btn-alert-view:hover { background: rgba(52,152,219,0.08); }

.btn-alert-close {
    padding: 2px 8px;
    background: transparent;
    border: none;
    border-radius: 4px;
    cursor: pointer;
    font-size: 18px;
    color: #95a5a6;
    line-height: 1;
    transition: color 0.2s;
}
.btn-alert-close:hover { color: #e74c3c; }

.alert-overflow-badge {
    text-align: center;
    padding: 6px 12px;
    background: rgba(255,255,255,0.9);
    border-radius: 8px;
    font-size: 12px;
    font-weight: 600;
    color: #7f8c8d;
    box-shadow: 0 2px 8px rgba(0,0,0,0.08);
}

@keyframes alertSlideIn {
    from { transform: translateX(100%); opacity: 0; }
    to { transform: translateX(0); opacity: 1; }
}

/* Dark mode alert overrides */
[data-theme="dark"] .alert-notification {
    background: rgba(15, 23, 42, 0.92);
    border-left-color: #00d4ff;
    box-shadow: 0 8px 32px rgba(0,0,0,0.4), 0 0 20px rgba(0, 212, 255, 0.08);
    backdrop-filter: blur(16px);
}
[data-theme="dark"] .alert-notification .alert-header strong { color: #e2e8f0; }
[data-theme="dark"] .alert-notification .alert-message { color: #94a3b8; }
[data-theme="dark"] .alert-notification .alert-time { color: #64748b; }

[data-theme="dark"] .alert-notification.alert-critical {
    border-left-color: #ff006e;
    box-shadow: 0 8px 32px rgba(0,0,0,0.4), 0 0 20px rgba(255,0,110,0.15);
}
[data-theme="dark"] .alert-notification.alert-critical .alert-icon { color: #ff006e; background: rgba(255,0,110,0.15); }

[data-theme="dark"] .alert-notification.alert-warning {
    border-left-color: #ffbe0b;
    box-shadow: 0 8px 32px rgba(0,0,0,0.4), 0 0 20px rgba(255,190,11,0.1);
}
[data-theme="dark"] .alert-notification.alert-warning .alert-icon { color: #ffbe0b; background: rgba(255,190,11,0.15); }

[data-theme="dark"] .alert-notification.alert-info .alert-icon { color: #00d4ff; background: rgba(0,212,255,0.12); }

[data-theme="dark"] .btn-alert-ack { background: rgba(0,212,255,0.2); color: #00d4ff; border: 1px solid rgba(0,212,255,0.3); }
[data-theme="dark"] .btn-alert-ack:hover { background: rgba(0,212,255,0.3); }
[data-theme="dark"] .btn-alert-view { color: #00d4ff; border-color: rgba(0,212,255,0.3); }
[data-theme="dark"] .btn-alert-view:hover { background: rgba(0,212,255,0.1); }
[data-theme="dark"] .btn-alert-close { color: #64748b; }
[data-theme="dark"] .btn-alert-close:hover { color: #ff006e; }

[data-theme="dark"] .alert-overflow-badge {
    background: rgba(15, 23, 42, 0.85);
    color: #94a3b8;
    border: 1px solid rgba(0,212,255,0.15);
}

.user-menu {
    display: flex;
    align-items: center;
    gap: 15px;
}

.btn-small {
    padding: 5px 15px;
    font-size: 14px;
}
`;
document.head.appendChild(style);