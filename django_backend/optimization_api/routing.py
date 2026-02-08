# django_backend/optimization_api/routing.py

from django.urls import re_path
from . import consumers  # Import from consumers module

# WebSocket URL patterns
websocket_urlpatterns = [
    # WebSocket endpoint for real-time alerts: ws://localhost:8000/ws/alerts/
    re_path(r'ws/alerts/$', consumers.AlertConsumer.as_asgi()),
]