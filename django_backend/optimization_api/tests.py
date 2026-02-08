import pytest
from django.urls import reverse
from rest_framework.test import APIClient
from django.contrib.auth.models import User
import pandas as pd
from types import SimpleNamespace

from .models import PIDatum, OptimizationRun
import sys

pytestmark = pytest.mark.django_db


def test_run_optimization_flow(settings, monkeypatch):
    """Ensure optimization endpoints respond and track run completion."""
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_BROKER_URL = 'memory://'
    settings.CELERY_RESULT_BACKEND = 'cache+memory://'

    # Stub Celery delay to avoid needing a broker
    monkeypatch.setattr(
        'optimization_api.views.run_optimization_task.delay',
        lambda run_id, optimization_ui_params=None: SimpleNamespace(id='fake-task', ready=lambda: True),
    )

    client = APIClient()
    resp = client.post(reverse('run_optimization'), {}, format='json')
    assert resp.status_code == 201
    run_id = resp.data['run_id']
    task_id = resp.data['task_id']

    # Simulate worker completing the run
    run = OptimizationRun.objects.get(id=run_id)
    run.status = 'completed'
    run.progress_percentage = 100
    run.progress_message = 'done'
    run.save()

    status_resp = client.get(reverse('optimization_status', args=[task_id]))
    assert status_resp.status_code == 200
    assert status_resp.data['status'] == 'completed'
    assert status_resp.data['progress_percentage'] == 100

    results_resp = client.get(reverse('optimization_results', args=[run_id]))
    assert results_resp.status_code in (200, 404)


def test_refresh_pi_data_and_latest_results(tmp_path, settings, monkeypatch):
    settings.CELERY_TASK_ALWAYS_EAGER = True
    user = User.objects.create(username='test')
    client = APIClient()
    client.force_authenticate(user=user)

    # Prepare mock PI data
    df = pd.DataFrame({
        'Afterbay_Elevation': [1.0],
        'Afterbay_Elevation_Setpoint': [2.0],
        'Oxbow_Power': [3.0],
        'OXPH_ADS': [3.5],
        'R4_Flow': [10.0],
        'R30_Flow': [11.0],
        'R20_Flow': [12.0],
        'R5L_Flow': [13.0],
        'R26_Flow': [14.0],
        'MFP_Total_Gen_GEN_MDFK_and_RA': [15.0],
        'CCS_Mode': [1.0],
    }, index=pd.DatetimeIndex([pd.Timestamp('2024-01-01T00:00:00Z')]))

    def fake_fetch():
        return None, df

    # Stub scipy to allow importing data_fetcher
    monkeypatch.setitem(sys.modules, 'scipy', SimpleNamespace(stats=None))
    from abay_opt import data_fetcher
    monkeypatch.setattr(data_fetcher, 'get_historical_and_current_data', fake_fetch)

    resp = client.post(reverse('refresh_pi_data'))
    assert resp.status_code == 200
    assert PIDatum.objects.count() == 1
    datum = PIDatum.objects.first()
    assert datum.r4_flow_cfs == 10.0
    assert datum.oxph_setpoint_mw == 3.5

    # Create a run with CSV file
    csv_df = pd.DataFrame({
        'ABAY_ft': [4.0],
        'OXPH_generation_MW': [5.0],
        'FLOAT_FT': [6.0]
    }, index=pd.DatetimeIndex([pd.Timestamp('2024-01-01T00:00:00Z')]))
    csv_path = tmp_path / 'run.csv'
    csv_df.to_csv(csv_path)
    run = OptimizationRun.objects.create(status='completed', result_file_path=str(csv_path), created_by=user)

    latest_resp = client.get(reverse('latest_optimization_results'))
    assert latest_resp.status_code == 200
    chart = latest_resp.data['chart_data']
    assert chart['elevation']['actual'][0] == 1.0
    assert chart['elevation']['optimized'][0] == 4.0
