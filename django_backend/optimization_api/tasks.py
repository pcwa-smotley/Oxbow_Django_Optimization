# django_backend/optimization_api/tasks.py

import os
import sys
import logging
import traceback
import time
from datetime import datetime, date, timezone, timedelta
import re
from pathlib import Path
import numpy as np
import pandas as pd
import json
from decimal import Decimal

# Only import Celery if it's available
try:
    from celery import shared_task, current_task

    CELERY_AVAILABLE = True
except ImportError:
    CELERY_AVAILABLE = False


    # Create a dummy decorator for when Celery isn't available
    def shared_task(bind=False):
        def decorator(func):
            return func

        return decorator

from django.utils import timezone
from django.conf import settings

logger = logging.getLogger(__name__)


def _format_failure_meta(exc: Exception, error_msg: str) -> dict:
    """Create a Celery-compatible metadata payload for task failures."""
    return {
        'exc_type': type(exc).__name__,
        'exc_message': str(exc),
        'exc_module': type(exc).__module__,
        'error': error_msg,
    }


def _serialize_diagnostics(diagnostics):
    """Convert solver diagnostics to a JSON-serializable dict."""
    try:
        serialized = json.loads(json.dumps(diagnostics, default=str))
        # Ensure we always return a dict so callers can safely access .get()
        if isinstance(serialized, dict):
            return serialized
        return {"raw": serialized}
    except Exception:
        logger.exception("Failed to serialize solver diagnostics")
        return {}


def load_optimization_modules():
    """Safely load abay_opt modules"""
    try:
        # Add the parent directory to sys.path
        current_dir = Path(__file__).resolve().parent
        project_root = current_dir.parent.parent
        abay_opt_path = project_root / 'abay_opt'
        logger.info(f"Looking for modules at: {abay_opt_path}")
        logger.info(f"Directory exists: {abay_opt_path.exists()}")

        if not abay_opt_path.exists():
            logger.error(f"abay_opt directory not found at: {abay_opt_path}")
            return None, None, None, None

        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))

        # Import the engine modules
        import abay_opt.build_inputs as build_inputs
        import abay_opt.optimizer as optimizer
        import abay_opt.cli as cli
        import abay_opt.constants as optimization_constants

        logger.info("Successfully loaded abay_opt modules")
        return build_inputs, optimizer, cli, optimization_constants

    except ImportError as e:
        logger.warning(f"Could not import optimization modules: {e}")
        return None, None, None, None
    except Exception as e:
        logger.error(f"Unexpected error loading optimization modules: {e}")
        return None, None, None, None


@shared_task(bind=True)
def run_optimization_task(self, run_id, optimization_ui_params=None):
    """
    Background task to run the ABAY reservoir optimization
    Only runs if Celery is available, otherwise returns simulation
    """
    if not CELERY_AVAILABLE:
        logger.warning("Celery not available - task cannot run")
        return {'error': 'Celery not available'}

    from .models import OptimizationRun, OptimizationResult

    try:
        # Get the optimization run
        run = OptimizationRun.objects.get(id=run_id)

        # Update status
        run.status = 'running'
        run.started_at = timezone.now()
        run.save()

        # Update progress
        self.update_state(
            state='PROGRESS',
            meta={'current': 0, 'total': 100, 'status': 'Initializing optimization...'}
        )
        run.update_progress('Initializing optimization...', 5)

        # Try to load optimization modules
        build_inputs, optimizer, cli, optimization_constants = load_optimization_modules()

        if not build_inputs:
            # Run simulation instead
            logger.warning("Running simulation - optimization modules not available")
            return _run_simulation(self, run)
        # Continue with real optimization if modules are available
        self.update_state(
            state='PROGRESS',
            meta={'current': 20, 'total': 100, 'status': 'Starting optimization pipeline...'}
        )
        run.update_progress('Starting optimization pipeline...', 20)

        # Prepare optimization parameters
        optimization_params = run.get_effective_parameters()

        # Apply parameter overrides to constants module
        if optimization_params:
            for param_name, param_value in optimization_params.items():
                if hasattr(optimization_constants, param_name):
                    # Special handling for time parameters
                    if param_name in ['SUMMER_TARGET_START_TIME', 'SUMMER_TARGET_END_TIME']:
                        if isinstance(param_value, str):
                            # Convert string time to time object
                            from datetime import time
                            try:
                                # Handle both 'HH:MM' and 'HH:MM:SS' formats
                                if len(param_value.split(':')) == 2:
                                    hour, minute = map(int, param_value.split(':'))
                                    param_value = time(hour, minute)
                                else:
                                    hour, minute, second = map(int, param_value.split(':'))
                                    param_value = time(hour, minute, second)
                                logger.info(f"Converted {param_name} from string to time: {param_value}")
                            except ValueError as e:
                                logger.error(f"Failed to convert time string {param_value}: {e}")
                                continue

                    setattr(optimization_constants, param_name, param_value)
                    logger.info(f"Set {param_name} = {param_value} (type: {type(param_value)})")

        run = OptimizationRun.objects.get(id=run_id)

        # Fetch input data for the optimization
        self.update_state(
            state='PROGRESS',
            meta={'current': 40, 'total': 100, 'status': 'Fetching input data...'}
        )
        run.update_progress('Fetching input data...', 40)

        try:
            historical_start = None
            if run.run_mode == 'historical' and run.historical_start_date:
                hist_datetime = datetime.combine(run.historical_start_date, datetime.min.time())
                historical_start = hist_datetime.strftime('%Y-%m-%dT%H:%M')

            lookback_df, forecast_df, initial_state_returned, r_bias_cfs, mfra_source = build_inputs.build_inputs(
                horizon_hours=72,
                forecast_source=run.forecast_source,
                historical_start_pt=historical_start,
            )

            # Store MFRA forecast source in run metadata
            cp = run.custom_parameters or {}
            cp['mfra_source'] = mfra_source
            run.custom_parameters = cp
            run.save(update_fields=['custom_parameters'])

            # Notify that input data has been loaded
            self.update_state(
                state='PROGRESS',
                meta={'current': 55, 'total': 100, 'status': 'Input data loaded'}
            )
            run.update_progress('Input data loaded', 55)

            cfg = optimizer.OptimizeConfig(
                min_elev_ft=optimization_constants.ABAY_MIN_ELEV_FT,
                # Updated constant name to match abay_opt.constants
                float_buffer_ft=getattr(
                    optimization_constants,
                    'ABAY_MAX_ELEV_BUFFER_FT',
                    0.5,
                ),
                smoothing_weight_day=getattr(
                    optimization_constants, 'SMOOTHING_WEIGHT_DAY', 1.0
                ),
                smoothing_weight_night=getattr(
                    optimization_constants, 'SMOOTHING_WEIGHT_NIGHT', 10.0
                ),
                summer_setpoint_floor_mw=getattr(
                    optimization_constants, 'SUMMER_OXPH_TARGET_MW', 6.0
                ),
                summer_tracking_weight=getattr(
                    optimization_constants, 'SUMMER_TRACKING_WEIGHT', 1000.0
                ),
                summer_floor_penalty=getattr(
                    optimization_constants, 'SUMMER_FLOOR_PENALTY', 1e6
                ),
            )

            initial_elev_ft = float(lookback_df['Afterbay_Elevation'].iloc[-1])
            initial_gen_mw = float(lookback_df['Oxbow_Power'].iloc[-1])
            smoothing_weights = forecast_df['smooth_weight'].tolist()
            morning_flags = forecast_df['is_summer_window'].tolist()

            # Solve the optimization problem
            self.update_state(
                state='PROGRESS',
                meta={'current': 60, 'total': 100, 'status': 'Solving optimization...'}
            )
            run.update_progress('Solving optimization...', 60)

            result_df, diagnostics = optimizer.build_and_solve(
                forecast_df=forecast_df,
                initial_elev_ft=initial_elev_ft,
                initial_gen_mw=initial_gen_mw,
                smoothing_weights=smoothing_weights,
                morning_window_flags=morning_flags,
                cfg=cfg
            )

            # Optimization solved, begin post-processing
            self.update_state(
                state='PROGRESS',
                meta={'current': 75, 'total': 100, 'status': 'Generating output...'}
            )
            run.update_progress('Generating output...', 75)

            try:
                s_over, change_times, g_avg = cli.compute_setpoint_change_annotations(
                    idx_utc=result_df.index,
                    g_end=result_df['OXPH_generation_MW'],
                    s_target=result_df['OXPH_setpoint_MW'],
                    initial_gen_mw=initial_gen_mw,
                    ramp_mw_per_min=optimization_constants.OXPH_RAMP_RATE_MW_PER_MIN,
                    tz_pt=optimization_constants.PACIFIC_TZ,
                )
            except Exception as annot_error:
                logger.warning(
                    "Setpoint change annotations failed, using defaults: %s (idx_utc len=%d, initial_gen_mw=%s)",
                    annot_error,
                    len(result_df.index),
                    initial_gen_mw,
                )
                s_over = result_df['OXPH_setpoint_MW']
                change_times = pd.Series([''] * len(result_df), index=result_df.index)
                g_avg = result_df['OXPH_generation_MW']

            result_df['OXPH_setpoint_MW'] = s_over.values
            result_df['OXPH_generation_MW'] = g_avg.values
            result_df['setpoint_change_time'] = change_times.values

            # Build final combined DataFrame using CLI helper
            final_output_df = cli.generate_final_output(
                lookback_df, forecast_df, result_df, r_bias_cfs
            )

            # Notify that result compilation is underway
            self.update_state(
                state='PROGRESS',
                meta={'current': 80, 'total': 100, 'status': 'Compiling results...'}
            )
            run.update_progress('Compiling results...', 80)

            historical_lookback_df = lookback_df
            diagnostics = diagnostics or {}
            main_results_df = final_output_df

            logger.info(
                f"Processing optimization results with {len(main_results_df)} rows"
            )
            logger.info(
                f"Date range: {main_results_df.index[0]} to {main_results_df.index[-1]}"
            )

        except Exception as opt_error:
            error_msg = f"Optimization pipeline failed: {str(opt_error)}"
            logger.error(f"{error_msg}\n{traceback.format_exc()}")
            run.status = 'failed'
            run.error_message = error_msg
            run.completed_at = timezone.now()
            run.save()
            return {'error': error_msg}

        # Process results
        self.update_state(
            state='PROGRESS',
            meta={'current': 90, 'total': 100, 'status': 'Processing results...'}
        )
        run.update_progress('Processing results...', 90)

        # REMOVED THE PROBLEMATIC BLOCK THAT WAS OVERWRITING THE DATA

        # Save results to database (optional - can be memory intensive)
        # This function can be commented out if needed.
        _save_optimization_results(run, main_results_df)

        # Calculate summary statistics (use forecast data only for stats)
        summary_stats = _calculate_summary_statistics(final_output_df)
        run.total_spillage_af = summary_stats.get('total_spillage_af')
        run.avg_oxph_utilization_pct = summary_stats.get('avg_oxph_utilization_pct')
        run.peak_elevation_ft = summary_stats.get('peak_elevation_ft')
        run.min_elevation_ft = summary_stats.get('min_elevation_ft')
        run.r_bias_cfs = r_bias_cfs  # Use the r_bias from the optimization results
        serialized_diagnostics = _serialize_diagnostics(diagnostics)
        run.solver_diagnostics = serialized_diagnostics
        solver_status = serialized_diagnostics.get('status') if isinstance(serialized_diagnostics, dict) else None

        # Save results file if output directory is configured
        if hasattr(settings, 'ABAY_OPTIMIZATION') and settings.ABAY_OPTIMIZATION.get('OUTPUT_DIR'):
            output_dir = Path(settings.ABAY_OPTIMIZATION['OUTPUT_DIR'])
            output_dir.mkdir(parents=True, exist_ok=True)

            filename = f"optimization_run_{run.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            file_path = output_dir / filename

            # Save the combined results (historical + forecast)
            main_results_df.to_csv(file_path)

            # Also save separate files for clarity
            if not historical_lookback_df.empty:
                historical_file = output_dir / f"historical_only_{run.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
                historical_lookback_df.to_csv(historical_file)
                logger.info(f"Saved historical data to: {historical_file}")

            if not final_output_df.empty:
                forecast_file = output_dir / f"forecast_only_{run.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
                final_output_df.to_csv(forecast_file)
                logger.info(f"Saved forecast data to: {forecast_file}")

            run.result_file_path = str(file_path)
            logger.info(f"Saved combined optimization results to: {file_path}")

        # Mark as completed
        run.status = 'completed'
        run.completed_at = timezone.now()
        run.progress_percentage = 100
        run.progress_message = 'Optimization completed successfully'
        run.save()

        # Final progress update
        self.update_state(
            state='SUCCESS',
            meta={'current': 100, 'total': 100, 'status': 'Optimization completed successfully!'}
        )

        logger.info(f"Optimization run {run_id} completed successfully")

        return {
            'status': 'completed',
            'run_id': run_id,
            'summary': summary_stats,
            'total_data_points': len(main_results_df),
            'solver_status': solver_status
        }

    except Exception as e:
        error_msg = f"Unexpected error in optimization task: {str(e)}"
        logger.error(f"{error_msg}\n{traceback.format_exc()}")

        try:
            run = OptimizationRun.objects.get(id=run_id)
            run.status = 'failed'
            run.error_message = error_msg
            run.completed_at = timezone.now()
            run.save()
        except:
            pass

        if CELERY_AVAILABLE:
            self.update_state(
                state='FAILURE',
                meta=_format_failure_meta(e, error_msg)
            )

        return {'error': error_msg}


def _run_simulation(task, run):
    """Run a simulation when optimization modules aren't available"""
    try:
        # Simulate optimization steps
        steps = [
            (10, 'Fetching PI data...'),
            (20, 'Loading forecast data...'),
            (40, 'Setting up optimization problem...'),
            (60, 'Solving optimization...'),
            (80, 'Recalculating state...'),
            (95, 'Finalizing results...'),
        ]

        for progress, message in steps:
            if CELERY_AVAILABLE and hasattr(task, 'update_state'):
                task.update_state(
                    state='PROGRESS',
                    meta={'current': progress, 'total': 100, 'status': message}
                )
            run.update_progress(message, progress)
            time.sleep(1)  # Simulate work

        # Generate fake summary statistics
        import random
        summary_stats = {
            'total_spillage_af': round(random.uniform(0, 50), 1),
            'avg_oxph_utilization_pct': round(random.uniform(60, 90), 1),
            'peak_elevation_ft': round(1170 + random.uniform(1, 4), 2),
            'min_elevation_ft': round(1168 + random.uniform(0, 2), 2),
            'r_bias_cfs': round(random.uniform(-5, 5), 2),
        }

        # Update run with simulated results
        run.total_spillage_af = summary_stats['total_spillage_af']
        run.avg_oxph_utilization_pct = summary_stats['avg_oxph_utilization_pct']
        run.peak_elevation_ft = summary_stats['peak_elevation_ft']
        run.min_elevation_ft = summary_stats['min_elevation_ft']
        run.r_bias_cfs = summary_stats['r_bias_cfs']
        run.status = 'completed'
        run.completed_at = timezone.now()
        run.progress_percentage = 100
        run.progress_message = 'Simulation completed successfully'
        run.save()

        if CELERY_AVAILABLE and hasattr(task, 'update_state'):
            task.update_state(
                state='SUCCESS',
                meta={'current': 100, 'total': 100, 'status': 'Simulation completed!'}
            )

        logger.info(f"Simulation run {run.id} completed")

        return {
            'status': 'completed',
            'run_id': run.id,
            'summary': summary_stats,
            'simulation_mode': True
        }

    except Exception as e:
        error_msg = f"Simulation failed: {str(e)}"
        logger.error(error_msg)
        run.status = 'failed'
        run.error_message = error_msg
        run.completed_at = timezone.now()
        run.save()
        return {'error': error_msg}


def _save_optimization_results(run, results_df):
    """
    Save optimization results to the database
    WARNING: This can be memory intensive for large datasets
    """
    from .models import OptimizationResult

    logger.info(f"Saving {len(results_df)} optimization result records to database")

    # Clear any existing results for this run
    OptimizationResult.objects.filter(optimization_run=run).delete()

    # Prepare batch insert
    result_objects = []

    for idx, (timestamp, row) in enumerate(results_df.iterrows()):
        # Convert timestamp to UTC if needed
        if hasattr(timestamp, 'tz_convert'):
            timestamp_utc = timestamp.tz_convert('UTC')
        else:
            timestamp_utc = timestamp

        # Create result object
        r20_val = _safe_float(row.get('R20_Flow'))
        r5l_val = _safe_float(row.get('R5L_Flow'))
        r20_minus_r5l = (r20_val or 0) - (r5l_val or 0)

        result_obj = OptimizationResult(
            optimization_run=run,
            timestamp_utc=timestamp_utc,

            # Input data
            r4_flow_cfs=_safe_float(row.get('R4_Forecast_CFS') or row.get('R4_Flow')),
            r30_flow_cfs=_safe_float(row.get('R30_Forecast_CFS') or row.get('R30_Flow')),
            mfra_mw=_safe_float(
                row.get('MFRA_MW_forecast')
                or row.get('MFRA_Forecast_MW')
                or row.get('MFRA_MW')
            ),
            r20_minus_r5l_cfs=r20_minus_r5l,
            r5l_flow_cfs=r5l_val,
            r26_flow_cfs=_safe_float(row.get('R26_Flow')),
            ccs_mode=_safe_int(row.get('Mode', 0)),
            abay_float_ft=_safe_float(row.get('FLOAT_FT')),

            # Optimization results
            oxph_generation_mw=_safe_float(row.get('OXPH_generation_MW')),
            abay_elev_ft=_safe_float(row.get('ABAY_ft')),
            abay_af=_safe_float(row.get('ABAY_af')),

            # Diagnostic data
            mf1_2_mw=_safe_float(row.get('MF1_2_MW_Sim') or row.get('MF_1_2_MW')),
            mf1_2_cfs=_safe_float(row.get('MF1_2_CFS_Sim') or row.get('MF_1_2_cfs')),
            oxph_outflow_cfs=_safe_float(row.get('OXPH_CFS_Sim') or row.get('OXPH_outflow_cfs')),
            abay_delta_af=_safe_float(row.get('ABAY_Delta_AF_Sim') or row.get('abay_error_af')),
            abay_net_flow_cfs=_safe_float(
                row.get('ABAY_Net_Flow_CFS_Recalc')
                or row.get('ABAY_NET_actual_cfs')
                or row.get('ABAY_NET_expected_cfs_with_bias')
            ),
            spill_volume_af=_safe_float(row.get('Spill_Volume_AF_Recalc')),
            abay_net_expected_cfs=_safe_float(row.get('ABAY_NET_expected_cfs')),
            abay_net_actual_cfs=_safe_float(row.get('ABAY_NET_actual_cfs')),
            head_limit_mw=_safe_float(row.get('Head_limit_MW')),
            regulated_component_cfs=_safe_float(row.get('Regulated_component_cfs')),
            mfra_side_reduction_mw=_safe_float(row.get('MFRA_side_reduction_MW')),
            bias_cfs=_safe_float(row.get('bias_cfs')),
            expected_abay_ft=_safe_float(row.get('Expected_ABAY_ft')),
            expected_abay_af=_safe_float(row.get('Expected_ABAY_af')),
            abay_net_expected_cfs_no_bias=_safe_float(row.get('ABAY_NET_expected_cfs_no_bias')),
            abay_net_expected_cfs_with_bias=_safe_float(row.get('ABAY_NET_expected_cfs_with_bias')),
            is_forecast=_safe_bool(row.get('is_forecast')),

            # Setpoint guidance
            adjust_oxph_needed=str(row.get('Adjust_OXPH_Needed', '')),
            oxph_setpoint_target=_safe_float(
                row.get('OXPH_setpoint_MW') or row.get('OXPH_Setpoint_Target')
            ),
            setpoint_adjust_time_pt=_safe_datetime(
                row.get('setpoint_change_time') or row.get('Setpoint_Adjust_Time_PT')
            ),
            is_head_loss_limited=bool(row.get('Is_Head_Loss_Limited', False)),

            # Historical comparison (if available)
            actual_oxph_mw=_safe_float(row.get('Oxbow_Power_Actual') or row.get('OXPH_generation_MW_hist')),
            actual_abay_elev_ft=_safe_float(row.get('Afterbay_Elevation_Actual')),
            abay_error_af=_safe_float(row.get('ABAY_Error_AF') or row.get('abay_error_af')),
            abay_error_cfs=_safe_float(row.get('ABAY_Error_CFS') or row.get('abay_error_cfs')),
            raw_values=_serialize_result_row(row, timestamp_utc),
        )

        result_objects.append(result_obj)

        # Batch insert every 1000 records to avoid memory issues
        if len(result_objects) >= 1000:
            OptimizationResult.objects.bulk_create(result_objects)
            result_objects = []
            logger.info(f"Saved batch of results (processed {idx + 1}/{len(results_df)} records)")

    # Insert remaining records
    if result_objects:
        OptimizationResult.objects.bulk_create(result_objects)

    logger.info(f"Saved all {len(results_df)} optimization result records")


def _calculate_summary_statistics(results_df):
    """Calculate summary statistics from optimization results"""
    try:
        import pandas as pd

        # Make sure we have a DataFrame with data
        if results_df is None or results_df.empty:
            logger.warning("Cannot calculate statistics from empty DataFrame")
            return {}

        if not hasattr(results_df, 'columns'):
            logger.error(f"Expected DataFrame for statistics, got {type(results_df)}")
            return {}

        logger.info(f"Calculating statistics from DataFrame with columns: {list(results_df.columns)}")

        stats = {}

        # Spillage statistics (if available)
        if 'Spill_Volume_AF_Recalc' in results_df.columns:
            spill_data = results_df['Spill_Volume_AF_Recalc'].fillna(0)
            stats['total_spillage_af'] = float(spill_data.sum())
            stats['max_hourly_spillage_af'] = float(spill_data.max())

        # OXPH utilization
        oxph_col = None
        if 'OXPH_generation_MW' in results_df.columns:
            oxph_col = 'OXPH_generation_MW'
        elif 'OXPH_Schedule_MW' in results_df.columns:
            oxph_col = 'OXPH_Schedule_MW'
        if oxph_col:
            oxph_data = results_df[oxph_col].fillna(0)
            max_mw = 5.8  # Could get from constants
            avg_utilization = (oxph_data.mean() / max_mw) * 100
            stats['avg_oxph_utilization_pct'] = float(avg_utilization)
            stats['max_oxph_mw'] = float(oxph_data.max())
            stats['min_oxph_mw'] = float(oxph_data.min())

        # Elevation statistics
        elev_col = None
        if 'ABAY_ft' in results_df.columns:
            elev_col = 'ABAY_ft'
        elif 'Simulated_ABAY_Elev_FT' in results_df.columns:
            elev_col = 'Simulated_ABAY_Elev_FT'
        if elev_col:
            elev_data = results_df[elev_col].dropna()
            if not elev_data.empty:
                stats['peak_elevation_ft'] = float(elev_data.max())
                stats['min_elevation_ft'] = float(elev_data.min())
                stats['avg_elevation_ft'] = float(elev_data.mean())

        # Flow statistics
        if 'ABAY_Net_Flow_CFS_Recalc' in results_df.columns:
            flow_data = results_df['ABAY_Net_Flow_CFS_Recalc'].dropna()
            if not flow_data.empty:
                stats['avg_net_flow_cfs'] = float(flow_data.mean())
                stats['max_net_flow_cfs'] = float(flow_data.max())
                stats['min_net_flow_cfs'] = float(flow_data.min())

        # Error statistics (for historical runs)
        if 'ABAY_Error_CFS' in results_df.columns:
            error_data = results_df['ABAY_Error_CFS'].dropna()
            if not error_data.empty:
                stats['r_bias_cfs'] = float(error_data.mean())
                stats['rmse_cfs'] = float((error_data ** 2).mean() ** 0.5)

        logger.info(f"Calculated summary statistics: {stats}")
        return stats

    except Exception as e:
        logger.error(f"Error calculating summary statistics: {e}")
        return {}


# Add this function to your existing tasks.py

@shared_task(bind=True)
def fetch_price_data_task(self, node_id='20000002064', use_cache=True):
    """
    Background task to fetch electricity price data from YES Energy
    """
    if not CELERY_AVAILABLE:
        logger.warning("Celery not available - returning simulated price data")
        return _get_simulated_price_data_sync(node_id)

    try:
        from django.core.cache import cache

        # Check cache first if enabled
        cache_key = f"price_data_{node_id}"
        if use_cache:
            cached_data = cache.get(cache_key)
            if cached_data:
                logger.info(f"Returning cached price data for node {node_id}")
                return cached_data

        # Update progress
        self.update_state(
            state='PROGRESS',
            meta={'current': 10, 'total': 100, 'status': 'Loading YES Energy module...'}
        )

        # Load YES Energy module
        build_inputs, optimizer, cli, optimization_constants = load_optimization_modules()
        if not build_inputs:
            logger.warning("Optimization modules not available, using simulated price data")
            return _get_simulated_price_data_sync(node_id)

        # Import YES Energy module
        try:
            current_dir = Path(__file__).resolve().parent
            project_root = current_dir.parent.parent
            if str(project_root) not in sys.path:
                sys.path.insert(0, str(project_root))

            import abay_opt.yes_energy_grab as yes_energy
        except ImportError as e:
            logger.warning(f"Could not import YES Energy module: {e}")
            return _get_simulated_price_data_sync(node_id)

        # Update progress
        self.update_state(
            state='PROGRESS',
            meta={'current': 30, 'total': 100, 'status': f'Fetching price data for node {node_id}...'}
        )

        # Fetch price data
        config_path = project_root / 'abay_opt' / 'config'
        price_data_df = yes_energy.get_current_electricity_prices(
            node_id=node_id,
            config_file=str(config_path)
        )

        if price_data_df.empty:
            logger.warning("YES Energy API returned empty data")
            return _get_simulated_price_data_sync(node_id)

        # Update progress
        self.update_state(
            state='PROGRESS',
            meta={'current': 70, 'total': 100, 'status': 'Processing price data...'}
        )

        # Convert to JSON-serializable format
        price_data = []
        for idx, row in price_data_df.iterrows():
            price_data.append({
                'timestamp': idx.isoformat(),
                'day_ahead_price': _safe_float(row.get('Day_Ahead_Price')),
                'real_time_price': _safe_float(row.get('Real_Time_Price')),
                'fifteen_min_price': _safe_float(row.get('Fifteen_Min_Price')),
            })

        # Calculate statistics
        stats = yes_energy.get_price_statistics(price_data_df)

        # Prepare result
        result = {
            'status': 'success',
            'node_id': node_id,
            'data_source': 'yes_energy_api',
            'data_count': len(price_data),
            'price_data': price_data,
            'statistics': stats,
            'data_range': {
                'start': price_data_df.index.min().isoformat(),
                'end': price_data_df.index.max().isoformat()
            },
            'fetched_at': timezone.now().isoformat()
        }

        # Cache the result
        if use_cache:
            cache_timeout = getattr(settings, 'ABAY_OPTIMIZATION', {}).get('YES_ENERGY', {}).get(
                'CACHE_TIMEOUT_SECONDS', 300)
            cache.set(cache_key, result, cache_timeout)
            logger.info(f"Cached price data for node {node_id} for {cache_timeout} seconds")

        # Final progress update
        self.update_state(
            state='SUCCESS',
            meta={'current': 100, 'total': 100, 'status': f'Successfully fetched {len(price_data)} price points'}
        )

        logger.info(f"Successfully fetched price data for node {node_id}")
        return result

    except Exception as e:
        error_msg = f"Failed to fetch price data for node {node_id}: {str(e)}"
        logger.error(f"{error_msg}\n{traceback.format_exc()}")

        if CELERY_AVAILABLE:
            self.update_state(
                state='FAILURE',
                meta=_format_failure_meta(e, error_msg)
            )

        # Return simulated data as fallback
        logger.info("Falling back to simulated price data")
        return _get_simulated_price_data_sync(node_id)


def _get_simulated_price_data_sync(node_id):
    """Generate simulated price data synchronously"""
    import random
    import math
    from datetime import timedelta

    logger.info(f"Generating simulated price data for node {node_id}")

    now = timezone.now()
    price_data = []

    for i in range(48):  # 48 hours
        timestamp = now + timedelta(hours=i)

        # Simulate realistic price patterns
        base_price = 45.0
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
        }
    }

    return {
        'status': 'success',
        'node_id': node_id,
        'data_source': 'simulation',
        'data_count': len(price_data),
        'price_data': price_data,
        'statistics': stats,
        'message': 'Using simulated data - YES Energy API not available',
        'fetched_at': timezone.now().isoformat()
    }


# Add this to enhance your existing run_optimization_task
def _enhance_optimization_with_prices(run, optimization_params):
    """
    Enhance optimization with price data if revenue optimization is enabled
    """
    try:
        # Check if price optimization is enabled
        if optimization_params.get('include_price_optimization', False):
            node_id = optimization_params.get('electricity_node_id', '20000002064')

            logger.info(f"Fetching price data for revenue optimization (node: {node_id})")

            # Fetch price data synchronously within the optimization task
            price_result = _get_simulated_price_data_sync(node_id)  # Could be enhanced to call real API

            if price_result and price_result['status'] == 'success':
                # Add price data to the optimization context
                optimization_params['price_data'] = price_result['price_data']
                optimization_params['price_statistics'] = price_result['statistics']

                logger.info(f"Added {price_result['data_count']} price points to optimization")
                return True
            else:
                logger.warning("Could not fetch price data for optimization")
                return False

    except Exception as e:
        logger.error(f"Error enhancing optimization with price data: {e}")
        return False

    return False


# Helper functions for safe data conversion
def _serialize_result_row(row, timestamp_utc=None):
    """Convert a pandas Series row into JSON-serializable primitives."""
    payload = {}

    if timestamp_utc is not None:
        payload['timestamp'] = _normalize_for_json(timestamp_utc)

    if hasattr(row, 'items'):
        for key, value in row.items():
            payload[str(key)] = _normalize_for_json(value)

    return payload


def _normalize_for_json(value):
    """Normalize values so they can be persisted in a JSONField."""
    if value is None:
        return None

    if isinstance(value, dict):
        return {str(k): _normalize_for_json(v) for k, v in value.items()}

    if isinstance(value, (list, tuple, set)):
        return [_normalize_for_json(v) for v in value]

    if isinstance(value, np.ndarray):
        return [_normalize_for_json(v) for v in value.tolist()]

    if isinstance(value, (np.bool_, bool)):
        return bool(value)

    if isinstance(value, pd.Timestamp):
        if pd.isna(value):
            return None
        return value.to_pydatetime().isoformat()

    if isinstance(value, datetime):
        return value.isoformat()

    if isinstance(value, np.datetime64):
        if np.isnat(value):
            return None
        ts = pd.to_datetime(value)
        return ts.to_pydatetime().isoformat()

    if isinstance(value, pd.Timedelta):
        if pd.isna(value):
            return None
        return value.total_seconds()

    if isinstance(value, np.timedelta64):
        if np.isnat(value):
            return None
        return float(value / np.timedelta64(1, 's'))

    if isinstance(value, Decimal):
        return float(value)

    if isinstance(value, (np.integer, )):
        return int(value)

    if isinstance(value, (np.floating, )):
        if np.isnan(value):
            return None
        return float(value)

    if isinstance(value, float):
        if pd.isna(value):
            return None
        return value

    try:
        if pd.isna(value):
            return None
    except Exception:
        pass

    return value


def _safe_float(value):
    """Safely convert value to float, returning None if not possible"""
    if value is None or str(value).lower() in ['nan', 'none', '']:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _safe_int(value):
    """Safely convert value to int, returning None if not possible"""
    if value is None or str(value).lower() in ['nan', 'none', '']:
        return None
    try:
        return int(float(value))  # Convert through float first to handle decimal strings
    except (ValueError, TypeError):
        return None


def _safe_datetime(value):
    """Safely convert value to datetime, returning None if not possible"""
    if value is None or str(value).strip().lower() in ['nan', 'none', '', 'nat']:
        return None
    try:
        # Handle pandas/NumPy timestamp objects
        if hasattr(value, 'to_pydatetime'):
            return value.to_pydatetime()
        if hasattr(value, 'tz_convert'):
            return value.tz_convert('UTC').to_pydatetime()

        # Parse string values – require a full date component
        if isinstance(value, str):
            if not re.search(r'\d{4}-\d{2}-\d{2}', value):
                return None
            parsed = pd.to_datetime(value, errors='coerce')
            if pd.isna(parsed):
                return None
            if hasattr(parsed, 'to_pydatetime'):
                return parsed.to_pydatetime()
            return parsed

        return value
    except (ValueError, TypeError, AttributeError):
        return None


def _safe_bool(value):
    """Safely convert a value to boolean, treating falsy/NaN values as False."""
    if value is None:
        return False

    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {'', '0', 'false', 'no', 'off', 'n'}:
            return False
        if lowered in {'1', 'true', 'yes', 'on', 'y'}:
            return True

    try:
        if pd.isna(value):
            return False
    except TypeError:
        pass

    return bool(value)


# Add these tasks to your existing tasks.py file:

@shared_task(bind=True)
def check_system_alerts(self):
    """
    Periodic task to check system alerts
    This should run every minute or few minutes
    """
    try:
        from .alerting import alerting_service

        logger.info("Starting system alert check...")

        # Update task state
        if CELERY_AVAILABLE:
            self.update_state(
                state='PROGRESS',
                meta={'status': 'Fetching PI data...'}
            )

        # Fetch current system data from PI
        system_data = alerting_service.fetch_current_pi_data()

        if not system_data:
            logger.error("No PI data available for alert checking")
            return {
                'status': 'error',
                'message': 'No PI data available',
                'timestamp': timezone.now().isoformat()
            }

        # Update task state
        if CELERY_AVAILABLE:
            self.update_state(
                state='PROGRESS',
                meta={'status': 'Checking alerts...'}
            )

        # Check all alerts
        triggered_alerts = alerting_service.check_all_alerts(system_data)

        # Log results
        if triggered_alerts:
            logger.info(f"Triggered {len(triggered_alerts)} alerts")
            for alert in triggered_alerts:
                logger.info(
                    f"Alert: {alert['alert_name']} ({alert['severity']}) "
                    f"for user {alert['username']}"
                )

        # Update system status
        from .models import SystemStatus
        SystemStatus.objects.create(
            status='online',
            pi_data_available=True,
            alert_system_active=True,
            status_message=f"Checked {len(system_data)} parameters, triggered {len(triggered_alerts)} alerts",
            last_pi_update=timezone.now()
        )

        return {
            'status': 'success',
            'alerts_checked': True,
            'triggered_count': len(triggered_alerts),
            'triggered_alerts': [
                {
                    'name': alert['alert_name'],
                    'user': alert['username'],
                    'severity': alert['severity']
                } for alert in triggered_alerts
            ],
            'timestamp': timezone.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Error in check_system_alerts task: {str(e)}")

        # Update system status
        try:
            from .models import SystemStatus
            SystemStatus.objects.create(
                status='degraded',
                pi_data_available=False,
                alert_system_active=False,
                status_message=f"Alert check error: {str(e)}"
            )
        except:
            pass

        return {
            'status': 'error',
            'error': str(e),
            'timestamp': timezone.now().isoformat()
        }


@shared_task
def cleanup_old_alert_logs():
    """
    Clean up old alert logs (run daily)
    Keep logs for 30 days by default
    """
    try:
        from .models import AlertLog

        cutoff_date = timezone.now() - timedelta(days=30)
        deleted_count, _ = AlertLog.objects.filter(
            created_at__lt=cutoff_date
        ).delete()

        logger.info(f"Cleaned up {deleted_count} old alert logs")

        return {
            'status': 'success',
            'deleted_count': deleted_count,
            'timestamp': timezone.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Error in cleanup_old_alert_logs task: {str(e)}")
        return {
            'status': 'error',
            'error': str(e),
            'timestamp': timezone.now().isoformat()
        }


@shared_task
def send_alert_summary_email(user_id):
    """
    Send daily/weekly alert summary email to user
    """
    try:
        from django.contrib.auth.models import User
        from django.core.mail import send_mail
        from django.conf import settings
        from .models import AlertLog

        user = User.objects.get(id=user_id)

        # Get alerts from last 24 hours
        since = timezone.now() - timedelta(hours=24)
        recent_alerts = AlertLog.objects.filter(
            user=user,
            created_at__gte=since
        ).order_by('-severity', '-created_at')

        if not recent_alerts.exists():
            logger.info(f"No alerts to summarize for user {user.username}")
            return {
                'status': 'success',
                'message': 'No alerts in period'
            }

        # Build summary
        critical_count = recent_alerts.filter(severity='critical').count()
        warning_count = recent_alerts.filter(severity='warning').count()
        info_count = recent_alerts.filter(severity='info').count()

        subject = f"ABAY Alert Summary - {critical_count} Critical, {warning_count} Warnings"

        body = f"""
ABAY Reservoir Optimization - Daily Alert Summary

Period: {since.strftime('%Y-%m-%d %H:%M')} to {timezone.now().strftime('%Y-%m-%d %H:%M')} PT

Summary:
- Critical Alerts: {critical_count}
- Warnings: {warning_count}
- Info Alerts: {info_count}
- Total: {recent_alerts.count()}

Recent Alerts:
"""

        for alert in recent_alerts[:20]:  # Show top 20
            body += f"""
{alert.created_at.strftime('%H:%M')} - {alert.severity.upper()}: {alert.message}
"""

        if recent_alerts.count() > 20:
            body += f"\n... and {recent_alerts.count() - 20} more alerts"

        body += f"""

View all alerts: {getattr(settings, 'SITE_URL', 'http://localhost:8000')}/alerts

To update your notification preferences: {getattr(settings, 'SITE_URL', 'http://localhost:8000')}/profile
"""

        send_mail(
            subject=subject,
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False
        )

        logger.info(f"Alert summary sent to {user.email}")

        return {
            'status': 'success',
            'alerts_summarized': recent_alerts.count(),
            'sent_to': user.email
        }

    except Exception as e:
        logger.error(f"Error sending alert summary: {str(e)}")
        return {
            'status': 'error',
            'error': str(e)
        }


@shared_task
def test_twilio_connection():
    """
    Test Twilio configuration and connection
    """
    try:
        from django.conf import settings
        from twilio.rest import Client

        if not hasattr(settings, 'TWILIO_ACCOUNT_SID'):
            return {
                'status': 'error',
                'message': 'Twilio credentials not configured'
            }

        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)

        # Test by fetching account info
        account = client.api.accounts(settings.TWILIO_ACCOUNT_SID).fetch()

        return {
            'status': 'success',
            'account_name': account.friendly_name,
            'account_status': account.status,
            'phone_number': getattr(settings, 'TWILIO_PHONE_NUMBER', 'Not configured')
        }

    except Exception as e:
        logger.error(f"Twilio test failed: {str(e)}")
        return {
            'status': 'error',
            'error': str(e)
        }
