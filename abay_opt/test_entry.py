
# abay_opt/test_entry.py

import pandas as pd
import numpy as np

from . import constants
from .build_inputs import build_inputs
from .optimizer import OptimizeConfig, build_and_solve
from .utils import AF_PER_CFS_HOUR
from .physics import (
    oxph_cfs_from_mw_linear, mf12_mw_from_mfra, mf12_cfs_from_mw_quadratic,
    regulated_component_gen, expected_abay_net_cfs, abay_feet_to_af,
    normalize_mode_series
)
from .bias import hourly_abay_error_diagnostics, expected_series_for_lookback

# ------------------------------
# Hard-coded inputs for testing
# ------------------------------
# 1) The date for historical analysis (PT or UTC string). Set to None for "current" analysis.
#HISTORICAL_START = "2025-08-01T00:00"   # e.g., "2025-06-28T00:00" or None
HISTORICAL_START = None   # e.g., "2025-06-28T00:00" or None

# Optional knobs (feel free to edit as needed)
HORIZON_HOURS   = 72
FORECAST_SOURCE = None        # None -> constants.DEFAULT_UPSTREAM_FORECAST_SOURCE
OUTFILE         = "./abay_schedule_test.csv"

# ------------------------------
# Utilities
# ------------------------------
def compute_setpoint_change_annotations(idx_utc, g_end, s_target,
                                        initial_gen_mw, ramp_mw_per_min, tz_pt):
    """
    For each hour-ending UTC timestamp in idx_utc:
      - setpoint_change_time: the latest PT clock time within that hour when
        operators must change the setpoint to meet future end-of-hour targets
        under the ramp constraint.
      - setpoint_override: setpoint value we change *to* in that hour (e.g., rafting floor).
      - g_avg: hour-average generation under a 'latest-start' ramp (head limit is already
        respected by the solver's g_end / constraints).
    """
    he = pd.DatetimeIndex(idx_utc)
    T = len(he)
    g_end = pd.Series(g_end, index=he, dtype=float)
    s_target = pd.Series(s_target, index=he, dtype=float)
    setpoint_override = s_target.copy()
    change_time_str = pd.Series([""] * T, index=he, dtype=object)

    r = float(ramp_mw_per_min)
    g_avg_vals = []
    g_prev = float(initial_gen_mw)
    for t in range(T):
        delta = float(g_end.iloc[t] - g_prev)
        t_need = min(abs(delta) / r, 60.0)
        g_avg_vals.append(g_prev + (t_need / 120.0) * delta)
        g_prev = float(g_end.iloc[t])
    g_avg = pd.Series(g_avg_vals, index=he)

    for h in range(T):
        he_prev = he[h] - pd.Timedelta(hours=1)
        cum = 0.0
        g_left = float(initial_gen_mw) if h == 0 else float(g_end.iloc[h-1])
        for t in range(h, T):
            g_right = float(g_end.iloc[t])
            step_minutes = abs(g_right - g_left) / r
            cum += step_minutes
            latest_start = he[t] - pd.Timedelta(minutes=cum)
            if he_prev < latest_start <= he[h]:
                change_time_str.iloc[h] = latest_start.tz_convert(tz_pt).strftime("%I:%M %p")
                setpoint_override.iloc[h] = max(setpoint_override.iloc[h], float(s_target.iloc[t]))
                break
            g_left = g_right
    return setpoint_override, change_time_str, g_avg


def run():
    # ------------------------------
    # Build inputs (historical mode defaults to actuals-as-forecast)
    # ------------------------------
    lookback, forecast, state, bias_cfs, _mfra_source = build_inputs(
        horizon_hours=HORIZON_HOURS,
        forecast_source=FORECAST_SOURCE,
        historical_start_pt=HISTORICAL_START,
        use_actual_as_forecast=(HISTORICAL_START is not None)
    )

    # ------------------------------
    # Optimize
    # ------------------------------
    cfg = OptimizeConfig(
        min_elev_ft=constants.ABAY_MIN_ELEV_FT,
        float_buffer_ft=getattr(constants, 'ABAY_FLOAT_BUFFER_FT', 0.5),
        smoothing_weight_day=getattr(constants, 'SMOOTHING_WEIGHT_DAY', 1.0),
        smoothing_weight_night=getattr(constants, 'SMOOTHING_WEIGHT_NIGHT', 10.0),
        summer_setpoint_floor_mw=getattr(constants, 'SUMMER_OXPH_TARGET_MW', 6.0),
        summer_tracking_weight=getattr(constants, 'SUMMER_TRACKING_WEIGHT', 1000.0),
        summer_floor_penalty=getattr(constants, 'SUMMER_FLOOR_PENALTY', 1e6)
    )

    initial_elev_ft = float(lookback['Afterbay_Elevation'].iloc[-1])
    initial_gen_mw  = float(lookback['Oxbow_Power'].iloc[-1])

    smoothing_weights = forecast['smooth_weight'].tolist()
    morning_flags     = forecast['is_summer_window'].tolist()

    result_df, _ = build_and_solve(
        forecast_df=forecast,
        initial_elev_ft=initial_elev_ft,
        initial_gen_mw=initial_gen_mw,
        smoothing_weights=smoothing_weights,
        morning_window_flags=morning_flags,
        cfg=cfg
    )

    # ------------------------------
    # Operator-facing annotations (identical semantics as cli.py)
    # ------------------------------
    s_over, change_times, g_avg = compute_setpoint_change_annotations(
        idx_utc=result_df.index,
        g_end=result_df['OXPH_generation_MW'],
        s_target=result_df['OXPH_setpoint_MW'],
        initial_gen_mw=initial_gen_mw,
        ramp_mw_per_min=constants.OXPH_RAMP_RATE_MW_PER_MIN,
        tz_pt=constants.PACIFIC_TZ
    )
    result_df['OXPH_setpoint_MW']   = s_over.values
    result_df['OXPH_generation_MW'] = g_avg.values
    result_df['setpoint_change_time'] = change_times.values

    # Stabilization-based setpoint change detection: only flag when the
    # setpoint has settled at a new level, not at ramp intermediates.
    stability_tol = 0.15
    if 'OXPH_ADS' in lookback.columns and lookback['OXPH_ADS'].notna().any():
        last_hist_sp = float(lookback['OXPH_ADS'].dropna().iloc[-1])
    else:
        last_hist_sp = float(lookback['Oxbow_Power'].iloc[-1])
    sp_rounded = result_df['OXPH_setpoint_MW'].round(1)
    T = len(sp_rounded)
    reference_sp = round(last_hist_sp, 1)
    keep_mask = pd.Series(False, index=result_df.index)
    for i in range(T):
        current_sp = float(sp_rounded.iloc[i])
        if abs(current_sp - reference_sp) > stability_tol:
            if i == T - 1:
                is_stable = True
            else:
                next_sp = float(sp_rounded.iloc[i + 1])
                is_stable = abs(current_sp - next_sp) <= stability_tol
            if is_stable:
                keep_mask.iloc[i] = True
                reference_sp = current_sp
    result_df.loc[~keep_mask, 'setpoint_change_time'] = ""

    # Flows/limits from hour-average MW and optimized ABAY_ft
    result_df['OXPH_outflow_cfs'] = oxph_cfs_from_mw_linear(result_df['OXPH_generation_MW']).values
    result_df['Head_limit_MW']    = constants.OXPH_HEAD_LOSS_SLOPE * result_df['ABAY_ft'] + constants.OXPH_HEAD_LOSS_INTERCEPT

    # ------------------------------
    # History diagnostics (last 24h)
    # ------------------------------
    diag_hist = hourly_abay_error_diagnostics(lookback)
    mode_hist_norm = normalize_mode_series(lookback['CCS_Mode'])
    mf12_mw_hist  = mf12_mw_from_mfra(lookback['MFP_Total_Gen_GEN_MDFK_and_RA'],
                                      lookback['R4_Flow'], lookback['R5L_Flow'],
                                      mode_hist_norm)
    mf12_cfs_hist = mf12_cfs_from_mw_quadratic(mf12_mw_hist)
    oxph_cfs_hist = oxph_cfs_from_mw_linear(lookback['Oxbow_Power'])
    expected_hist = expected_series_for_lookback(lookback)
    head_limit_hist = constants.OXPH_HEAD_LOSS_SLOPE * lookback['Afterbay_Elevation'] + constants.OXPH_HEAD_LOSS_INTERCEPT

    hist_last_24 = lookback.tail(24).copy()
    diag_last_24 = diag_hist.reindex(hist_last_24.index)
    exp_last_24  = expected_hist.reindex(hist_last_24.index)
    setpoint_hist = hist_last_24.get('OXPH_ADS', pd.Series(index=hist_last_24.index, dtype=float))

    hist = pd.DataFrame(index=hist_last_24.index)
    hist['OXPH_setpoint_MW_hist'] = setpoint_hist
    hist['OXPH_generation_MW']    = hist_last_24['Oxbow_Power']
    hist['OXPH_outflow_cfs_hist'] = oxph_cfs_hist.reindex(hist_last_24.index)
    hist['R26_Flow'] = hist_last_24['R26_Flow']; hist['R5L_Flow'] = hist_last_24['R5L_Flow']; hist['R20_Flow'] = hist_last_24['R20_Flow']
    hist['R4_Flow']  = hist_last_24['R4_Flow'];  hist['R30_Flow'] = hist_last_24['R30_Flow']
    hist['MFRA_MW']  = hist_last_24['MFP_Total_Gen_GEN_MDFK_and_RA']
    hist['MF_1_2_MW'] = mf12_mw_hist.reindex(hist_last_24.index)
    hist['MF_1_2_cfs'] = mf12_cfs_hist.reindex(hist_last_24.index)
    hist['ABAY_ft'] = hist_last_24['Afterbay_Elevation']
    hist['ABAY_af'] = abay_feet_to_af(hist['ABAY_ft'])
    hist['Expected_ABAY_ft'] = exp_last_24['Expected_ABAY_ft']
    hist['Expected_ABAY_af'] = exp_last_24['Expected_ABAY_af']
    hist['ABAY_NET_expected_cfs'] = diag_last_24['ABAY_NET_expected_cfs']
    hist['ABAY_NET_actual_cfs']   = diag_last_24['ABAY_NET_actual_cfs']
    hist['abay_error_cfs_hourly'] = diag_last_24['abay_error_cfs_hourly']
    hist['abay_error_af_hourly']  = diag_last_24['abay_error_af_hourly']
    hist['Mode'] = hist_last_24['CCS_Mode']
    hist['Head_limit_MW'] = head_limit_hist.reindex(hist_last_24.index)
    hist['bias_cfs_24h'] = float(bias_cfs)
    hist['bias_af_24h']  = float(bias_cfs) * AF_PER_CFS_HOUR
    hist['Regulated_component_cfs'] = regulated_component_gen(
        mf12_cfs_hist.reindex(hist_last_24.index),
        hist_last_24['R4_Flow'], hist_last_24['R5L_Flow']
    ).values
    hist['MFRA_side_reduction_MW'] = np.minimum(86.0, np.maximum(0.0, (hist['R4_Flow'] - hist['R5L_Flow'])/10.0))
    hist['setpoint_change_time'] = ""

    # ------------------------------
    # Forecast diagnostics / output block
    # ------------------------------
    f = forecast.copy()
    f_out = result_df[['OXPH_setpoint_MW','OXPH_generation_MW','OXPH_outflow_cfs',
                       'ABAY_ft','ABAY_af','Head_limit_MW','setpoint_change_time']].copy()
    f_out = f_out.join(f[['R26_Flow','R5L_Flow','R20_Flow','R4_Forecast_CFS','R30_Forecast_CFS',
                          'MFRA_MW_forecast','FLOAT_FT','Mode','bias_cfs']])
    f_out.rename(columns={'R4_Forecast_CFS':'R4_Flow',
                          'R30_Forecast_CFS':'R30_Flow',
                          'MFRA_MW_forecast':'MFRA_MW'}, inplace=True)

    mode_fc_norm = normalize_mode_series(f['Mode'])
    mf12_mw_fc   = mf12_mw_from_mfra(f['MFRA_MW_forecast'], f['R4_Forecast_CFS'], f['R5L_Flow'], mode_fc_norm)
    f_out['MF_1_2_MW']  = mf12_mw_fc.values
    f_out['MF_1_2_cfs'] = mf12_cfs_from_mw_quadratic(mf12_mw_fc).values

    tmp = pd.DataFrame(index=f.index)
    tmp['R30_Flow'] = f_out['R30_Flow']; tmp['R4_Flow'] = f_out['R4_Flow']
    tmp['R20_Flow'] = f_out['R20_Flow']; tmp['R5L_Flow'] = f_out['R5L_Flow']; tmp['R26_Flow'] = f_out['R26_Flow']
    tmp['Oxbow_Power'] = f_out['OXPH_generation_MW']         # hour-average MW
    tmp['MFP_Total_Gen_GEN_MDFK_and_RA'] = f_out['MFRA_MW']
    tmp['CCS_Mode'] = f['Mode']
    exp_net_no_bias = expected_abay_net_cfs(tmp)
    f_out['ABAY_NET_expected_cfs_no_bias']   = exp_net_no_bias.values
    f_out['ABAY_NET_expected_cfs_with_bias'] = (exp_net_no_bias + f_out['bias_cfs']).values

    f_out['Regulated_component_cfs'] = regulated_component_gen(
        f_out['MF_1_2_cfs'], f_out['R4_Flow'], f_out['R5L_Flow']
    ).values
    f_out['MFRA_side_reduction_MW']  = np.minimum(86.0, np.maximum(0.0, (f_out['R4_Flow'] - f_out['R5L_Flow'])/10.0))

    # ------------------------------
    # Write CSV (same core schema as cli.py)
    # ------------------------------
    hist['timestamp_end'] = hist.index.tz_convert(constants.UTC_TZ)
    f_out['timestamp_end'] = f_out.index.tz_convert(constants.UTC_TZ)

    core_cols = ['timestamp_end',
                 'OXPH_setpoint_MW','OXPH_generation_MW','OXPH_outflow_cfs',
                 'R26_Flow','R5L_Flow','R20_Flow','R4_Flow','R30_Flow',
                 'MFRA_MW','MF_1_2_MW','MF_1_2_cfs','ABAY_ft','ABAY_af',
                 'Expected_ABAY_ft','Expected_ABAY_af','abay_error_cfs','abay_error_af',
                 'setpoint_change_time']

    hist_out = pd.DataFrame(index=hist.index)
    hist_out['timestamp_end'] = hist['timestamp_end']
    hist_out['OXPH_setpoint_MW']   = hist['OXPH_setpoint_MW_hist']
    hist_out['OXPH_generation_MW'] = hist['OXPH_generation_MW']
    hist_out['OXPH_outflow_cfs']   = hist['OXPH_outflow_cfs_hist']
    hist_out['R26_Flow'] = hist['R26_Flow']; hist_out['R5L_Flow'] = hist['R5L_Flow']; hist_out['R20_Flow'] = hist['R20_Flow']
    hist_out['R4_Flow']  = hist['R4_Flow'];  hist_out['R30_Flow'] = hist['R30_Flow']
    hist_out['MFRA_MW']  = hist['MFRA_MW'];  hist_out['MF_1_2_MW'] = hist['MF_1_2_MW']; hist_out['MF_1_2_cfs'] = hist['MF_1_2_cfs']
    hist_out['ABAY_ft']  = hist['ABAY_ft'];  hist_out['ABAY_af']  = hist['ABAY_af']
    hist_out['Expected_ABAY_ft'] = hist['Expected_ABAY_ft']; hist_out['Expected_ABAY_af'] = hist['Expected_ABAY_af']
    hist_out['abay_error_cfs'] = hist['abay_error_cfs_hourly']; hist_out['abay_error_af'] = hist['abay_error_af_hourly']
    hist_out['setpoint_change_time'] = hist['setpoint_change_time']
    hist_out = hist_out[core_cols]

    fc_out = pd.DataFrame(index=f_out.index)
    fc_out['timestamp_end'] = f_out['timestamp_end']
    fc_out['OXPH_setpoint_MW']   = f_out['OXPH_setpoint_MW']
    fc_out['OXPH_generation_MW'] = f_out['OXPH_generation_MW']
    fc_out['OXPH_outflow_cfs']   = f_out['OXPH_outflow_cfs']
    fc_out['R26_Flow'] = f_out['R26_Flow']; fc_out['R5L_Flow'] = f_out['R5L_Flow']; fc_out['R20_Flow'] = f_out['R20_Flow']
    fc_out['R4_Flow']  = f_out['R4_Flow'];  fc_out['R30_Flow'] = f_out['R30_Flow']
    fc_out['MFRA_MW']  = f_out['MFRA_MW'];  fc_out['MF_1_2_MW'] = f_out['MF_1_2_MW']; fc_out['MF_1_2_cfs'] = f_out['MF_1_2_cfs']
    fc_out['ABAY_ft']  = f_out['ABAY_ft'];  fc_out['ABAY_af']  = f_out['ABAY_af']
    fc_out['Expected_ABAY_ft'] = np.nan;    fc_out['Expected_ABAY_af'] = np.nan
    fc_out['abay_error_cfs']   = f_out['bias_cfs']; fc_out['abay_error_af'] = f_out['bias_cfs'] * AF_PER_CFS_HOUR
    fc_out['setpoint_change_time'] = f_out['setpoint_change_time']
    fc_out = fc_out[core_cols]

    hist_diag_cols = [
        'Mode','Head_limit_MW','ABAY_NET_expected_cfs','ABAY_NET_actual_cfs',
        'bias_cfs_24h','bias_af_24h','OXPH_setpoint_MW_hist','OXPH_outflow_cfs_hist',
        'Regulated_component_cfs','MFRA_side_reduction_MW'
    ]
    fc_diag_cols = [
        'Mode','Head_limit_MW','FLOAT_FT','bias_cfs',
        'ABAY_NET_expected_cfs_no_bias','ABAY_NET_expected_cfs_with_bias',
        'Regulated_component_cfs','MFRA_side_reduction_MW'
    ]

    hist_out = hist_out.join(hist[hist_diag_cols], how='left')
    fc_out   = fc_out.join(f_out[fc_diag_cols],   how='left')

    final = pd.concat([hist_out, fc_out], axis=0, ignore_index=False)
    final.to_csv(OUTFILE, index=False)
    print(f"Wrote schedule CSV to {OUTFILE}")

if __name__ == "__main__":
    run()
