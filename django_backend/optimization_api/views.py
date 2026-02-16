# django_backend/optimization_api/views.py

import os
import sys
import json
import logging
import re
from copy import deepcopy
from datetime import datetime, timedelta, time, date
from pathlib import Path
import pandas as pd
import math, random

from abay_opt import constants as abay_constants
from abay_opt.data_fetcher import get_combined_r4_r30_forecasts
from abay_opt.recalc import recalc_abay_path
from abay_opt.utils import AF_PER_CFS_HOUR

from django.shortcuts import render
from django.conf import settings
from django.http import JsonResponse
from django.utils import timezone  # Add this line
from django.utils.dateparse import parse_datetime
from django.contrib.auth.models import User
from rest_framework import viewsets, status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import action

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import update_session_auth_hash, logout
from django.contrib import messages
from django.views.decorators.http import require_http_methods

from .tasks import run_optimization_task
from .models import (
    OptimizationRun, ParameterSet, OptimizationResult, UserPreferences,
    UserProfile, PIDatum, CAISODAAward, CAISODAAwardSummary,
)
from .serializers import (
    OptimizationRunSerializer,
    ParameterSetSerializer,
    OptimizationResultSerializer
)

logger = logging.getLogger(__name__)

# Global variable to track if optimization modules are loaded
_optimization_modules_loaded = False
_optimization_constants = None


def load_optimization_modules():
    """Dynamically load optimization modules"""
    global _optimization_modules_loaded, _optimization_constants

    if _optimization_modules_loaded:
        return True

    try:
        current_dir = Path(__file__).resolve().parent
        project_root = current_dir.parent.parent
        
        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))

        import abay_opt.constants as constants
        # We might also want to ensure optimizer is importable
        import abay_opt.optimizer

        _optimization_constants = constants
        _optimization_modules_loaded = True
        logger.info("Optimization modules loaded successfully")
        return True

    except ImportError as e:
        logger.error(f"Failed to load optimization modules: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error loading optimization modules: {e}")
        return False


# Replace your ElectricityPriceView with this enhanced version

class ElectricityPriceView(APIView):
    """API endpoint for fetching electricity price data from YES Energy"""

    def get(self, request):
        """Get electricity price data for optimization"""
        try:

            node_id = request.query_params.get('node_id', '20000002064')
            logger.info(f"ElectricityPriceView called with node_id: {node_id}")

            # Check if we should use simulated data
            use_simulated = settings.ABAY_OPTIMIZATION.get('USE_SIMULATED_DATA', False)

            if use_simulated:
                logger.info("USE_SIMULATED_DATA is True - returning simulated price data")
                return self._get_simulated_price_data(node_id)

            # Dynamic import of YES Energy module
            current_dir = Path(__file__).resolve().parent
            project_root = current_dir.parent.parent
            abay_opt_path = project_root / 'abay_opt'

            if str(project_root) not in sys.path:
                sys.path.insert(0, str(project_root))

            # Import YES Energy module
            try:
                import abay_opt.yes_energy_grab as yes_energy
                logger.info("Successfully imported YES Energy module")

                # Fetch real price data
                price_data_df = yes_energy.get_current_electricity_prices(
                    node_id=node_id,
                    config_file=str(project_root / 'abay_opt' / 'config')
                )

                if price_data_df.empty:
                    logger.warning("YES Energy API returned empty data, using simulation")
                    return self._get_simulated_price_data(node_id)

                # Convert DataFrame to JSON-serializable format
                price_data = []
                for idx, row in price_data_df.iterrows():
                    price_data.append({
                        'timestamp': idx.isoformat(),
                        'day_ahead_price': float(row.get('Day_Ahead_Price', 0)) if pd.notna(
                            row.get('Day_Ahead_Price')) else None,
                        'real_time_price': float(row.get('Real_Time_Price', 0)) if pd.notna(
                            row.get('Real_Time_Price')) else None,
                        'fifteen_min_price': float(row.get('Fifteen_Min_Price', 0)) if pd.notna(
                            row.get('Fifteen_Min_Price')) else None,
                    })

                # Get price statistics
                stats = yes_energy.get_price_statistics(price_data_df)

                return Response({
                    'status': 'success',
                    'node_id': node_id,
                    'data_source': 'yes_energy_api',
                    'data_count': len(price_data),
                    'price_data': price_data,
                    'statistics': stats,
                    'data_range': {
                        'start': price_data_df.index.min().isoformat() if not price_data_df.empty else None,
                        'end': price_data_df.index.max().isoformat() if not price_data_df.empty else None
                    }
                })

            except ImportError as e:
                logger.warning(f"Could not import YES Energy module: {e}")
                return self._get_simulated_price_data(node_id)

        except Exception as e:
            logger.error(f"Error in ElectricityPriceView: {e}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            return Response({
                'error': 'Failed to fetch electricity prices',
                'detail': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def _get_simulated_price_data(self, node_id):
        """Generate simulated price data when real data is not available"""
        logger.info(f"Generating simulated price data for node {node_id}")

        try:
            now = timezone.now()
            price_data = []

            for i in range(48):  # 48 hours of data
                timestamp = now + timedelta(hours=i)

                # Simulate realistic price patterns
                base_price = 45.0  # Base price in $/MWh
                time_factor = 1.0 + 0.3 * math.sin((timestamp.hour - 6) / 24 * 2 * math.pi)
                volatility = random.uniform(0.8, 1.2)

                day_ahead = base_price * time_factor * volatility
                real_time = day_ahead * random.uniform(0.9, 1.1)
                fifteen_min = real_time * random.uniform(0.95, 1.05)

                price_data.append({
                    'timestamp': timestamp.isoformat(),
                    'day_ahead_price': round(day_ahead, 2),
                    'real_time_price': round(real_time, 2),
                    'fifteen_min_price': round(fifteen_min, 2),
                })

            stats = {
                'Day_Ahead_Price': {
                    'current': price_data[-1]['day_ahead_price'],
                    'min': min(p['day_ahead_price'] for p in price_data),
                    'max': max(p['day_ahead_price'] for p in price_data),
                    'mean': sum(p['day_ahead_price'] for p in price_data) / len(price_data),
                    'count': len(price_data)
                },
                'Real_Time_Price': {
                    'current': price_data[-1]['real_time_price'],
                    'min': min(p['real_time_price'] for p in price_data),
                    'max': max(p['real_time_price'] for p in price_data),
                    'mean': sum(p['real_time_price'] for p in price_data) / len(price_data),
                    'count': len(price_data)
                }
            }

            return Response({
                'status': 'success',
                'node_id': node_id,
                'data_source': 'simulation',
                'data_count': len(price_data),
                'price_data': price_data,
                'statistics': stats,
                'message': 'Using simulated data - YES Energy API not available',
                'fetched_at': timezone.now().isoformat()
            })

        except Exception as e:
            logger.error(f"Error generating simulated price data: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return Response({
                'error': 'Failed to generate simulated price data',
                'detail': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CAISODAAwardsView(APIView):
    """API endpoint for CAISO Day Ahead awards for Middle Fork (MFP1)"""

    def get(self, request):
        """Return stored DA awards for a given trade date.

        Query params:
          - trade_date: ISO date string (default: next delivery day)
          - detail: if "true", include per-resource breakdown from CAISODAAward
        """
        try:
            import pytz
            tz_pt = pytz.timezone('America/Los_Angeles')

            trade_date_str = request.query_params.get('trade_date')
            if trade_date_str:
                trade_dt = date.fromisoformat(trade_date_str)
            else:
                # Default to next delivery day
                now_pt = timezone.now().astimezone(tz_pt)
                trade_dt = (now_pt + timedelta(days=1)).date() if now_pt.hour >= 13 else now_pt.date()

            summaries = CAISODAAwardSummary.objects.filter(trade_date=trade_dt).order_by('interval_start_utc')
            has_awards = summaries.exists()

            hourly = []
            for s in summaries:
                hourly.append({
                    'interval_start_utc': s.interval_start_utc.isoformat(),
                    'total_mw': s.total_mw,
                    'resource_count': s.resource_count,
                })

            response_data = {
                'status': 'success',
                'trade_date': trade_dt.isoformat(),
                'has_awards': has_awards,
                'hours': len(hourly),
                'hourly_data': hourly,
                'fetched_at': summaries.first().fetched_at.isoformat() if has_awards else None,
            }

            # Include per-resource detail when requested
            include_detail = request.query_params.get('detail', '').lower() == 'true'
            if include_detail and has_awards:
                raw_awards = CAISODAAward.objects.filter(
                    trade_date=trade_dt
                ).order_by('interval_start_utc', 'resource')

                resources = sorted(
                    raw_awards.values_list('resource', flat=True).distinct()
                )

                detail_rows = []
                for award in raw_awards:
                    hour_pt = award.interval_start_utc.astimezone(tz_pt)
                    detail_rows.append({
                        'hour_pt': hour_pt.strftime('%I:%M %p'),
                        'hour_utc': award.interval_start_utc.strftime('%H:%M'),
                        'resource': award.resource,
                        'mw': award.mw,
                        'product_type': award.product_type,
                        'schedule_type': award.schedule_type,
                    })

                response_data['resources'] = resources
                response_data['detail'] = detail_rows

            return Response(response_data)

        except Exception as e:
            logger.error(f"Error in CAISODAAwardsView GET: {e}", exc_info=True)
            return Response({
                'error': 'Failed to retrieve DA awards',
                'detail': str(e),
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @staticmethod
    def _fetch_and_store_date(trade_dt, fetch_fn, agg_fn):
        """Fetch DA awards for one trade date, store raw + summary in DB.

        Returns (raw_record_count, summary_records_list, hourly_series_or_none).
        """
        raw_df = fetch_fn(trade_dt)
        if raw_df is None or raw_df.empty:
            return 0, [], None

        # Store raw award records (all resources/schedule types for diagnostics)
        for _, row in raw_df.iterrows():
            try:
                ist = pd.Timestamp(row['intervalStartTime']).to_pydatetime()
                iet = pd.Timestamp(row['intervalEndTime']).to_pydatetime()
                CAISODAAward.objects.update_or_create(
                    trade_date=trade_dt,
                    interval_start_utc=ist,
                    resource=row.get('resource', 'UNKNOWN'),
                    product_type=row.get('productType', 'EN'),
                    defaults={
                        'interval_end_utc': iet,
                        'mw': float(row.get('MW', 0)),
                        'schedule_type': row.get('scheduleType', 'FINAL'),
                    },
                )
            except Exception as row_err:
                logger.warning(f"Skipping raw award row: {row_err}")

        # Aggregate MDFKRL_2_PROJCT CLEARED awards and store summaries
        hourly_series = agg_fn(raw_df)
        summary_records = []
        if hourly_series is not None:
            for ts, mw_val in hourly_series.items():
                CAISODAAwardSummary.objects.update_or_create(
                    trade_date=trade_dt,
                    interval_start_utc=ts.to_pydatetime(),
                    defaults={
                        'total_mw': float(mw_val),
                        'resource_count': 1,  # filtered to MDFKRL_2_PROJCT
                    },
                )
                summary_records.append({
                    'interval_start_utc': ts.isoformat(),
                    'total_mw': float(mw_val),
                })

        return len(raw_df), summary_records, hourly_series

    def post(self, request):
        """Fetch fresh DA awards from CAISO for today AND tomorrow, store in DB."""
        try:
            import pytz
            tz_pt = pytz.timezone('America/Los_Angeles')
            from abay_opt.caiso_da import fetch_mfp1_da_awards, aggregate_hourly_mw

            # If a specific date was requested, fetch only that date
            trade_date_str = request.data.get('trade_date')
            if trade_date_str:
                dates_to_fetch = [date.fromisoformat(trade_date_str)]
            else:
                # Fetch BOTH today and tomorrow
                now_pt = timezone.now().astimezone(tz_pt)
                today = now_pt.date()
                tomorrow = today + timedelta(days=1)
                dates_to_fetch = [today, tomorrow]

            all_summary = []
            total_raw = 0
            dates_with_awards = []

            for trade_dt in dates_to_fetch:
                raw_count, summaries, hourly = self._fetch_and_store_date(
                    trade_dt, fetch_mfp1_da_awards, aggregate_hourly_mw
                )
                total_raw += raw_count
                all_summary.extend(summaries)
                if summaries:
                    dates_with_awards.append(trade_dt.isoformat())
                    logger.info(f"DA awards for {trade_dt}: {len(summaries)} hours, "
                                f"avg={hourly.mean():.1f} MW" if hourly is not None else "")

            if not all_summary:
                return Response({
                    'status': 'success',
                    'trade_dates': [d.isoformat() for d in dates_to_fetch],
                    'has_awards': False,
                    'message': f'No DA awards available for {", ".join(d.isoformat() for d in dates_to_fetch)}.',
                })

            avg_mw = sum(s['total_mw'] for s in all_summary) / len(all_summary) if all_summary else 0

            return Response({
                'status': 'success',
                'trade_dates': [d.isoformat() for d in dates_to_fetch],
                'dates_with_awards': dates_with_awards,
                'has_awards': True,
                'raw_records': total_raw,
                'hours': len(all_summary),
                'hourly_data': all_summary,
                'avg_mw': round(avg_mw, 1),
                'message': f'Fetched {total_raw} raw records. '
                           f'Awards found for: {", ".join(dates_with_awards) or "none"}',
            })

        except Exception as e:
            logger.error(f"Error in CAISODAAwardsView POST: {e}", exc_info=True)
            return Response({
                'error': 'Failed to fetch DA awards from CAISO',
                'detail': str(e),
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class PriceAnalysisView(APIView):
    """API endpoint for electricity price analysis"""
    def get(self, request):
        return Response({'status': 'success', 'message': 'Price analysis placeholder'})


class PriceTaskStatusView(APIView):
    """Check the status of a background price data fetch task"""

    def get(self, request, task_id):
        """Get the current status of a price data fetch task"""
        try:
            from celery.result import AsyncResult

            task_result = AsyncResult(task_id)

            if task_result.state == 'PENDING':
                response_data = {
                    'status': 'pending',
                    'message': 'Price data fetch is queued'
                }
            elif task_result.state == 'PROGRESS':
                response_data = {
                    'status': 'progress',
                    'message': task_result.info.get('status', 'Fetching price data...'),
                    'progress': task_result.info.get('current', 0),
                    'total': task_result.info.get('total', 100)
                }
            elif task_result.state == 'SUCCESS':
                response_data = {
                    'status': 'completed',
                    'result': task_result.result
                }
            elif task_result.state == 'FAILURE':
                response_data = {
                    'status': 'failed',
                    'error': str(task_result.info)
                }
            else:
                response_data = {
                    'status': 'unknown',
                    'state': task_result.state
                }
            
            return Response(response_data)

        except Exception as e:
            logger.error(f"Error checking task status: {e}")
            return Response({
                'error': 'Failed to check task status',
                'detail': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ParameterSetViewSet(viewsets.ModelViewSet):
    queryset = ParameterSet.objects.all()
    serializer_class = ParameterSetSerializer

    def get_queryset(self):
        """Include default parameter sets and user's custom sets"""
        from django.db import models
        queryset = super().get_queryset()
        if self.request.user.is_authenticated:
            queryset = queryset.filter(
                models.Q(is_default=True) |
                models.Q(created_by=self.request.user)
            )
        else:
            queryset = queryset.filter(is_default=True)
        return queryset


class OptimizationRunViewSet(viewsets.ModelViewSet):
    queryset = OptimizationRun.objects.all()
    serializer_class = OptimizationRunSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if self.request.user.is_authenticated:
            return OptimizationRun.objects.filter(created_by=self.request.user).order_by('-created_at')
        return OptimizationRun.objects.none()

    @action(detail=False, methods=['post'], url_path='apply-bias')
    def apply_bias(self, request):
        """Apply bias correction to a run and recalculate"""
        run_id = request.data.get('run_id')
        bias_value = request.data.get('bias_value')
        
        if not run_id or bias_value is None:
            return Response({'error': 'run_id and bias_value are required'}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            run = OptimizationRun.objects.get(pk=run_id, created_by=request.user)
            # Update the run with the new bias
            # This is a placeholder for the actual logic
            # In a real implementation, we might trigger a recalculation here
            
            # For now, just save it in custom_parameters
            if not run.custom_parameters:
                run.custom_parameters = {}
            run.custom_parameters['bias_value'] = bias_value
            run.save()
            
            return Response({'status': 'success', 'message': 'Bias applied'})
        except OptimizationRun.DoesNotExist:
            return Response({'error': 'Run not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class RunOptimizationView(APIView):
    """API endpoint to start a new optimization run"""

    def post(self, request):
        """Start a new optimization run"""
        try:
            # Check if we should use simulated data
            use_simulated = settings.ABAY_OPTIMIZATION.get('USE_SIMULATED_DATA', False)

            if use_simulated:
                logger.info("USE_SIMULATED_DATA is True - creating simulation run")
                return self._create_simulation_run(request)

            if not load_optimization_modules():
                logger.warning("Optimization modules not available - falling back to simulation")
                return self._create_simulation_run(request)

            logger.info("Running real optimization (USE_SIMULATED_DATA is False)")
            logger.info("=== OPTIMIZATION REQUEST RECEIVED ===")

            # Extract parameters from request
            run_mode = request.data.get('runMode', 'forecast')
            optimizer_type = 'linear'
            forecast_source = request.data.get('forecastSource', 'hydroforecast-short-term')
            historical_date = request.data.get('historicalDate')
            parameter_set_id = request.data.get('parameterSetId')
            custom_parameters = request.data.get('customParameters', {})

            # NEW: Extract optimization UI parameters
            optimization_ui_params = request.data.get('optimizationSettings', {})

            # Validate and structure the UI parameters
            processed_ui_params = self._process_optimization_params(optimization_ui_params)

            # Include UI params in custom_parameters for storage
            if processed_ui_params:
                custom_parameters['optimization_settings'] = processed_ui_params
                
                # Apply constant overrides to top-level custom_parameters so they are picked up by the task
                if 'constants_overrides' in processed_ui_params:
                    custom_parameters.update(processed_ui_params['constants_overrides'])

            # Create optimization run record
            run = OptimizationRun.objects.create(
                run_mode=run_mode,
                optimizer_type=optimizer_type,
                forecast_source=forecast_source,
                historical_start_date=historical_date if historical_date else None,
                parameter_set_id=parameter_set_id if parameter_set_id else None,
                custom_parameters=custom_parameters,
                created_by=request.user if request.user.is_authenticated else None,
                status='pending'
            )

            # Try to start the optimization task
            try:
                # Pass UI params to the task
                task = run_optimization_task.delay(run.id, optimization_ui_params=processed_ui_params)
                run.task_id = task.id
                run.started_at = timezone.now()

                # Only mark as running if the task has not already completed (eager mode)
                if not task.ready():
                    run.status = 'running'
                run.save()

                logger.info(f"Started optimization run {run.id} with task ID {task.id}")
                logger.info(f"Using optimization settings: {processed_ui_params}")

                return Response({
                    'run_id': run.id,
                    'task_id': task.id,
                    'status': 'started',
                    'message': 'Optimization started successfully',
                    'optimization_settings': processed_ui_params  # Return what settings were used
                }, status=status.HTTP_201_CREATED)

            except ImportError:
                logger.warning("Celery not available - running simulation")
                return self._create_simulation_run(request, run)

        except Exception as e:
            logger.error(f"Failed to start optimization: {e}")
            return Response({
                'error': 'Failed to start optimization',
                'detail': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def _process_optimization_params(self, ui_params):
        """Process and validate UI optimization parameters"""
        if not ui_params:
            return None

        processed = {
            'priorities': {},
            'enable_flags': {},
            'custom_weights': {},
            'constants_overrides': {}
        }

        if 'avoidSpill' in ui_params:
            try:
                avoid = bool(ui_params['avoidSpill'])
                processed['priorities']['avoid_spill'] = 1 if avoid else 5
            except (ValueError, TypeError):
                logger.warning(f"Invalid avoidSpill value: {ui_params['avoidSpill']}")

        # Process priorities (ensure they're integers between 1-5)
        priority_mapping = {
            'smoothOperation': 'smooth_operation',
            'midpointElevation': 'midpoint_elevation'
        }

        for ui_key, internal_key in priority_mapping.items():
            if ui_key in ui_params:
                try:
                    value = int(ui_params[ui_key])
                    value = max(1, min(5, value))
                    processed['priorities'][internal_key] = value
                except (ValueError, TypeError):
                    logger.warning(f"Invalid priority value for {ui_key}: {ui_params[ui_key]}")

        # Process enable flags
        if 'enableSmoothing' in ui_params:
            processed['enable_flags']['smoothing_penalty'] = bool(ui_params['enableSmoothing'])

        if 'enableMidpoint' in ui_params:
            processed['enable_flags']['midpoint_elevation_penalty'] = bool(ui_params['enableMidpoint'])

        # Process custom weights (if provided directly)
        if 'smoothingWeight' in ui_params and ui_params.get('enableSmoothing', True):
            try:
                weight = float(ui_params['smoothingWeight'])
                # Clamp to reasonable range
                weight = max(0, min(10000, weight))
                processed['custom_weights']['smoothing_weight'] = weight
            except (ValueError, TypeError):
                logger.warning(f"Invalid smoothing weight: {ui_params['smoothingWeight']}")

        # Process advanced settings
        if 'abayMinElevation' in ui_params:
            try:
                val = float(ui_params['abayMinElevation'])
                processed['constants_overrides']['ABAY_MIN_ELEV_FT'] = val
            except (ValueError, TypeError):
                logger.warning(f"Invalid abayMinElevation: {ui_params['abayMinElevation']}")

        if 'abayMaxElevationBuffer' in ui_params:
            try:
                val = float(ui_params['abayMaxElevationBuffer'])
                processed['constants_overrides']['ABAY_MAX_ELEV_BUFFER_FT'] = val
            except (ValueError, TypeError):
                logger.warning(f"Invalid abayMaxElevationBuffer: {ui_params['abayMaxElevationBuffer']}")

        if 'oxphMinMW' in ui_params:
            try:
                val = float(ui_params['oxphMinMW'])
                processed['constants_overrides']['OXPH_MIN_MW'] = val
            except (ValueError, TypeError):
                logger.warning(f"Invalid oxphMinMW: {ui_params['oxphMinMW']}")

        return processed if any(processed.values()) else None

    def _create_simulation_run(self, request, run=None):
        """Create a simulated optimization run"""
        try:
            if not run:
                # Extract parameters
                run_mode = request.data.get('runMode', 'forecast')
                optimizer_type = 'linear'
                forecast_source = request.data.get('forecastSource', 'hydroforecast-short-term')
                historical_date = request.data.get('historicalDate')
                parameter_set_id = request.data.get('parameterSetId')
                custom_parameters = request.data.get('customParameters', {})
                
                # Create run record
                run = OptimizationRun.objects.create(
                    run_mode=run_mode,
                    optimizer_type=optimizer_type,
                    forecast_source=forecast_source,
                    historical_start_date=historical_date if historical_date else None,
                    parameter_set_id=parameter_set_id if parameter_set_id else None,
                    custom_parameters=custom_parameters,
                    created_by=request.user if request.user.is_authenticated else None,
                    status='pending'
                )

            # Generate simulated results immediately
            run.task_id = f'simulation-{run.id}'
            run.status = 'completed'
            run.progress_percentage = 100
            run.progress_message = 'Simulation completed'
            run.completed_at = timezone.now()
            
            # Generate some fake stats
            run.total_spillage_af = random.uniform(0, 100)
            run.avg_oxph_utilization_pct = random.uniform(80, 100)
            run.peak_elevation_ft = 1175.0 + random.uniform(-1, 1)
            run.min_elevation_ft = 1170.0 + random.uniform(-1, 1)
            run.r_bias_cfs = 0.0
            
            # Create a dummy CSV file for the simulation
            self._generate_simulation_results_file(run)
            
            run.save()

            return Response({
                'run_id': run.id,
                'task_id': run.task_id,
                'status': 'started',
                'message': 'Simulation started successfully',
                'simulation': True
            }, status=status.HTTP_201_CREATED)

        except Exception as e:
            logger.error(f"Error creating simulation run: {e}")
            return Response({
                'error': 'Failed to create simulation run',
                'detail': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def _generate_simulation_results_file(self, run):
        """Generate a dummy results file for simulation"""
        try:
            output_dir = settings.ABAY_OPTIMIZATION.get('OUTPUT_DIR', settings.BASE_DIR / 'optimization_outputs')
            os.makedirs(output_dir, exist_ok=True)
            
            filename = f'simulation_run_{run.id}.csv'
            file_path = Path(output_dir) / filename
            
            # Generate 48 hours of data
            start_time = timezone.now().replace(minute=0, second=0, microsecond=0)
            data = []
            
            for i in range(48):
                ts = start_time + timedelta(hours=i)
                data.append({
                    'timestamp_end': ts.isoformat(),
                    'ABAY_ft': 1173.0 + math.sin(i/10),
                    'OXPH_generation_MW': 4.0 + math.cos(i/10),
                    'R4_Flow': 800 + random.uniform(-50, 50),
                    'R30_Flow': 1200 + random.uniform(-50, 50),
                    'FLOAT_FT': 1173.0,
                    'Mode': 'GEN',
                    'is_forecast': True
                })
                
            df = pd.DataFrame(data)
            df.to_csv(file_path)
            run.result_file_path = str(file_path)
            run.save()
            
        except Exception as e:
            logger.error(f"Failed to generate simulation file: {e}")


class OptimizationSettingsView(APIView):
    """API endpoint for optimization settings"""

    def get(self, request):
        """Get current default optimization settings"""
        try:
            # Load optimization modules to get constants
            if not load_optimization_modules():
                return Response({
                    'error': 'Optimization modules not available'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            global _optimization_constants
            constants = _optimization_constants

            settings = {
                'priorities': {
                    'smoothOperation': constants.PRIORITY_SMOOTH_OPERATION,
                    'midpointElevation': constants.PRIORITY_MIDPOINT_ELEVATION
                },
                'enableFlags': {
                    'spillagePenalty': constants.ENABLE_SPILLAGE_PENALTY,
                    'smoothingPenalty': constants.ENABLE_SMOOTHING_PENALTY,
                    'midpointElevationPenalty': constants.ENABLE_MIDPOINT_ELEVATION_PENALTY,
                    'pwlApproximation': constants.ENABLE_PWL_APPROXIMATION
                },
                'weights': {
                    'spillage': constants.LP_SPILLAGE_PENALTY_WEIGHT,
                    'summerSpillage': constants.LP_SUMMER_SPILLAGE_PENALTY_WEIGHT,
                    'summerMw': constants.LP_SUMMER_MW_REWARD_WEIGHT,
                    'smoothing': constants.LP_BASE_SMOOTHING_PENALTY_WEIGHT,
                    'midpoint': constants.LP_TARGET_ELEV_MIDPOINT_WEIGHT
                },
                'constraints': {
                    'forceOxphAlwaysOn': constants.FORCE_OXPH_ALWAYS_ON,
                    'prohibitSummerSpill': constants.PROHIBIT_SUMMER_SPILL,
                    'spillOnlyAboveMw': constants.SPILL_ONLY_ABOVE_MW
                },
                'ui': {
                    'priorityRange': list(constants.UI_PRIORITY_RANGE) if hasattr(constants, 'UI_PRIORITY_RANGE') else [
                        1, 5],
                    'smoothingWeightRange': list(constants.UI_SMOOTHING_WEIGHT_RANGE) if hasattr(constants,
                                                                                                 'UI_SMOOTHING_WEIGHT_RANGE') else [
                        0, 1000],
                    'allowDisableSmoothing': constants.UI_ALLOW_DISABLE_SMOOTHING if hasattr(constants,
                                                                                             'UI_ALLOW_DISABLE_SMOOTHING') else True
                }
            }

            return Response({
                'status': 'success',
                'settings': settings
            })

        except Exception as e:
            logger.error(f"Error getting optimization settings: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return Response({
                'error': 'Failed to get optimization settings',
                'detail': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class OptimizationStatusView(APIView):
    """Check the status of a running optimization"""

    def get(self, request, task_id):
        """Get the current status of an optimization task"""
        try:
            # Handle simulation tasks
            if task_id.startswith('simulation-'):
                run_id = int(task_id.split('-')[1])
                run = OptimizationRun.objects.get(id=run_id)

                return Response({
                    'run_id': run.id,
                    'task_id': task_id,
                    'status': run.status,
                    'progress_message': run.progress_message,
                    'progress_percentage': run.progress_percentage,
                    'created_at': run.created_at,
                    'started_at': run.started_at,
                    'completed_at': run.completed_at,
                    'task_status': 'SUCCESS' if run.status == 'completed' else 'PROGRESS',
                    'simulation_mode': True,
                    'summary': {
                        'total_spillage_af': run.total_spillage_af,
                        'avg_oxph_utilization_pct': run.avg_oxph_utilization_pct,
                        'peak_elevation_ft': run.peak_elevation_ft,
                        'min_elevation_ft': run.min_elevation_ft,
                        'r_bias_cfs': run.r_bias_cfs,
                    } if run.status == 'completed' else None
                })

            # Get the optimization run
            run = OptimizationRun.objects.get(task_id=task_id)

            response_data = {
                'run_id': run.id,
                'task_id': task_id,
                'status': run.status,
                'progress_message': run.progress_message,
                'progress_percentage': run.progress_percentage,
                'created_at': run.created_at,
                'started_at': run.started_at,
                'completed_at': run.completed_at,
                'error_message': run.error_message,
            }

            # Try to get task status from Celery if available
            try:
                from celery.result import AsyncResult
                task_result = AsyncResult(task_id)

                if task_result.state == 'PENDING':
                    response_data['task_status'] = 'PENDING'
                elif task_result.state in ['PROGRESS', 'STARTED']:
                    response_data['task_status'] = task_result.state

                    # Include Celery task info
                    task_info = task_result.info or {}
                    response_data['task_info'] = task_info

                    # Override progress details with Celery metadata when available
                    status_msg = task_info.get('status')
                    if status_msg:
                        response_data['progress_message'] = status_msg

                    current = task_info.get('current')
                    total = task_info.get('total') or 100
                    if current is not None and total:
                        try:
                            response_data['progress_percentage'] = int(current / total * 100)
                        except Exception:
                            pass
                elif task_result.state == 'SUCCESS':
                    response_data['task_status'] = 'SUCCESS'
                    response_data['task_result'] = task_result.result
                elif task_result.state == 'FAILURE':
                    response_data['task_status'] = 'FAILURE'
                    response_data['task_error'] = str(task_result.info)

            except ImportError:
                response_data['task_status'] = 'SUCCESS' if run.status == 'completed' else 'PROGRESS'

            # Add summary statistics if completed
            if run.status == 'completed':
                response_data['summary'] = {
                    'total_spillage_af': run.total_spillage_af,
                    'avg_oxph_utilization_pct': run.avg_oxph_utilization_pct,
                    'peak_elevation_ft': run.peak_elevation_ft,
                    'min_elevation_ft': run.min_elevation_ft,
                    'r_bias_cfs': run.r_bias_cfs,
                }

            # Include solver status when available
            if run.solver_diagnostics:
                if isinstance(run.solver_diagnostics, dict):
                    response_data['solver_status'] = run.solver_diagnostics.get('status')
                else:
                    response_data['solver_status'] = None

            # Add diagnostics to response if available
            if run.status == 'failed' and run.solver_diagnostics:
                response_data['diagnostics'] = run.solver_diagnostics

                # Add user-friendly interpretation
                response_data['failure_reason'] = self._interpret_failure(run.solver_diagnostics)
                response_data['suggestions'] = self._get_suggestions(run.solver_diagnostics)

            return Response(response_data)

        except OptimizationRun.DoesNotExist:
            return Response({
                'error': 'Optimization run not found'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error getting optimization status: {e}")
            return Response({
                'error': 'Failed to get optimization status',
                'detail': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


    def _interpret_failure(self, diagnostics):
        """Provide user-friendly interpretation of failure"""
        if not diagnostics:
            return "Unknown optimization failure"

        status = diagnostics.get('status', 'Unknown')

        if status == 'Infeasible':
            reasons = []
            if diagnostics.get('infeasible_constraints'):
                constraint_groups = [c.get('group', 'Unknown') for c in diagnostics['infeasible_constraints']]
                reasons.append(f"Conflicting constraints: {', '.join(constraint_groups)}")

            if diagnostics.get('warnings'):
                # Take first 2 warnings
                for warning in diagnostics['warnings'][:2]:
                    reasons.append(warning)

            return "No feasible solution exists. " + " ".join(reasons)

        elif status == 'Unbounded':
            return "The optimization objective can be improved infinitely. This usually indicates incorrect penalty weights."

        else:
            return f"Optimization failed with status: {status}"

    def _get_suggestions(self, diagnostics):
        """Provide actionable suggestions"""
        suggestions = []

        if not diagnostics:
            return suggestions

        status = diagnostics.get('status', 'Unknown')

        if status == 'Infeasible':
            # Check specific warnings
            warnings_str = ' '.join(diagnostics.get('warnings', []))

            if 'summer prep' in warnings_str.lower():
                suggestions.append("Reduce the summer preparation buffer in parameters")
                suggestions.append("Check if the forecast provides enough inflow")

            if 'head loss' in warnings_str.lower():
                suggestions.append("Consider disabling head loss constraints")
                suggestions.append("Check if minimum OXPH MW is too high")

            if 'initial volume' in warnings_str.lower():
                suggestions.append("Initial reservoir level may be too low/high")
                suggestions.append("Adjust elevation buffer constraints")

            # General suggestions
            suggestions.append("Try reducing spillage penalty weight")
            suggestions.append("Verify input flow forecasts are reasonable")

        elif status == 'Unbounded':
            suggestions.append("Increase smoothing penalty weight")
            suggestions.append("Check that spillage penalty is positive")
            suggestions.append("Verify all weights are reasonable values")

        return suggestions[:4]  # Limit to 4 suggestions


class OptimizationDiagnosticsView(APIView):
    """Get detailed diagnostics for debugging optimization failures"""

    def get(self, request, run_id):
        """Get detailed diagnostics and LP file location"""
        try:
            run = OptimizationRun.objects.get(id=run_id)

            response_data = {
                'run_id': run_id,
                'status': run.status,
                'error_message': run.error_message
            }

            if run.solver_diagnostics:
                diagnostics = run.solver_diagnostics

                response_data.update({
                    'diagnostics': diagnostics,
                    'lp_file_path': diagnostics.get('lp_file_path'),
                    'solve_time': diagnostics.get('solve_time'),
                    'interpretation': self._interpret_diagnostics(diagnostics),
                    'technical_details': self._get_technical_details(diagnostics)
                })

            return Response(response_data)

        except OptimizationRun.DoesNotExist:
            return Response({'error': 'Run not found'}, status=404)

    def _get_technical_details(self, diagnostics):
        """Extract technical details for advanced users"""
        details = []

        if diagnostics.get('binding_constraints'):
            details.append(f"{len(diagnostics['binding_constraints'])} binding constraints")

        if diagnostics.get('infeasible_constraints'):
            for constraint in diagnostics['infeasible_constraints']:
                details.append(f"Infeasible: {constraint.get('group')} - {constraint.get('message')}")

        if diagnostics.get('shadow_prices'):
            high_shadow = [(k, v) for k, v in diagnostics['shadow_prices'].items() if abs(v) > 1000]
            if high_shadow:
                details.append(f"{len(high_shadow)} constraints with high shadow prices")

        return details


class HistoricalDataView(APIView):
    """API endpoint for retrieving historical data"""

    def get(self, request):
        """Get historical data for a date range"""
        try:
            start_date = request.query_params.get('start_date')
            end_date = request.query_params.get('end_date')

            if not start_date or not end_date:
                return Response({
                    'error': 'start_date and end_date parameters are required'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Parse dates
            try:
                start_dt = datetime.strptime(start_date, '%Y-%m-%d')
                end_dt = datetime.strptime(end_date, '%Y-%m-%d')
            except ValueError:
                return Response({
                    'error': 'Invalid date format. Use YYYY-MM-DD'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Generate simulated historical data
            historical_data = self._generate_historical_data(start_dt, end_dt)

            return Response({
                'start_date': start_date,
                'end_date': end_date,
                'data': historical_data
            })

        except Exception as e:
            logger.error(f"Error fetching historical data: {e}")
            return Response({
                'error': 'Failed to fetch historical data',
                'detail': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def _generate_historical_data(self, start_date, end_date):
        """Generate simulated historical data"""
        import math
        import random

        data = []
        current_date = start_date

        while current_date <= end_date:
            # Generate hourly data points
            for hour in range(24):
                timestamp = current_date.replace(hour=hour)

                # Simulate realistic data patterns
                base_elevation = 1170 + math.sin(hour / 12 * math.pi) * 2
                actual_elevation = base_elevation + random.uniform(-0.5, 0.5)
                expected_elevation = base_elevation + 0.2 + random.uniform(-0.3, 0.3)
                bias_corrected = base_elevation + 0.1 + random.uniform(-0.2, 0.2)

                oxph_power = max(0, 2 + math.sin(hour / 6 * math.pi) * 1.5 + random.uniform(-0.5, 0.5))

                data.append({
                    'timestamp': timestamp.isoformat(),
                    'actual_elevation_ft': round(actual_elevation, 2),
                    'expected_elevation_ft': round(expected_elevation, 2),
                    'bias_corrected_elevation_ft': round(bias_corrected, 2),
                    'oxph_power_mw': round(oxph_power, 2),
                    'r4_flow_cfs': round(800 + random.uniform(-100, 100), 1),
                    'r30_flow_cfs': round(1200 + random.uniform(-200, 200), 1),
                })


class RecalculateElevationView(APIView):
    """API endpoint for real-time elevation recalculation when users edit MFRA/OXPH values"""

    def post(self, request):
        """Recalculate elevation based on modified forecast data"""
        try:
            forecast_data = request.data.get('forecastData', [])
            if not forecast_data:
                return Response({
                    'error': 'forecastData is required'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Convert list of dicts to DataFrame
            rows = []
            for entry in forecast_data:
                # Handle various date formats
                ts_str = entry.get('datetime') or entry.get('dateTime')
                if not ts_str:
                    continue
                
                try:
                    ts = pd.to_datetime(ts_str).tz_convert('UTC')
                except Exception:
                    # Fallback for naive or other formats
                    try:
                        ts = pd.to_datetime(ts_str)
                        if ts.tz is None:
                            ts = ts.tz_localize('UTC')
                        else:
                            ts = ts.tz_convert('UTC')
                    except Exception:
                        continue

                # Helper to safely get float
                def get_val(keys, default=0.0):
                    for k in keys:
                        if k in entry and entry[k] is not None:
                            try:
                                return float(entry[k])
                            except (ValueError, TypeError):
                                pass
                    return default

                # Helper to get string
                def get_str(keys, default='GEN'):
                    for k in keys:
                        if k in entry and entry[k]:
                            return str(entry[k])
                    return default

                rows.append({
                    'timestamp': ts,
                    'R4_Flow': get_val(['r4', 'r4_forecast', 'R4_Flow']),
                    'R30_Flow': get_val(['r30', 'r30_forecast', 'R30_Flow']),
                    'R20_Flow': get_val(['r20', 'r20_forecast', 'R20_Flow']),
                    'R5L_Flow': get_val(['r5l', 'r5l_forecast', 'R5L_Flow']),
                    'R26_Flow': get_val(['r26', 'r26_forecast', 'R26_Flow']),
                    'MFRA_MW': get_val(['mfra', 'mfra_forecast', 'MFRA_MW']),
                    'OXPH_generation_MW': get_val(['oxph', 'oxph_forecast', 'OXPH_generation_MW']),
                    'FLOAT_FT': get_val(['float_level', 'floatLevel', 'FLOAT_FT'], 1173.0),
                    'Mode': get_str(['mode', 'Mode']),
                    'bias_cfs': get_val(['bias_cfs', 'bias', 'additionalBias']),
                    'ABAY_ft': get_val(['elevation', 'expected_abay', 'ABAY_ft'], None), # For initial reference
                    'actual_elevation': get_val(['abayElevation', 'abay_elevation'], None) # For initial reference
                })

            if not rows:
                return Response({'error': 'No valid rows parsed'}, status=status.HTTP_400_BAD_REQUEST)

            df = pd.DataFrame(rows)
            df.set_index('timestamp', inplace=True)
            df.sort_index(inplace=True)

            # Determine initial elevation
            initial_abay_ft = None
            # Try to find the last actual elevation before the forecast starts, or use the first row's actual/expected
            # For simplicity in this context, we use the first row's actual if present, else expected, else 1170
            first_row = df.iloc[0]
            if pd.notna(first_row.get('actual_elevation')) and first_row.get('actual_elevation') > 0:
                initial_abay_ft = first_row['actual_elevation']
            elif pd.notna(first_row.get('ABAY_ft')) and first_row.get('ABAY_ft') > 0:
                initial_abay_ft = first_row['ABAY_ft']
            else:
                initial_abay_ft = 1170.0

            # Call the core recalculation logic
            # We pass the dataframe as is; recalc_abay_path will use the columns we populated
            recalculated_df = recalc_abay_path(
                df, 
                overrides=None, 
                initial_abay_ft=initial_abay_ft,
                inplace=False
            )

            # Format response
            results = []
            for idx, row in recalculated_df.iterrows():
                results.append({
                    'datetime': idx.isoformat(),
                    'elevation': safe_float(row.get('ABAY_ft')),
                    'oxph': safe_float(row.get('OXPH_generation_MW')),
                    'mfra': safe_float(row.get('MFRA_MW')),
                    'r4': safe_float(row.get('R4_Flow')),
                    'r30': safe_float(row.get('R30_Flow')),
                    'bias_cfs': safe_float(row.get('bias_cfs')),
                    'float_level': safe_float(row.get('FLOAT_FT')),
                    'mode': row.get('Mode'),
                    # Add other calculated fields if needed
                    'net_flow_cfs': safe_float(row.get('ABAY_net_flow_cfs')),
                    'head_limit_mw': safe_float(row.get('Head_limit_MW'))
                })

            return Response({
                'status': 'success',
                'recalculated_data': results
            })

        except Exception as e:
            logger.error(f"Error recalculating elevation: {e}", exc_info=True)
            return Response({
                'error': 'Failed to recalculate elevation',
                'detail': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CurrentStateView(APIView):
    """API endpoint for getting current system state"""

    def get(self, request):
        """Get current reservoir and system state"""
        try:
            # Simulate current state data
            current_state = {
                'timestamp': timezone.now().isoformat(),
                'abay_elevation_ft': 1171.5,
                'abay_volume_af': 2450.8,
                'oxph_power_mw': 3.2,
                'oxph_status': 'Running',
                'r4_flow_cfs': 825.3,
                'r30_flow_cfs': 1150.7,
                'r20_flow_cfs': 945.2,
                'r5l_flow_cfs': 155.8,
                'r26_flow_cfs': 215.4,
                'mfra_power_mw': 165.8,
                'ccs_mode': 0,
                'float_level_setpoint_ft': 1173.0,
                'system_status': 'Normal',
                'optimization_modules_loaded': _optimization_modules_loaded,
                'last_optimization': None
            }

            # Add information about the most recent optimization run
            latest_run = OptimizationRun.objects.filter(
                status='completed'
            ).order_by('-completed_at').first()

            if latest_run:
                current_state['last_optimization'] = {
                    'run_id': latest_run.id,
                    'completed_at': latest_run.completed_at.isoformat(),
                    'run_mode': latest_run.run_mode,
                    'r_bias_cfs': latest_run.r_bias_cfs,
                    'summary': {
                        'peak_elevation_ft': latest_run.peak_elevation_ft,
                        'min_elevation_ft': latest_run.min_elevation_ft,
                        'total_spillage_af': latest_run.total_spillage_af,
                    }
                }

            return Response(current_state)

        except Exception as e:
            logger.error(f"Error getting current state: {e}")
            return Response({
                'error': 'Failed to get current state',
                'detail': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class DashboardView(APIView):
    """API endpoint for dashboard data"""

    def get(self, request):
        """Get dashboard data including recent runs, current state, and charts data"""
        try:
            # Get recent optimization runs
            recent_runs = OptimizationRun.objects.order_by('-created_at')[:10]

            # Get current state
            current_state_view = CurrentStateView()
            current_state_response = current_state_view.get(request)
            current_state = current_state_response.data if current_state_response.status_code == 200 else {}

            return Response({
                'current_state': current_state,
                'recent_runs': OptimizationRunSerializer(recent_runs, many=True).data,
                'chart_data': None,  # Will be populated by frontend
                'system_status': 'Normal',
                'alerts': [],
                'statistics': {
                    'total_runs_today': OptimizationRun.objects.filter(
                        created_at__date=timezone.now().date()
                    ).count(),
                    'successful_runs_today': OptimizationRun.objects.filter(
                        created_at__date=timezone.now().date(),
                        status='completed'
                    ).count(),
                    'avg_runtime_minutes': 3.5,
                }
            })

        except Exception as e:
            logger.error(f"Error getting dashboard data: {e}")
            return Response({
                'error': 'Failed to get dashboard data',
                'detail': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def safe_float(value, default=None):
    """Convert ``value`` to a JSON-safe float.
    The API frequently serializes pandas-derived values where missing entries
    may appear as ``NaN``/``NaT`` objects or even as the string ``"nan"``.
    ``json.dumps`` rejects those sentinel values, so we normalise anything that
    fails a finite-number check back to ``default``.
    """
    if value is None:
        return default

    try:
        # ``pd.isna`` gracefully handles pandas NA/NaT sentinels and avoids
        # propagating them further into ``float`` conversion where they would
        # raise or become ``nan``.
        if pd.isna(value):
            return default
    except TypeError:
        # Some non-scalar objects (e.g. dicts) will raise here; fall through
        # to the conversion/exception handling below.
        pass

    if isinstance(value, str):
        value = value.strip()
        if value == "":
            return default

    try:
        numeric_value = float(value)
    except (TypeError, ValueError, OverflowError):
        return default

    if not math.isfinite(numeric_value):
        return default

    return numeric_value


def _prepare_chart_data(run, results_df=None):
    """Load run results and merge with actual PI data.

    Any NaN values are converted to ``None`` so the returned structure is fully
    JSON-serialisable.
    """

    if results_df is None:
        results_df = _load_run_results_dataframe(run)
    else:
        results_df = results_df.copy()
        if not isinstance(results_df.index, pd.DatetimeIndex):
            results_df.index = pd.to_datetime(results_df.index)
        if results_df.index.tz is None:
            results_df.index = results_df.index.tz_localize('UTC')
        else:
            results_df.index = results_df.index.tz_convert('UTC')
        results_df.sort_index(inplace=True)

    # Fetch actual PI data for overlap
    pi_qs = PIDatum.objects.filter(
        timestamp_utc__gte=results_df.index.min(),
        timestamp_utc__lte=results_df.index.max(),
    ).values(
        'timestamp_utc',
        'abay_elevation_ft',
        'abay_float_ft',
        'oxph_generation_mw',
        'oxph_setpoint_mw',
        'r4_flow_cfs',
        'r30_flow_cfs',
        'r20_flow_cfs',
        'r5l_flow_cfs',
        'r26_flow_cfs',
        'mfp_total_gen_mw',
        'ccs_mode',
    )
    pi_df = pd.DataFrame(list(pi_qs))
    if not pi_df.empty:
        pi_df['timestamp_utc'] = pd.to_datetime(pi_df['timestamp_utc'])
        if pi_df['timestamp_utc'].dt.tz is None:
            pi_df['timestamp_utc'] = pi_df['timestamp_utc'].dt.tz_localize('UTC')
        else:
            pi_df['timestamp_utc'] = pi_df['timestamp_utc'].dt.tz_convert('UTC')
        pi_df.set_index('timestamp_utc', inplace=True)
        merged = results_df.join(pi_df, how='left')
    else:
        merged = results_df
        merged['abay_elevation_ft'] = None
        merged['abay_float_ft'] = None
        merged['oxph_generation_mw'] = None

    def _friendly_source_name(source_key):
        if not source_key:
            return ''
        key = str(source_key).lower()
        if 'hydro' in key:
            return 'HydroForecast'
        if 'cnrfc' in key:
            return 'CNRFC Forecast'
        return str(source_key).replace('_', ' ').replace('-', ' ').title()

    chart_data = {
        'labels': [],
        'elevation': {
            'optimized': [],
            'actual': [],
            'bias_corrected': [],
            'float': [],
        },
        'oxph': {
            'optimized': [],
            'historical': []
        },
        'mfra': {
            'forecast': [],
            'historical': []
        },
        'river': {
            'selected_source': run.forecast_source,
            'selected_source_label': None,
            'source_labels': {
                'hydro': 'HydroForecast',
                'cnrfc': 'CNRFC Forecast'
            },
            'r4': {
                'actual': [],
                'hydro': [],
                'cnrfc': []
            },
            'r30': {
                'actual': [],
                'hydro': [],
                'cnrfc': []
            }
        },
        'actual_mask': [],
        'forecast_data': []
    }

    chart_data['river']['selected_source_label'] = _friendly_source_name(run.forecast_source)

    def _extract_series_by_keywords(df, site_key, keywords):
        site_key = site_key.lower()
        for col in df.columns:
            lower = col.lower()
            if site_key in lower and 'forecast' in lower and any(keyword in lower for keyword in keywords):
                series = df[col]
                if isinstance(series, pd.Series):
                    return series
        return None

    def _fetch_forecast_df(source_key):
        try:
            df = get_combined_r4_r30_forecasts(forecast_source=source_key, fallback_to_cnrfc=False)
        except Exception as exc:
            logger.warning("Failed to fetch %s forecasts: %s", source_key, exc)
            return None
        if df is None or df.empty:
            return None
        return df

    def _align_series(series):
        if series is None or len(series) == 0:
            return None
        aligned = series.copy()
        if not isinstance(aligned.index, pd.DatetimeIndex):
            return None
        if aligned.index.tz is None:
            aligned.index = aligned.index.tz_localize('UTC')
        else:
            aligned.index = aligned.index.tz_convert('UTC')
        try:
            reindexed = aligned.reindex(merged.index)
        except Exception:
            return None
        if reindexed.isna().all():
            try:
                reindexed = aligned.reindex(
                    merged.index,
                    method='nearest',
                    tolerance=pd.Timedelta(minutes=30)
                )
            except Exception:
                pass
        return reindexed

    hydro_r4_series = _extract_series_by_keywords(results_df, 'r4', ['hydro', 'hf'])
    hydro_r30_series = _extract_series_by_keywords(results_df, 'r30', ['hydro', 'hf'])
    cnrfc_r4_series = _extract_series_by_keywords(results_df, 'r4', ['cnrfc'])
    cnrfc_r30_series = _extract_series_by_keywords(results_df, 'r30', ['cnrfc'])

    if hydro_r4_series is None and hydro_r30_series is None:
        hydro_df = _fetch_forecast_df(abay_constants.UPSTREAM_FORECAST_SOURCE_HYDROFORECAST)
        if hydro_df is not None:
            hydro_r4_series = hydro_df.get('R4_Forecast_CFS')
            hydro_r30_series = hydro_df.get('R30_Forecast_CFS')

    if cnrfc_r4_series is None and cnrfc_r30_series is None:
        cnrfc_df = _fetch_forecast_df(abay_constants.UPSTREAM_FORECAST_SOURCE_CNRFC)
        if cnrfc_df is not None:
            cnrfc_r4_series = cnrfc_df.get('R4_Forecast_CFS')
            cnrfc_r30_series = cnrfc_df.get('R30_Forecast_CFS')

    aligned_forecasts = {
        'hydro': {
            'r4': _align_series(hydro_r4_series),
            'r30': _align_series(hydro_r30_series)
        },
        'cnrfc': {
            'r4': _align_series(cnrfc_r4_series),
            'r30': _align_series(cnrfc_r30_series)
        }
    }

    def _first_non_missing(row, keys):
        for key in keys:
            if key in row.index:
                value = row.get(key)
                if value is not None and not pd.isna(value):
                    if isinstance(value, str) and value.strip() == '':
                        continue
                    return value
        return None

    prev_setpoint = None
    for position, (idx, row) in enumerate(merged.iterrows()):
        timestamp_pt = idx.tz_convert('America/Los_Angeles')
        chart_data['labels'].append(timestamp_pt.strftime('%a %b %d, %H'))

        elev_forecast = row.get('ABAY_ft')
        float_val = row.get('FLOAT_FT', row.get('Afterbay_Elevation_Setpoint'))

        oxph_forecast_raw = row.get('OXPH_generation_MW', row.get('OXPH_Schedule_MW'))
        oxph_actual_raw = row.get('oxph_generation_mw')
        if pd.isna(oxph_forecast_raw):
            oxph_forecast_raw = oxph_actual_raw
        oxph_forecast = safe_float(oxph_forecast_raw)
        oxph_actual = safe_float(oxph_actual_raw)
        oxph_setpoint_raw = _first_non_missing(
            row,
            [
                'OXPH_setpoint_MW',
                'oxph_setpoint_mw',
                'oxph_setpoint_target',
                'OXPH_Setpoint_Target',
            ],
        )
        if oxph_setpoint_raw is None:
            oxph_setpoint_raw = oxph_forecast_raw

        r4_forecast_raw = _first_non_missing(row, ['R4_Forecast_CFS', 'R4_Flow', 'r4_forecast'])
        if r4_forecast_raw is None:
            r4_forecast_raw = row.get('r4_flow_cfs')
        r4_forecast = safe_float(r4_forecast_raw)
        r4_actual = safe_float(row.get('r4_flow_cfs'))

        r30_forecast_raw = _first_non_missing(row, ['R30_Forecast_CFS', 'R30_Flow', 'r30_forecast'])
        if r30_forecast_raw is None:
            r30_forecast_raw = row.get('r30_flow_cfs')
        r30_forecast = safe_float(r30_forecast_raw)
        r30_actual = safe_float(row.get('r30_flow_cfs'))

        mfra_forecast_raw = _first_non_missing(row, ['MFRA_MW_forecast', 'MFRA_Forecast_MW', 'MFRA_MW'])
        mfra_actual_raw = row.get('mfp_total_gen_mw')
        if pd.isna(mfra_forecast_raw):
            mfra_forecast_raw = mfra_actual_raw
        mfra_forecast = safe_float(mfra_forecast_raw)
        mfra_actual = safe_float(mfra_actual_raw)

        abay_actual = safe_float(row.get('abay_elevation_ft'))

        has_actual = any(
            pd.notna(val) for val in (
                oxph_actual_raw,
                mfra_actual_raw,
                row.get('r4_flow_cfs'),
                row.get('r30_flow_cfs'),
                row.get('abay_elevation_ft')
            )
        )

        hydro_r4_value = None
        hydro_r30_value = None
        cnrfc_r4_value = None
        cnrfc_r30_value = None

        hydro_r4_series_aligned = aligned_forecasts['hydro']['r4']
        if hydro_r4_series_aligned is not None and position < len(hydro_r4_series_aligned):
            hydro_r4_value = safe_float(hydro_r4_series_aligned.iloc[position])
        hydro_r30_series_aligned = aligned_forecasts['hydro']['r30']
        if hydro_r30_series_aligned is not None and position < len(hydro_r30_series_aligned):
            hydro_r30_value = safe_float(hydro_r30_series_aligned.iloc[position])

        cnrfc_r4_series_aligned = aligned_forecasts['cnrfc']['r4']
        if cnrfc_r4_series_aligned is not None and position < len(cnrfc_r4_series_aligned):
            cnrfc_r4_value = safe_float(cnrfc_r4_series_aligned.iloc[position])
        cnrfc_r30_series_aligned = aligned_forecasts['cnrfc']['r30']
        if cnrfc_r30_series_aligned is not None and position < len(cnrfc_r30_series_aligned):
            cnrfc_r30_value = safe_float(cnrfc_r30_series_aligned.iloc[position])

        if hydro_r4_value is None and run.forecast_source and 'hydro' in run.forecast_source.lower():
            hydro_r4_value = r4_forecast
        if hydro_r30_value is None and run.forecast_source and 'hydro' in run.forecast_source.lower():
            hydro_r30_value = r30_forecast
        if cnrfc_r4_value is None and run.forecast_source and 'cnrfc' in run.forecast_source.lower():
            cnrfc_r4_value = r4_forecast
        if cnrfc_r30_value is None and run.forecast_source and 'cnrfc' in run.forecast_source.lower():
            cnrfc_r30_value = r30_forecast

        chart_data['elevation']['optimized'].append(safe_float(elev_forecast))
        chart_data['elevation']['actual'].append(abay_actual)
        chart_data['elevation']['bias_corrected'].append(None)
        chart_data['elevation']['float'].append(safe_float(float_val))

        chart_data['oxph']['optimized'].append(oxph_forecast)
        chart_data['oxph']['historical'].append(oxph_actual)

        chart_data['mfra']['forecast'].append(mfra_forecast)
        chart_data['mfra']['historical'].append(mfra_actual)

        chart_data['river']['r4']['actual'].append(r4_actual)
        chart_data['river']['r30']['actual'].append(r30_actual)
        chart_data['river']['r4']['hydro'].append(hydro_r4_value)
        chart_data['river']['r30']['hydro'].append(hydro_r30_value)
        chart_data['river']['r4']['cnrfc'].append(cnrfc_r4_value)
        chart_data['river']['r30']['cnrfc'].append(cnrfc_r30_value)

        chart_data['actual_mask'].append(has_actual)

        setpoint_change = None
        explicit_setpoint_change = _first_non_missing(
            row, ['setpoint_change_time', 'setpoint_adjust_time_pt']
        )
        if explicit_setpoint_change is not None:
            try:
                if isinstance(explicit_setpoint_change, str):
                    if not re.search(r'\d{4}-\d{2}-\d{2}', explicit_setpoint_change):
                        raise ValueError('setpoint change timestamp missing date component')
                explicit_timestamp = pd.to_datetime(explicit_setpoint_change)
                if pd.isna(explicit_timestamp):
                    raise ValueError('setpoint change timestamp is NaT')
                if explicit_timestamp.tzinfo is None:
                    explicit_timestamp = explicit_timestamp.tz_localize('UTC')
                else:
                    explicit_timestamp = explicit_timestamp.tz_convert('UTC')
                setpoint_change = explicit_timestamp.tz_convert('America/Los_Angeles').isoformat()
            except Exception:
                setpoint_change = None

        setpoint_numeric = safe_float(oxph_setpoint_raw)
        if setpoint_numeric is not None:
            setpoint_rounded = round(setpoint_numeric, 1)
            if setpoint_change is None and (
                prev_setpoint is None or abs(setpoint_rounded - prev_setpoint) > 0.15
            ):
                # Stabilization check: only flag if the setpoint has settled
                # (next row has the same rounded value, or this is the last row)
                total_rows = len(merged)
                is_last = (position + 1 >= total_rows)
                is_stable = is_last
                if not is_last:
                    next_row = merged.iloc[position + 1]
                    next_sp_raw = _first_non_missing(
                        next_row,
                        ['OXPH_setpoint_MW', 'oxph_setpoint_mw',
                         'oxph_setpoint_target', 'OXPH_Setpoint_Target'],
                    )
                    next_sp = safe_float(next_sp_raw)
                    if next_sp is not None:
                        is_stable = abs(setpoint_rounded - round(next_sp, 1)) <= 0.15
                if is_stable:
                    setpoint_change = timestamp_pt.isoformat()
                    prev_setpoint = setpoint_rounded
            else:
                prev_setpoint = setpoint_rounded

        mode_forecast_value = row.get('Mode')
        try:
            if pd.isna(mode_forecast_value):
                mode_forecast_value = None
        except TypeError:
            pass
        if isinstance(mode_forecast_value, (int, float)) and not math.isfinite(float(mode_forecast_value)):
            mode_forecast_value = None
        if isinstance(mode_forecast_value, str):
            mode_forecast_value = mode_forecast_value.strip() or None

        mode_actual_value = row.get('ccs_mode')
        try:
            if pd.isna(mode_actual_value):
                mode_actual_value = None
        except TypeError:
            pass
        if isinstance(mode_actual_value, (int, float)) and not math.isfinite(float(mode_actual_value)):
            mode_actual_value = None

        chart_data['forecast_data'].append({
            'datetime': timestamp_pt.isoformat(),
            'setpoint': safe_float(oxph_setpoint_raw),
            'oxph': oxph_forecast,
            'oxph_actual': oxph_actual,
            'setpoint_change': setpoint_change,
            'r4_forecast': r4_forecast,
            'r30_forecast': r30_forecast,
            'r4_actual': r4_actual,
            'r30_actual': r30_actual,
            'r4_hydro_forecast': hydro_r4_value,
            'r4_cnrfc_forecast': cnrfc_r4_value,
            'r30_hydro_forecast': hydro_r30_value,
            'r30_cnrfc_forecast': cnrfc_r30_value,
            'r20_forecast': safe_float(row.get('R20_Flow')),
            'r20_actual': safe_float(row.get('r20_flow_cfs')),
            'r5l_forecast': safe_float(row.get('R5L_Flow')),
            'r5l_actual': safe_float(row.get('r5l_flow_cfs')),
            'r26_forecast': safe_float(row.get('R26_Flow')),
            'r26_actual': safe_float(row.get('r26_flow_cfs')),
            'mode_forecast': mode_forecast_value,
            'mode_actual': mode_actual_value,
            'abay_elevation': abay_actual,
            'expected_abay': safe_float(elev_forecast),
            'float_level': safe_float(float_val),
            'mfra_forecast': mfra_forecast,
            'mfra_actual': mfra_actual,
            'bias_cfs': safe_float(row.get('bias_cfs')),
            'additional_bias': safe_float(row.get('bias_cfs'))
        })

    return chart_data


def _run_metadata(run):
    """Return a compact metadata dictionary for a run."""
    if not run:
        return None

    created_by_name = None
    created_by_username = None
    if run.created_by:
        created_by_username = run.created_by.username
        full_name = run.created_by.get_full_name()
        created_by_name = full_name if full_name else created_by_username

    return {
        'id': run.id,
        'created_at': run.created_at.isoformat() if run.created_at else None,
        'completed_at': run.completed_at.isoformat() if run.completed_at else None,
        'created_by': created_by_username,
        'created_by_username': created_by_username,
        'created_by_name': created_by_name,
        'forecast_source': run.forecast_source,
        'run_mode': run.run_mode,
        'run_mode_display': run.get_run_mode_display(),
        'status': run.status,
        'status_display': run.get_status_display(),
        'mfra_source': (run.custom_parameters or {}).get('mfra_source', 'persistence'),
    }


class OptimizationResultsView(APIView):
    """API endpoint to fetch optimization results"""

    def get(self, request, run_id):
        try:
            run = OptimizationRun.objects.get(id=run_id)
            if run.status != 'completed':
                return Response({'error': 'Optimization not completed', 'status': run.status}, status=status.HTTP_400_BAD_REQUEST)
            if not run.result_file_path or not os.path.exists(run.result_file_path):
                return Response({'error': 'Results file not found'}, status=status.HTTP_404_NOT_FOUND)

            chart_data = _prepare_chart_data(run)
            return Response({
                'status': 'success',
                'run_id': run_id,
                'solver_status': run.solver_diagnostics.get('status') if run.solver_diagnostics else None,
                'chart_data': chart_data,
                'run': _run_metadata(run),
                'summary': {
                    'total_spillage_af': safe_float(run.total_spillage_af),
                    'avg_oxph_utilization_pct': safe_float(run.avg_oxph_utilization_pct),
                    'peak_elevation_ft': safe_float(run.peak_elevation_ft),
                    'min_elevation_ft': safe_float(run.min_elevation_ft),
                    'r_bias_cfs': safe_float(run.r_bias_cfs),
                }
            })
        except OptimizationRun.DoesNotExist:
            return Response({'error': 'Optimization run not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error fetching optimization results: {e}")
            return Response({'error': 'Failed to fetch results', 'detail': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ApplyBiasView(APIView):
    """Apply a manual bias correction to an existing optimization run."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        if 'bias_cfs' in request.data:
            bias_raw = request.data.get('bias_cfs')
        elif 'bias' in request.data:
            bias_raw = request.data.get('bias')
        elif 'biasValue' in request.data:
            bias_raw = request.data.get('biasValue')
        else:
            bias_raw = None

        if bias_raw in (None, ''):
            return Response({'error': 'bias_cfs is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            bias_value = float(bias_raw)
        except (TypeError, ValueError):
            return Response({'error': 'bias_cfs must be a numeric value'}, status=status.HTTP_400_BAD_REQUEST)

        run_id = request.data.get('run_id') or request.data.get('runId')
        if not run_id:
            return Response({'error': 'run_id is required to apply bias'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            run = OptimizationRun.objects.get(id=run_id)
        except OptimizationRun.DoesNotExist:
            return Response({'error': 'Optimization run not found'}, status=status.HTTP_404_NOT_FOUND)

        if not run.result_file_path:
            return Response({'error': 'Optimization results are not available for this run'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            results_df = _load_run_results_dataframe(run)
        except Exception as exc:
            logger.error('Failed to load run results for bias application: %s', exc, exc_info=True)
            return Response({
                'error': 'Unable to load run data for bias application',
                'detail': str(exc)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        if results_df.empty:
            return Response({'error': 'Optimization results are empty'}, status=status.HTTP_400_BAD_REQUEST)

        forecast_mask = None
        if 'is_forecast' in results_df.columns:
            forecast_mask = results_df['is_forecast'].astype(bool)
        if (forecast_mask is None or not forecast_mask.any()) and 'Expected_ABAY_ft' in results_df.columns:
            fallback_mask = results_df['Expected_ABAY_ft'].isna()
            forecast_mask = fallback_mask if forecast_mask is None else (forecast_mask | fallback_mask)
        if (forecast_mask is None or not forecast_mask.any()) and 'bias_cfs' in results_df.columns:
            forecast_mask = results_df['bias_cfs'].notna()

        if forecast_mask is None or not forecast_mask.any():
            return Response({'error': 'Unable to identify forecast rows to update'}, status=status.HTTP_400_BAD_REQUEST)

        forecast_df = results_df.loc[forecast_mask].copy()
        forecast_df.sort_index(inplace=True)

        forecast_df['bias_cfs'] = bias_value

        required_columns = [
            'R4_Flow', 'R30_Flow', 'R20_Flow', 'R5L_Flow', 'R26_Flow',
            'MFRA_MW', 'FLOAT_FT', 'Mode', 'OXPH_generation_MW'
        ]
        for column in required_columns:
            if column not in forecast_df.columns:
                forecast_df[column] = 'GEN' if column == 'Mode' else 0.0

        if 'ABAY_ft' not in forecast_df.columns:
            forecast_df['ABAY_ft'] = None
        if 'ABAY_af' not in forecast_df.columns:
            forecast_df['ABAY_af'] = None

        indexer = results_df.index.get_indexer([forecast_df.index[0]])
        initial_abay_ft = None
        if len(indexer) and indexer[0] > 0:
            prev_idx = results_df.index[indexer[0] - 1]
            prev_value = results_df.at[prev_idx, 'ABAY_ft'] if 'ABAY_ft' in results_df.columns else None
            if pd.notna(prev_value):
                initial_abay_ft = float(prev_value)

        if (initial_abay_ft is None or not math.isfinite(initial_abay_ft)) and 'ABAY_ft' in forecast_df.columns:
            first_forecast_abay = forecast_df['ABAY_ft'].dropna()
            if not first_forecast_abay.empty:
                initial_abay_ft = float(first_forecast_abay.iloc[0])

        try:
            recalculated = recalc_abay_path(forecast_df, overrides=None, initial_abay_ft=initial_abay_ft)
        except Exception as exc:
            logger.error('Bias recalculation failed for run %s: %s', run.id, exc, exc_info=True)
            return Response({
                'error': 'Failed to recalculate elevation with bias',
                'detail': str(exc)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        for column in ['ABAY_ft', 'ABAY_af', 'OXPH_generation_MW', 'OXPH_outflow_cfs', 'Regulated_component_cfs', 'Head_limit_MW']:
            if column in recalculated.columns:
                forecast_df[column] = recalculated[column]

        forecast_df['bias_cfs'] = bias_value
        forecast_df['abay_error_cfs'] = bias_value
        forecast_df['abay_error_af'] = bias_value * AF_PER_CFS_HOUR

        updated_results_df = results_df.copy()
        for column in forecast_df.columns:
            updated_results_df.loc[forecast_df.index, column] = forecast_df[column]

        run.r_bias_cfs = bias_value
        run.save(update_fields=['r_bias_cfs'])

        chart_data = _prepare_chart_data(run, results_df=updated_results_df)

        peak_elev = safe_float(updated_results_df['ABAY_ft'].max())
        min_elev = safe_float(updated_results_df['ABAY_ft'].min())

        avg_oxph_util_pct = None
        if 'OXPH_generation_MW' in forecast_df.columns:
            non_null_gen = forecast_df['OXPH_generation_MW'].dropna()
            if not non_null_gen.empty:
                try:
                    max_mw = float(getattr(abay_constants, 'OXPH_MAX_MW', 5.8)) or 5.8
                    if max_mw:
                        avg_val = non_null_gen.mean()
                        avg_oxph_util_pct = safe_float((avg_val / max_mw) * 100.0)
                except Exception:
                    avg_oxph_util_pct = None

        summary = {
            'total_spillage_af': safe_float(run.total_spillage_af),
            'avg_oxph_utilization_pct': avg_oxph_util_pct if avg_oxph_util_pct is not None else safe_float(run.avg_oxph_utilization_pct),
            'peak_elevation_ft': peak_elev,
            'min_elevation_ft': min_elev,
            'r_bias_cfs': bias_value,
        }

        return Response({
            'status': 'success',
            'run_id': run.id,
            'run': _run_metadata(run),
            'chart_data': chart_data,
            'summary': summary,
            'applied_bias_cfs': bias_value,
        })


class SaveEditedOptimizationView(APIView):
    """Persist manually edited forecast data as a new optimization run."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        forecast_data = request.data.get('forecast_data') or request.data.get('forecastData')
        if not forecast_data or not isinstance(forecast_data, list):
            return Response({'error': 'forecast_data must be a non-empty list'}, status=status.HTTP_400_BAD_REQUEST)

        source_run_id = request.data.get('source_run_id') or request.data.get('sourceRunId')
        source_run = None
        if source_run_id:
            source_run = OptimizationRun.objects.filter(id=source_run_id).first()

        now = timezone.now()

        custom_parameters = {}
        if source_run and source_run.custom_parameters:
            custom_parameters = deepcopy(source_run.custom_parameters)

        if source_run_id:
            custom_parameters['source_run_id'] = source_run_id
        custom_parameters['manual_adjustment'] = True

        run = OptimizationRun.objects.create(
            run_mode=source_run.run_mode if source_run else 'forecast',
            optimizer_type=source_run.optimizer_type if source_run else 'linear',
            forecast_source=source_run.forecast_source if source_run else 'manual_adjustment',
            historical_start_date=source_run.historical_start_date if source_run else None,
            parameter_set=source_run.parameter_set if source_run else None,
            custom_parameters=custom_parameters,
            created_by=request.user,
            status='completed',
            started_at=now,
            completed_at=now,
            progress_percentage=100,
            progress_message='Manual adjustments saved from dashboard',
            solver_diagnostics={'status': 'Manual Adjustment'}
        )

        rows = []

        for entry in forecast_data:
            timestamp_str = entry.get('datetime') or entry.get('dateTime')
            if not timestamp_str:
                continue

            timestamp = parse_datetime(timestamp_str)
            if timestamp is None:
                try:
                    timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                except Exception:
                    continue

            if timezone.is_naive(timestamp):
                timestamp = timezone.make_aware(timestamp, timezone=timezone.utc)
            else:
                timestamp = timestamp.astimezone(timezone.utc)

            def pick(*keys):
                for key in keys:
                    if key in entry and entry[key] is not None:
                        return entry[key]
                return None

            rows.append({
                'timestamp': timestamp,
                'ABAY_ft': pick('expected_abay', 'expectedAbay', 'elevation'),
                'FLOAT_FT': pick('float_level', 'floatLevel'),
                'OXPH_generation_MW': pick('oxph', 'oxph_forecast'),
                'OXPH_Schedule_MW': pick('oxph', 'oxph_forecast'),
                'oxph_setpoint_mw': pick('setpoint', 'oxph_setpoint'),
                'setpoint_change_time': pick('setpoint_change_time', 'setpoint_change', 'setpointChange'),
                'R4_Forecast_CFS': pick('r4', 'r4_forecast'),
                'R30_Forecast_CFS': pick('r30', 'r30_forecast'),
                'R20_Flow': pick('r20', 'r20_forecast', 'R20_Flow'),
                'R5L_Flow': pick('r5l', 'r5l_forecast', 'R5L_Flow'),
                'R26_Flow': pick('r26', 'r26_forecast', 'R26_Flow'),
                'MFRA_MW_forecast': pick('mfra', 'mfra_forecast'),
                'MFRA_Forecast_MW': pick('mfra', 'mfra_forecast'),
                'R4_Actual_CFS': pick('r4_actual', 'r4Actual'),
                'R30_Actual_CFS': pick('r30_actual', 'r30Actual'),
                'r20_flow_cfs': pick('r20_actual', 'r20Actual'),
                'r5l_flow_cfs': pick('r5l_actual', 'r5lActual'),
                'r26_flow_cfs': pick('r26_actual', 'r26Actual'),
                'MFRA_Actual_MW': pick('mfra_actual', 'mfraActual'),
                'OXPH_actual_MW': pick('oxph_actual', 'oxphActual'),
                'Afterbay_Elevation_Setpoint': pick('float_level', 'floatLevel')
            })

        if not rows:
            run.delete()
            return Response({'error': 'No valid forecast rows provided'}, status=status.HTTP_400_BAD_REQUEST)

        df = pd.DataFrame(rows)
        df.set_index('timestamp', inplace=True)
        df.sort_index(inplace=True)

        output_dir = settings.ABAY_OPTIMIZATION.get('OUTPUT_DIR', settings.BASE_DIR / 'optimization_outputs')
        os.makedirs(output_dir, exist_ok=True)
        filename = f'optimization_run_{run.id}_{now.strftime("%Y%m%d_%H%M%S")}.csv'
        file_path = Path(output_dir) / filename
        df.to_csv(file_path)

        run.result_file_path = str(file_path)

        if not df['ABAY_ft'].dropna().empty:
            run.peak_elevation_ft = safe_float(df['ABAY_ft'].max())
            run.min_elevation_ft = safe_float(df['ABAY_ft'].min())

        if not df['OXPH_generation_MW'].dropna().empty:
            try:
                avg_oxph = df['OXPH_generation_MW'].dropna().mean()
                utilization = max(0.0, min(100.0, (avg_oxph / 5.8) * 100.0))
                run.avg_oxph_utilization_pct = safe_float(utilization)
            except Exception:
                run.avg_oxph_utilization_pct = None

        run.save()

        chart_data = _prepare_chart_data(run)
        summary = {
            'total_spillage_af': safe_float(run.total_spillage_af),
            'avg_oxph_utilization_pct': safe_float(run.avg_oxph_utilization_pct),
            'peak_elevation_ft': safe_float(run.peak_elevation_ft),
            'min_elevation_ft': safe_float(run.min_elevation_ft),
            'r_bias_cfs': safe_float(run.r_bias_cfs),
        }

        return Response({
            'status': 'success',
            'run_id': run.id,
            'message': 'Manual optimization run saved',
            'run': _run_metadata(run),
            'chart_data': chart_data,
            'summary': summary
        }, status=status.HTTP_201_CREATED)


class LatestOptimizationResultsView(APIView):
    """Return most recent completed optimization results for the current user."""

    def get(self, request):
        run = OptimizationRun.objects.filter(created_by=request.user, status='completed').order_by('-created_at').first()
        if not run:
            return Response({'error': 'No completed runs found'}, status=status.HTTP_404_NOT_FOUND)
        chart_data = _prepare_chart_data(run)
        return Response({
            'status': 'success',
            'run_id': run.id,
            'solver_status': run.solver_diagnostics.get('status') if run.solver_diagnostics else None,
            'run': _run_metadata(run),
            'chart_data': chart_data,
            'summary': {
                'total_spillage_af': safe_float(run.total_spillage_af),
                'avg_oxph_utilization_pct': safe_float(run.avg_oxph_utilization_pct),
                'peak_elevation_ft': safe_float(run.peak_elevation_ft),
                'min_elevation_ft': safe_float(run.min_elevation_ft),
                'r_bias_cfs': safe_float(run.r_bias_cfs),
            }
        })


class RefreshPIDataView(APIView):
    """Fetch latest PI data and store in PIDatum."""

    def post(self, request):
        try:
            from abay_opt import data_fetcher

            _, lookback = data_fetcher.get_historical_and_current_data()
            if lookback is None or lookback.empty:
                return Response({'error': 'Failed to fetch PI data'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            last_ts = PIDatum.objects.order_by('-timestamp_utc').values_list('timestamp_utc', flat=True).first()
            if last_ts:
                lookback = lookback[lookback.index > pd.Timestamp(last_ts).tz_convert('UTC')]

            created = 0
            for idx, row in lookback.iterrows():
                PIDatum.objects.update_or_create(
                    timestamp_utc=idx.tz_convert('UTC'),
                    defaults={
                        'abay_elevation_ft': row.get('Afterbay_Elevation'),
                        'abay_float_ft': row.get('Afterbay_Elevation_Setpoint'),
                        'oxph_generation_mw': row.get('Oxbow_Power'),
                        'oxph_setpoint_mw': row.get('OXPH_ADS'),
                        'r4_flow_cfs': row.get('R4_Flow'),
                        'r30_flow_cfs': row.get('R30_Flow'),
                        'r20_flow_cfs': row.get('R20_Flow'),
                        'r5l_flow_cfs': row.get('R5L_Flow'),
                        'r26_flow_cfs': row.get('R26_Flow'),
                        'mfp_total_gen_mw': row.get('MFP_Total_Gen_GEN_MDFK_and_RA'),
                        'ccs_mode': row.get('CCS_Mode'),
                    }
                )
                created += 1

            return Response({'status': 'success', 'records': created})
        except Exception as e:
            logger.error(f"Error refreshing PI data: {e}")
            return Response({'error': 'Failed to refresh PI data', 'detail': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def dashboard_view(request):
    """Serve the main dashboard HTML page"""
    return render(request, 'dashboard.html', {
        'user': request.user,
        'title': 'ABAY Reservoir Optimization Dashboard'
    })


# ADD these views to your views.py for rafting configuration management

class RaftingConfigView(APIView):
    """API endpoint for managing rafting recreation configuration"""

    def get(self, request):
        """Get current rafting configuration"""
        try:
            # Dynamic import of optimization modules (same pattern as your existing views)
            current_dir = Path(__file__).resolve().parent
            project_root = current_dir.parent.parent
            abay_opt_path = project_root / 'abay_opt'

            if str(project_root) not in sys.path:
                sys.path.insert(0, str(project_root))

            # Import constants
            try:
                import abay_opt.constants as constants
            except ImportError as e:
                logger.warning(f"Could not import optimization modules: {e}")
                return Response({
                    'error': 'Optimization modules not available',
                    'detail': str(e)
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            config = {
                'current_water_year_type': constants.CURRENT_WATER_YEAR_TYPE,
                'early_release_saturdays': [
                    {
                        'date': f"{month:02d}-{day:02d}-{year}",
                        'formatted': f"{date(year, month, day).strftime('%B %d, %Y')}"
                    }
                    for month, day, year in constants.EARLY_RELEASE_SATURDAYS
                ],
                'water_year_types': list(constants.RAFTING_SCHEDULES.keys()),
                'rafting_season': {
                    'end_date': f"{constants.RAFTING_SEASON_END_DATE[0]:02d}-{constants.RAFTING_SEASON_END_DATE[1]:02d}",
                    'min_flow_cfs': constants.RAFTING_MIN_FLOW_CFS,
                    'optimal_flow_cfs': constants.RAFTING_OPTIMAL_FLOW_CFS,
                },
                'early_release_config': {
                    'start_time': constants.EARLY_RELEASE_START_TIME.strftime('%H:%M'),
                    'end_time': constants.EARLY_RELEASE_END_TIME.strftime('%H:%M'),
                    'target_mw': constants.EARLY_RELEASE_TARGET_MW,
                }
            }

            return Response({
                'status': 'success',
                'config': config
            })

        except Exception as e:
            logger.error(f"Error getting rafting configuration: {e}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            return Response({
                'error': 'Failed to get rafting configuration',
                'detail': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class RaftingTimesView(APIView):
    """API endpoint for rafting times dashboard widget"""

    def get(self, request):
        """Get today and tomorrow's rafting times with OXPH adjustment info"""
        try:
            # Import optimization modules
            current_dir = Path(__file__).resolve().parent
            project_root = current_dir.parent.parent

            if str(project_root) not in sys.path:
                sys.path.insert(0, str(project_root))

            import abay_opt.constants as constants
            import abay_opt.schedule as schedule

            now_pt = timezone.now().astimezone(constants.PACIFIC_TZ)
            today = now_pt.date()
            tomorrow = today + timedelta(days=1)

            def get_rafting_info_for_date(check_date):
                """Get rafting schedule info for a specific date"""
                # Check multiple times throughout the day to find rafting periods
                times_to_check = [
                    time(4, 0),  # Early release check
                    time(8, 0),  # Weekend start
                    time(9, 0),  # Weekday start
                    time(12, 0),  # Noon
                ]

                rafting_periods = []
                for check_time in times_to_check:
                    timestamp = constants.PACIFIC_TZ.localize(
                        datetime.combine(check_date, check_time)
                    )
                    is_active = schedule.summer_setpoint_required(timestamp)
                    schedule_type = 'weekend' if timestamp.weekday() >= 5 else 'weekday'

                    if is_active:
                        rafting_periods.append({
                            'time': check_time,
                            'active': True,
                            'type': schedule_type
                        })

                if not rafting_periods:
                    return {
                        'has_rafting': False,
                        'start_time': None,
                        'end_time': None,
                        'is_early_release': False,
                        'oxph_adjustment_needed': False,
                        'oxph_adjustment_time': None,
                        'current_oxph_setting': None
                    }

                # Find the actual start and end times from the schedule
                weekday_name = check_date.strftime('%A')
                water_year_type = constants.CURRENT_WATER_YEAR_TYPE

                # Determine if we're in main season or post-Labor Day
                labor_day_date = schedule.labor_day(check_date.year)
                if check_date <= labor_day_date:
                    schedule_period = 'main_season'
                else:
                    schedule_period = 'post_labor_day'

                sched = constants.RAFTING_SCHEDULES[water_year_type][schedule_period]
                is_weekend = weekday_name in ['Saturday', 'Sunday']
                schedule_type = 'weekends' if is_weekend else 'weekdays'
                day_schedule = sched[schedule_type]

                # Check if this day has rafting
                if weekday_name not in day_schedule['days']:
                    return {
                        'has_rafting': False,
                        'start_time': None,
                        'end_time': None,
                        'is_early_release': False,
                        'oxph_adjustment_needed': False,
                        'oxph_adjustment_time': None,
                        'current_oxph_setting': None
                    }

                # Get base times
                base_start_time = day_schedule['start_time']
                end_time = day_schedule['end_time']

                # Check for early release
                is_early_release = False
                actual_start_time = base_start_time
                for month, day, year in constants.EARLY_RELEASE_SATURDAYS:
                    if check_date == date(year, month, day):
                        is_early_release = True
                        actual_start_time = constants.EARLY_RELEASE_START_TIME
                        break

                # Calculate when OXPH adjustment needs to be made
                target_mw = constants.SUMMER_OXPH_TARGET_MW
                min_mw = constants.OXPH_MIN_MW
                ramp_rate = constants.OXPH_RAMP_RATE_MW_PER_MIN

                # Calculate ramp time needed
                ramp_minutes = (target_mw - min_mw) / ramp_rate if ramp_rate > 0 else 0

                # Time when adjustment should be made
                target_start_dt = datetime.combine(check_date, actual_start_time)
                adjustment_dt = target_start_dt - timedelta(minutes=ramp_minutes)
                adjustment_time = adjustment_dt.time()

                return {
                    'has_rafting': True,
                    'start_time': actual_start_time.strftime('%H:%M'),
                    'end_time': end_time.strftime('%H:%M'),
                    'is_early_release': is_early_release,
                    'oxph_adjustment_needed': True,
                    'oxph_adjustment_time': adjustment_time.strftime('%H:%M'),
                    'current_oxph_setting': f"{min_mw} MW → {target_mw} MW",
                    'ramp_duration_minutes': round(ramp_minutes, 1)
                }

            # Get info for today and tomorrow
            today_info = get_rafting_info_for_date(today)
            tomorrow_info = get_rafting_info_for_date(tomorrow)

            return Response({
                'status': 'success',
                'current_time': now_pt.strftime('%H:%M'),
                'water_year_type': constants.CURRENT_WATER_YEAR_TYPE,
                'today': {
                    'date': today.strftime('%Y-%m-%d'),
                    'day_name': today.strftime('%A'),
                    **today_info
                },
                'tomorrow': {
                    'date': tomorrow.strftime('%Y-%m-%d'),
                    'day_name': tomorrow.strftime('%A'),
                    **tomorrow_info
                },
                'ramp_settings': {
                    'target_mw': constants.SUMMER_OXPH_TARGET_MW,
                    'min_mw': constants.OXPH_MIN_MW,
                    'ramp_rate_mw_per_min': constants.OXPH_RAMP_RATE_MW_PER_MIN
                }
            })

        except Exception as e:
            logger.error(f"Error getting rafting times: {e}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            return Response({
                'error': 'Failed to get rafting times',
                'detail': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class RampCalculatorView(APIView):
    """API endpoint for calculating OXPH ramp timing"""

    def post(self, request):
        """Calculate when to adjust OXPH setpoint for a given target"""
        try:
            # Import optimization modules
            current_dir = Path(__file__).resolve().parent
            project_root = current_dir.parent.parent

            if str(project_root) not in sys.path:
                sys.path.insert(0, str(project_root))

            import abay_opt.constants as constants

            # Get input parameters
            current_mw = float(request.data.get('current_mw', constants.OXPH_MIN_MW))
            target_mw = float(request.data.get('target_mw', constants.SUMMER_OXPH_TARGET_MW))
            target_time_str = request.data.get('target_time')  # Format: "HH:MM"
            target_date_str = request.data.get('target_date', timezone.now().date().strftime('%Y-%m-%d'))

            if not target_time_str:
                return Response({
                    'error': 'target_time is required (HH:MM format)'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Parse target time
            try:
                target_time = datetime.strptime(target_time_str, '%H:%M').time()
                target_date = datetime.strptime(target_date_str, '%Y-%m-%d').date()
            except ValueError:
                return Response({
                    'error': 'Invalid time format. Use HH:MM for time and YYYY-MM-DD for date'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Calculate ramp time needed
            mw_difference = target_mw - current_mw
            ramp_rate = constants.OXPH_RAMP_RATE_MW_PER_MIN

            if mw_difference <= 0:
                return Response({
                    'status': 'success',
                    'message': 'No ramp up needed - current MW is already at or above target',
                    'current_mw': current_mw,
                    'target_mw': target_mw,
                    'adjustment_needed': False
                })

            ramp_minutes = mw_difference / ramp_rate if ramp_rate > 0 else 0

            # Calculate when adjustment should be made
            target_datetime = datetime.combine(target_date, target_time)
            adjustment_datetime = target_datetime - timedelta(minutes=ramp_minutes)

            # Format times nicely
            adjustment_time = adjustment_datetime.time()

            return Response({
                'status': 'success',
                'calculation': {
                    'current_mw': current_mw,
                    'target_mw': target_mw,
                    'mw_increase_needed': round(mw_difference, 2),
                    'ramp_rate_mw_per_min': ramp_rate,
                    'ramp_duration_minutes': round(ramp_minutes, 1),
                    'ramp_duration_formatted': f"{int(ramp_minutes // 60):02d}:{int(ramp_minutes % 60):02d}",
                    'target_time': target_time_str,
                    'target_date': target_date_str,
                    'adjustment_time': adjustment_time.strftime('%H:%M'),
                    'adjustment_datetime': adjustment_datetime.strftime('%Y-%m-%d %H:%M'),
                    'adjustment_needed': True
                }
            })

        except ValueError as ve:
            return Response({
                'error': 'Invalid input values',
                'detail': str(ve)
            }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Error calculating ramp timing: {e}")
            return Response({
                'error': 'Failed to calculate ramp timing',
                'detail': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

def health_check(request):
    """Simple health check endpoint"""
    return JsonResponse({
        'status': 'healthy',
        'timestamp': timezone.now().isoformat(),
        'optimization_modules_loaded': _optimization_modules_loaded
    })

def dashboard_data(request):
    """Consolidated dashboard data endpoint"""
    dashboard_view = DashboardView()
    return dashboard_view.get(request)


def _load_run_results_dataframe(run):
    """Load the combined optimization results DataFrame for a run."""

    if not run:
        raise ValueError('Run results not available for this optimization run')

    result_qs = OptimizationResult.objects.filter(optimization_run=run).order_by('timestamp_utc')

    if result_qs.exists():
        records = list(result_qs.values(
            'timestamp_utc',
            'oxph_setpoint_target',
            'oxph_generation_mw',
            'oxph_outflow_cfs',
            'r26_flow_cfs',
            'r5l_flow_cfs',
            'r4_flow_cfs',
            'r30_flow_cfs',
            'r20_minus_r5l_cfs',
            'mfra_mw',
            'mf1_2_mw',
            'mf1_2_cfs',
            'abay_elev_ft',
            'abay_af',
            'abay_float_ft',
            'expected_abay_ft',
            'expected_abay_af',
            'abay_error_cfs',
            'abay_error_af',
            'setpoint_adjust_time_pt',
            'ccs_mode',
            'head_limit_mw',
            'bias_cfs',
            'abay_net_flow_cfs',
            'abay_net_expected_cfs',
            'abay_net_actual_cfs',
            'abay_net_expected_cfs_no_bias',
            'abay_net_expected_cfs_with_bias',
            'regulated_component_cfs',
            'mfra_side_reduction_mw',
            'adjust_oxph_needed',
            'is_head_loss_limited',
            'spill_volume_af',
            'actual_oxph_mw',
            'actual_abay_elev_ft',
            'abay_delta_af',
            'is_forecast',
        ))

        df = pd.DataFrame.from_records(records)

        if df.empty:
            # Fall back to CSV if database rows failed to load for some reason
            return _load_run_results_from_csv(run)

        df['timestamp_end'] = pd.to_datetime(df.pop('timestamp_utc'), utc=True)
        df.set_index('timestamp_end', inplace=True)

        rename_map = {
            'oxph_setpoint_target': 'OXPH_setpoint_MW',
            'oxph_generation_mw': 'OXPH_generation_MW',
            'oxph_outflow_cfs': 'OXPH_outflow_cfs',
            'r26_flow_cfs': 'R26_Flow',
            'r5l_flow_cfs': 'R5L_Flow',
            'r4_flow_cfs': 'R4_Flow',
            'r30_flow_cfs': 'R30_Flow',
            'mfra_mw': 'MFRA_MW',
            'mf1_2_mw': 'MF_1_2_MW',
            'mf1_2_cfs': 'MF_1_2_cfs',
            'abay_elev_ft': 'ABAY_ft',
            'abay_af': 'ABAY_af',
            'abay_float_ft': 'FLOAT_FT',
            'expected_abay_ft': 'Expected_ABAY_ft',
            'expected_abay_af': 'Expected_ABAY_af',
            'abay_error_cfs': 'abay_error_cfs',
            'abay_error_af': 'abay_error_af',
            'setpoint_adjust_time_pt': 'setpoint_change_time',
            'ccs_mode': 'Mode',
            'head_limit_mw': 'Head_limit_MW',
            'bias_cfs': 'bias_cfs',
            'abay_net_flow_cfs': 'ABAY_net_flow_cfs',
            'abay_net_expected_cfs': 'ABAY_NET_expected_cfs',
            'abay_net_actual_cfs': 'ABAY_NET_actual_cfs',
            'abay_net_expected_cfs_no_bias': 'ABAY_NET_expected_cfs_no_bias',
            'abay_net_expected_cfs_with_bias': 'ABAY_NET_expected_cfs_with_bias',
            'regulated_component_cfs': 'Regulated_component_cfs',
            'mfra_side_reduction_mw': 'MFRA_side_reduction_MW',
            'adjust_oxph_needed': 'Adjust_OXPH_Needed',
            'is_head_loss_limited': 'Is_Head_Loss_Limited',
            'spill_volume_af': 'Spill_Volume_AF_Recalc',
            'actual_oxph_mw': 'OXPH_generation_MW_hist',
            'actual_abay_elev_ft': 'Afterbay_Elevation_Actual',
            'abay_delta_af': 'ABAY_Delta_AF_Sim',
            'is_forecast': 'is_forecast',
        }

        df.rename(columns=rename_map, inplace=True)

        if 'r20_minus_r5l_cfs' in df.columns:
            r5l = df.get('R5L_Flow')
            r20_vals = pd.to_numeric(df['r20_minus_r5l_cfs'], errors='coerce').fillna(0.0)
            if r5l is not None:
                r5l_vals = pd.to_numeric(r5l, errors='coerce').fillna(0.0)
            else:
                r5l_vals = 0.0
            df['R20_Flow'] = r20_vals + r5l_vals
            df.drop(columns=['r20_minus_r5l_cfs'], inplace=True)

        if 'setpoint_change_time' in df.columns:
            df['setpoint_change_time'] = df['setpoint_change_time'].apply(
                lambda value: value.isoformat() if pd.notna(value) else None
            )

        if 'is_forecast' in df.columns:
            df['is_forecast'] = df['is_forecast'].fillna(False).astype(bool)

        # Provide a convenience column matching the CSV output
        df['timestamp_end'] = df.index

        df.sort_index(inplace=True)
        return df

    return _load_run_results_from_csv(run)


def _load_run_results_from_csv(run):
    if not run or not run.result_file_path:
        raise ValueError('Run results not available for this optimization run')

    if not os.path.exists(run.result_file_path):
        raise FileNotFoundError(f"Results file not found at {run.result_file_path}")

    df = pd.read_csv(run.result_file_path, index_col=0, parse_dates=True)

    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)

    if df.index.tz is None:
        df.index = df.index.tz_localize('UTC')
    else:
        df.index = df.index.tz_convert('UTC')

    if 'timestamp_end' not in df.columns:
        df['timestamp_end'] = df.index

    if 'is_forecast' not in df.columns:
        if 'Expected_ABAY_ft' in df.columns:
            df['is_forecast'] = df['Expected_ABAY_ft'].isna()
        else:
            df['is_forecast'] = False

    df.sort_index(inplace=True)
    return df


@login_required
def profile_view(request):
    """User profile page for updating personal info and preferences"""

    # Get or create user profile
    profile, created = UserProfile.objects.get_or_create(user=request.user)

    if request.method == 'POST':
        try:
            # Update user basic info
            request.user.first_name = request.POST.get('first_name', '')
            request.user.last_name = request.POST.get('last_name', '')
            request.user.email = request.POST.get('email', '')
            request.user.save()

            # Update profile info
            profile.phone_number = request.POST.get('phone_number', '')
            profile.email_notifications = request.POST.get('email_notifications') == 'on'
            profile.sms_notifications = request.POST.get('sms_notifications') == 'on'
            profile.browser_notifications = request.POST.get('browser_notifications') == 'on'
            profile.default_tab = request.POST.get('default_tab', 'dashboard')
            profile.refresh_interval = int(request.POST.get('refresh_interval', 60))
            profile.dark_mode = request.POST.get('dark_mode') == 'on'

            # Validate phone number if SMS notifications are enabled
            if profile.sms_notifications and not profile.phone_number:
                messages.warning(request, 'Phone number is required for SMS notifications')
                profile.sms_notifications = False

            profile.save()

            # Handle password change
            current_password = request.POST.get('current_password')
            new_password = request.POST.get('new_password')
            confirm_password = request.POST.get('confirm_password')

            if current_password and new_password:
                if new_password == confirm_password:
                    if request.user.check_password(current_password):
                        request.user.set_password(new_password)
                        request.user.save()
                        update_session_auth_hash(request, request.user)
                        messages.success(request, 'Password changed successfully')
                    else:
                        messages.error(request, 'Current password is incorrect')
                else:
                    messages.error(request, 'New passwords do not match')

            messages.success(request, 'Profile updated successfully')
            return redirect('/')

        except Exception as e:
            logger.error(f"Error updating profile: {e}")
            messages.error(request, 'Error updating profile. Please try again.')

    context = {
        'user': request.user,
        'profile': profile,
    }

    return render(request, 'profile.html', context)


@login_required
def logout_confirmation_view(request):
    """Show logout confirmation page"""
    if request.method == 'POST':
        logout(request)
        return redirect('login')
    return render(request, 'logout_confirmation.html')
