# django_backend/abay_web/urls.py

from django.contrib import admin
from django.urls import path, include
from django.views.generic import TemplateView
from django.contrib.auth import views as auth_views
from optimization_api.views import dashboard_view, profile_view, logout_confirmation_view
from optimization_api.auth_views import CustomLoginView

urlpatterns = [
    path('admin/', admin.site.urls),

    # Authentication URLs

    path('login/', CustomLoginView.as_view(), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    path('profile/', profile_view, name='profile'),

    # Main dashboard
    path('', dashboard_view, name='dashboard'),

    # API endpoints
    path('api/', include('optimization_api.urls')),
]
