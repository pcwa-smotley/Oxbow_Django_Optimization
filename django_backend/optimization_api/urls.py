# django_backend/optimization_api/urls.py

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views
from . import auth_views
from .auth_views import RegistrationDisabledView, activity_ping, EnhancedAlertsView, get_alert_history, test_alert

router = DefaultRouter()
router.register(r'optimization-runs', views.OptimizationRunViewSet)
router.register(r'parameters', views.ParameterSetViewSet)

urlpatterns = [
    path('optimization-runs/save-edited/', views.SaveEditedOptimizationView.as_view(), name='save_edited_optimization'),
    path('optimization-runs/apply-bias/', views.ApplyBiasView.as_view(), name='apply_bias'),
    path('', include(router.urls)),

    # Authentication endpoints
    path('auth-status/', auth_views.auth_status, name='auth_status'),
    path('register/', RegistrationDisabledView.as_view(), name='register'),
    path('user-parameters/', auth_views.ParametersView.as_view(), name='user_parameters'),
    path('alerts/', EnhancedAlertsView.as_view(), name='alerts'),
    path('alerts/<int:alert_id>/', EnhancedAlertsView.as_view(), name='alert_detail'),
    path('alerts/history/', get_alert_history, name='alert_history'),
    path('alerts/<int:alert_id>/test/', test_alert, name='test_alert'),
    path('test-notifications/', auth_views.test_notifications, name='test_notifications'),

    # Optimization endpoints - FIXED NAMES TO MATCH FRONTEND
    path('run-optimization/', views.RunOptimizationView.as_view(), name='run_optimization'),  # Changed from 'optimize/'
    path('optimization-settings/', views.OptimizationSettingsView.as_view(), name='optimization-settings'),
    # Removed 'api/' prefix
    path('optimization-status/<str:task_id>/', views.OptimizationStatusView.as_view(), name='optimization_status'),
    # Changed from 'status/'
    path('optimization-results/<int:run_id>/', views.OptimizationResultsView.as_view(), name='optimization_results'),
    path('optimization-results/latest/', views.LatestOptimizationResultsView.as_view(),
         name='latest_optimization_results'),
    path('refresh-pi-data/', views.RefreshPIDataView.as_view(), name='refresh_pi_data'),
    path('optimization-diagnostics/<int:run_id>/', views.OptimizationDiagnosticsView.as_view(),
         name='optimization-diagnostics'),  # Removed 'api/optimization/'

    # Other endpoints
    path('historical-data/', views.HistoricalDataView.as_view(), name='historical_data'),
    path('recalculate/', views.RecalculateElevationView.as_view(), name='recalculate'),
    path('current-state/', views.CurrentStateView.as_view(), name='current_state'),

    # CAISO DA Awards
    path('caiso-da-awards/', views.CAISODAAwardsView.as_view(), name='caiso_da_awards'),

    # Price data endpoints
    path('electricity-prices/', views.ElectricityPriceView.as_view(), name='electricity_prices'),
    path('price-analysis/', views.PriceAnalysisView.as_view(), name='price_analysis'),
    path('price-task-status/<str:task_id>/', views.PriceTaskStatusView.as_view(), name='price_task_status'),
    path('activity/', activity_ping, name='activity_ping'),

    # Rafting/Recreation endpoints
    path('rafting-times/', views.RaftingTimesView.as_view(), name='rafting_times'),
    path('ramp-calculator/', views.RampCalculatorView.as_view(), name='ramp_calculator'),
    path('rafting-config/', views.RaftingConfigView.as_view(), name='rafting_config'),

    # System health and dashboard
    path('health/', views.health_check, name='health'),
    path('dashboard-data/', views.dashboard_data, name='dashboard_data'),
]