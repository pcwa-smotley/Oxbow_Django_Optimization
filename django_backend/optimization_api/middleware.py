# django_backend/optimization_api/middleware.py

from django.shortcuts import redirect
from django.urls import reverse
from django.conf import settings
from django.utils import timezone
import logging


logger = logging.getLogger(__name__)


class LoginRequiredMiddleware:
    """
    Middleware that requires a user to be authenticated to view any page
    other than LOGIN_EXEMPT_URLS. Also tracks last activity for analytics.
    """

    def __init__(self, get_response):
        self.get_response = get_response

        # URLs that don't require authentication
        self.exempt_urls = [
            reverse('login'),
            '/admin/login/',
            '/api/auth-status/',  # Allow checking auth status
        ]

        # Add static and media URLs
        if hasattr(settings, 'STATIC_URL'):
            self.exempt_urls.append(settings.STATIC_URL)
        if hasattr(settings, 'MEDIA_URL'):
            self.exempt_urls.append(settings.MEDIA_URL)

    def __call__(self, request):
        # Check if user is authenticated
        if not request.user.is_authenticated:
            path = request.path_info

            # Check if the current path is exempt
            exempt = any(path.startswith(url) for url in self.exempt_urls)

            if not exempt:
                # Store the URL the user was trying to access
                login_url = f"{reverse('login')}?next={path}"
                return redirect(login_url)
        else:
            # User is authenticated - track activity
            self.track_user_activity(request)

        response = self.get_response(request)
        return response

    def track_user_activity(self, request):
        """Track user's last activity for analytics and security"""
        try:
            # Only track meaningful requests (not static files, ajax polls, etc.)
            if (not request.path.startswith('/static/') and
                    not request.path.startswith('/api/auth-status/') and
                    request.method in ['GET', 'POST'] and
                    hasattr(request.user, 'optimization_profile')):

                profile = request.user.optimization_profile
                profile.last_activity = timezone.now()

                # Update last login if this is their first request of the session
                if not request.session.get('activity_tracked'):
                    profile.last_login = timezone.now()
                    request.session['activity_tracked'] = True
                    logger.info(f"User {request.user.username} session started")

                profile.save(update_fields=['last_activity', 'last_login'])

        except Exception as e:
            # Don't break the request if tracking fails
            logger.error(f"Error tracking user activity: {e}")


class UpdateLastActivityMiddleware:
    """Middleware to track user activity without enforcing timeouts"""

    def __init__(self, get_response):
        self.get_response = get_response
        # Paths that shouldn't update activity (to avoid too many DB writes)
        self.exclude_paths = [
            '/api/auth-status/',
            '/api/activity/',
            '/static/',
            '/media/',
            '/__debug__/',
        ]

    def __call__(self, request):
        # Update last activity for authenticated users
        # Better way: use request.user.is_authenticated instead of isinstance check
        if request.user.is_authenticated:
            # Skip activity update for excluded paths
            if not any(request.path.startswith(path) for path in self.exclude_paths):
                try:
                    # Only update if it's been more than 5 minutes since last update
                    profile = request.user.optimization_profile
                    if profile.last_activity is None or \
                            (timezone.now() - profile.last_activity).total_seconds() > 300:
                        profile.last_activity = timezone.now()
                        profile.save(update_fields=['last_activity'])
                except Exception:
                    # Don't break the request if activity tracking fails
                    pass

        response = self.get_response(request)
        return response