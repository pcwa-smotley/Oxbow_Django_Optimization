// django_backend/static/js/session-manager.js - Simple version without timeout

class SessionManager {
    constructor() {
        this.lastCheckTime = Date.now();
        this.checkInterval = 60 * 60 * 1000; // Check every hour
        this.init();
    }

    init() {
        // Check session when page becomes visible
        document.addEventListener('visibilitychange', () => {
            if (!document.hidden) {
                this.checkSessionIfNeeded();
            }
        });

        // Check session periodically (every hour)
        setInterval(() => this.checkSession(), this.checkInterval);

        // Check session on page load
        this.checkSession();
    }

    checkSessionIfNeeded() {
        // Only check if it's been more than 5 minutes since last check
        const now = Date.now();
        if (now - this.lastCheckTime > 5 * 60 * 1000) {
            this.checkSession();
        }
    }

    async checkSession() {
        try {
            const response = await fetch('/api/auth-status/', {
                credentials: 'include',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest'
                }
            });

            if (!response.ok) {
                throw new Error('Session check failed');
            }

            const data = await response.json();

            if (!data.authenticated) {
                // Session expired or user logged out elsewhere
                this.handleSessionExpired();
            } else {
                // Session is valid
                this.lastCheckTime = Date.now();
                this.updateLastSeen();
            }
        } catch (error) {
            console.error('Session check error:', error);
            // Don't redirect on network errors - user might be offline temporarily
        }
    }

    handleSessionExpired() {
        // Store current location
        const currentPath = window.location.pathname + window.location.search;

        // Show a brief message
        const message = document.createElement('div');
        message.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            background: #e74c3c;
            color: white;
            padding: 15px 20px;
            border-radius: 5px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.2);
            z-index: 100000;
        `;
        message.textContent = 'Your session has expired. Redirecting to login...';
        document.body.appendChild(message);

        // Redirect after 2 seconds
        setTimeout(() => {
            window.location.href = `/login/?next=${encodeURIComponent(currentPath)}`;
        }, 2000);
    }

    updateLastSeen() {
        // Update the last seen indicator if it exists
        const lastSeenElement = document.getElementById('last-activity');
        if (lastSeenElement) {
            const now = new Date();
            lastSeenElement.textContent = now.toLocaleTimeString();
        }
    }

    // Manual logout function
    logout() {
        if (confirm('Are you sure you want to logout?')) {
            window.location.href = '/logout/';
        }
    }
}

// Initialize session manager
const sessionManager = new SessionManager();

// Enhanced API call function with better error handling
async function apiCall(url, options = {}) {
    try {
        const defaultOptions = {
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken(),
                'X-Requested-With': 'XMLHttpRequest'
            },
            credentials: 'include'
        };

        const response = await fetch(url, { ...defaultOptions, ...options });

        // Handle authentication errors
        if (response.status === 401 || response.status === 403) {
            // Check if we're really logged out
            const authCheck = await fetch('/api/auth-status/', {
                credentials: 'include',
                headers: { 'X-Requested-With': 'XMLHttpRequest' }
            });

            if (authCheck.ok) {
                const authData = await authCheck.json();
                if (!authData.authenticated) {
                    sessionManager.handleSessionExpired();
                    return;
                }
            }

            // If we're still authenticated, it's a permission issue
            throw new Error('Permission denied');
        }

        if (!response.ok) {
            throw new Error(`API call failed: ${response.status} ${response.statusText}`);
        }

        return await response.json();
    } catch (error) {
        console.error('API call error:', error);
        throw error;
    }
}

// CSRF token helper
function getCsrfToken() {
    const name = 'csrftoken';
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

// Add logout confirmation to logout links
document.addEventListener('DOMContentLoaded', function() {
    const logoutLinks = document.querySelectorAll('a[href="/logout/"]');
    logoutLinks.forEach(link => {
        link.addEventListener('click', function(e) {
            e.preventDefault();
            sessionManager.logout();
        });
    });
});