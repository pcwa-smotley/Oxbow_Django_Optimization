# abay_opt/cli.py
import argparse
import pandas as pd
import numpy as np
import logging
from . import constants
from .build_inputs import build_inputs
from .optimizer import OptimizeConfig, build_and_solve
from .utils import AF_PER_CFS_HOUR
from .physics import (
    oxph_cfs_from_mw_linear, mf12_mw_from_mfra, mf12_cfs_from_mw_quadratic,
    regulated_component_gen, expected_abay_net_cfs, abay_feet_to_af,
    normalize_mode_series  # maps 0/1 or strings -> 'GEN'/'SPILL'
)
from .bias import hourly_abay_error_diagnostics, expected_series_for_lookback

logger = logging.getLogger(__name__)

def compute_setpoint_change_annotations(idx_utc, g_end, s_target,
                                        initial_gen_mw, ramp_mw_per_min, tz_pt):
    """
    Given hourly end-of-hour targets g_end (from the optimizer) and target setpoints s_target,
    compute for each hour:
      - setpoint_change_time (PT, 'HH:MM'): the *latest* minute in that hour when the setpoint
        must be changed so that cumulative ramp reaches the future target(s) on time.
      - setpoint_override: the setpoint we change *to* in that hour (e.g., 6.0 during rafting).
      - g_avg: hour-average generation under the 'latest-start' ramp policy.

    Notes:
    - Ramp is limited by constants.OXPH_RAMP_RATE_MW_PER_MIN (0.042 MW/min).
    - We keep the optimizer’s end-of-hour generation g_end for feasibility and head-limit consistency.
    """

    he = pd.DatetimeIndex(idx_utc)              # hour-ending UTC times
    T = len(he)
    g_end = pd.Series(g_end, index=he, dtype=float)
    s_target = pd.Series(s_target, index=he, dtype=float)
    setpoint_override = s_target.copy()
    change_time_str = pd.Series([""] * T, index=he, dtype=object)

    # 1) Hour-average generation using 'latest-start' ramp in each hour
    r = float(ramp_mw_per_min)
    g_avg_vals = []
    g_prev = float(initial_gen_mw)
    for t in range(T):
        delta = float(g_end.iloc[t] - g_prev)
        t_need = abs(delta) / r
        # With our ramp constraint, t_need <= 60; clamp just in case.
        t_need = min(t_need, 60.0)
        # Average of piecewise (hold then ramp): avg = g_prev + (t_need/120)*delta
        g_avg_vals.append(g_prev + (t_need / 120.0) * delta)
        g_prev = float(g_end.iloc[t])

    g_avg = pd.Series(g_avg_vals, index=he)

    # 2) Latest-start change minute that falls *inside* each hour
    # For each hour h, look forward to the first future hour t whose cumulative
    # ramp time pushes the start into (he[h]-1h, he[h]].
    for h in range(T):
        he_prev = he[h] - pd.Timedelta(hours=1)
        cum = 0.0
        # generation at the end of prior hour boundary for this forward scan
        g_left = float(initial_gen_mw) if h == 0 else float(g_end.iloc[h-1])
        for t in range(h, T):
            g_right = float(g_end.iloc[t])
            step_minutes = abs(g_right - g_left) / r
            cum += step_minutes
            latest_start = he[t] - pd.Timedelta(minutes=cum)
            if he_prev < latest_start <= he[h]:
                # Record PT clock time, and set the setpoint *we are changing to* in hour h
                change_time_str.iloc[h] = latest_start.tz_convert(tz_pt).strftime("%I:%M %p")
                setpoint_override.iloc[h] = max(setpoint_override.iloc[h], float(s_target.iloc[t]))
                break
            g_left = g_right  # advance to next step

    logger.info(f"Finished Running Change Annotations in cli with setpoint override: {setpoint_override.iloc[0]}")

    return setpoint_override, change_time_str, g_avg


def generate_final_output(lookback, forecast, result_df, bias_cfs, outfile=None):
    """Create the final combined DataFrame used by both CLI and Django."""
    # --- only show a time when the setpoint actually changed (> 0.1 MW) ---
    thresh = 0.1  # MW

    # Last historical PI setpoint (OXPH_ADS), if present
    if 'OXPH_ADS' in lookback.columns and lookback['OXPH_ADS'].notna().any():
        last_hist_sp = float(lookback['OXPH_ADS'].dropna().iloc[-1])
    else:
        last_hist_sp = float(lookback['Oxbow_Power'].iloc[-1])

    # Previous-hour setpoint series for comparison
    prev_s = result_df['OXPH_setpoint_MW'].shift(1)
    prev_s.iloc[0] = last_hist_sp

    # Mask of *actual* change > 0.1 MW
    changed = (result_df['OXPH_setpoint_MW'] - prev_s).abs() > thresh

    # Blank out times when there wasn't a real change
    result_df.loc[~changed, 'setpoint_change_time'] = ""

    # Flows/limits from hour-average MW and optimized ABAY_ft
    result_df['OXPH_outflow_cfs'] = oxph_cfs_from_mw_linear(result_df['OXPH_generation_MW']).values
    result_df['Head_limit_MW'] = (
        constants.OXPH_HEAD_LOSS_SLOPE * result_df['ABAY_ft']
        + constants.OXPH_HEAD_LOSS_INTERCEPT
    )

    # ---------- history (last 24h) diagnostics ----------
    diag_hist = hourly_abay_error_diagnostics(lookback)
    mode_hist_norm = normalize_mode_series(lookback['CCS_Mode'])
    mf12_mw_hist = mf12_mw_from_mfra(
        lookback['MFP_Total_Gen_GEN_MDFK_and_RA'],
        lookback['R4_Flow'],
        lookback['R5L_Flow'],
        mode_hist_norm,
    )
    mf12_cfs_hist = mf12_cfs_from_mw_quadratic(mf12_mw_hist)
    oxph_cfs_hist = oxph_cfs_from_mw_linear(lookback['Oxbow_Power'])
    expected_hist = expected_series_for_lookback(lookback)
    head_limit_hist = (
        constants.OXPH_HEAD_LOSS_SLOPE * lookback['Afterbay_Elevation']
        + constants.OXPH_HEAD_LOSS_INTERCEPT
    )

    hist_last_24 = lookback.tail(24).copy()
    diag_last_24 = diag_hist.reindex(hist_last_24.index)
    exp_last_24 = expected_hist.reindex(hist_last_24.index)
    setpoint_hist = hist_last_24.get(
        'OXPH_ADS', pd.Series(index=hist_last_24.index, dtype=float)
    )

    hist = pd.DataFrame(index=hist_last_24.index)
    hist['OXPH_setpoint_MW_hist'] = setpoint_hist
    hist['OXPH_generation_MW'] = hist_last_24['Oxbow_Power']
    hist['OXPH_outflow_cfs_hist'] = oxph_cfs_hist.reindex(hist_last_24.index)
    hist['R26_Flow'] = hist_last_24['R26_Flow']
    hist['R5L_Flow'] = hist_last_24['R5L_Flow']
    hist['R20_Flow'] = hist_last_24['R20_Flow']
    hist['R4_Flow'] = hist_last_24['R4_Flow']
    hist['R30_Flow'] = hist_last_24['R30_Flow']
    hist['MFRA_MW'] = hist_last_24['MFP_Total_Gen_GEN_MDFK_and_RA']
    hist['MF_1_2_MW'] = mf12_mw_hist.reindex(hist_last_24.index)
    hist['MF_1_2_cfs'] = mf12_cfs_hist.reindex(hist_last_24.index)
    hist['ABAY_ft'] = hist_last_24['Afterbay_Elevation']
    hist['ABAY_af'] = abay_feet_to_af(hist['ABAY_ft'])
    hist['FLOAT_FT'] = hist_last_24.get('Afterbay_Elevation_Setpoint', hist['ABAY_ft'])
    hist['Expected_ABAY_ft'] = exp_last_24['Expected_ABAY_ft']
    hist['Expected_ABAY_af'] = exp_last_24['Expected_ABAY_af']
    hist['ABAY_NET_expected_cfs'] = diag_last_24['ABAY_NET_expected_cfs']
    hist['ABAY_NET_actual_cfs'] = diag_last_24['ABAY_NET_actual_cfs']
    hist['abay_error_cfs_hourly'] = diag_last_24['abay_error_cfs_hourly']
    hist['abay_error_af_hourly'] = diag_last_24['abay_error_af_hourly']
    hist['Mode'] = hist_last_24['CCS_Mode']
    hist['Head_limit_MW'] = head_limit_hist.reindex(hist_last_24.index)
    hist['bias_cfs_24h'] = float(bias_cfs)
    hist['bias_af_24h'] = float(bias_cfs) * AF_PER_CFS_HOUR
    hist['bias_cfs'] = float(bias_cfs)
    hist['Regulated_component_cfs'] = regulated_component_gen(
        mf12_cfs_hist.reindex(hist_last_24.index),
        hist_last_24['R4_Flow'],
        hist_last_24['R5L_Flow'],
    ).values
    hist['MFRA_side_reduction_MW'] = np.minimum(
        86.0, np.maximum(0.0, (hist['R4_Flow'] - hist['R5L_Flow']) / 10.0)
    )
    hist['setpoint_change_time'] = ""  # N/A for history rows

    # ---------- forecast diagnostics ----------
    f = forecast.copy()
    f_out = result_df[
        [
            'OXPH_setpoint_MW',
            'OXPH_generation_MW',
            'OXPH_outflow_cfs',
            'ABAY_ft',
            'ABAY_af',
            'Head_limit_MW',
            'setpoint_change_time',
        ]
    ].copy()
    f_out = f_out.join(
        f[
            [
                'R26_Flow',
                'R5L_Flow',
                'R20_Flow',
                'R4_Forecast_CFS',
                'R30_Forecast_CFS',
                'MFRA_MW_forecast',
                'FLOAT_FT',
                'Mode',
                'bias_cfs',
            ]
        ]
    )
    f_out.rename(
        columns={
            'R4_Forecast_CFS': 'R4_Flow',
            'R30_Forecast_CFS': 'R30_Flow',
            'MFRA_MW_forecast': 'MFRA_MW',
        },
        inplace=True,
    )

    mode_fc_norm = normalize_mode_series(f['Mode'])
    mf12_mw_fc = mf12_mw_from_mfra(
        f['MFRA_MW_forecast'], f['R4_Forecast_CFS'], f['R5L_Flow'], mode_fc_norm
    )
    f_out['MF_1_2_MW'] = mf12_mw_fc.values
    f_out['MF_1_2_cfs'] = mf12_cfs_from_mw_quadratic(mf12_mw_fc).values

    tmp = pd.DataFrame(index=f.index)
    tmp['R30_Flow'] = f_out['R30_Flow']
    tmp['R4_Flow'] = f_out['R4_Flow']
    tmp['R20_Flow'] = f_out['R20_Flow']
    tmp['R5L_Flow'] = f_out['R5L_Flow']
    tmp['R26_Flow'] = f_out['R26_Flow']
    tmp['Oxbow_Power'] = f_out['OXPH_generation_MW']
    tmp['MFP_Total_Gen_GEN_MDFK_and_RA'] = f_out['MFRA_MW']
    tmp['CCS_Mode'] = f['Mode']
    exp_net_no_bias = expected_abay_net_cfs(tmp)
    f_out['ABAY_NET_expected_cfs_no_bias'] = exp_net_no_bias.values
    f_out['ABAY_NET_expected_cfs_with_bias'] = (
        exp_net_no_bias + f_out['bias_cfs']
    ).values

    f_out['Regulated_component_cfs'] = regulated_component_gen(
        f_out['MF_1_2_cfs'], f_out['R4_Flow'], f_out['R5L_Flow']
    ).values
    f_out['MFRA_side_reduction_MW'] = np.minimum(
        86.0, np.maximum(0.0, (f_out['R4_Flow'] - f_out['R5L_Flow']) / 10.0)
    )

    # ---------- assemble final output ----------
    hist['timestamp_end'] = hist.index.tz_convert(constants.UTC_TZ)
    f_out['timestamp_end'] = f_out.index.tz_convert(constants.UTC_TZ)

    core_cols = [
        'timestamp_end',
        'OXPH_setpoint_MW',
        'OXPH_generation_MW',
        'OXPH_outflow_cfs',
        'R26_Flow',
        'R5L_Flow',
        'R20_Flow',
        'R4_Flow',
        'R30_Flow',
        'MFRA_MW',
        'MF_1_2_MW',
        'MF_1_2_cfs',
        'ABAY_ft',
        'ABAY_af',
        'Expected_ABAY_ft',
        'Expected_ABAY_af',
        'abay_error_cfs',
        'abay_error_af',
        'setpoint_change_time',
        'is_forecast',
    ]

    hist_out = pd.DataFrame(index=hist.index)
    hist_out['timestamp_end'] = hist['timestamp_end']
    hist_out['OXPH_setpoint_MW'] = hist['OXPH_setpoint_MW_hist']
    hist_out['OXPH_generation_MW'] = hist['OXPH_generation_MW']
    hist_out['OXPH_outflow_cfs'] = hist['OXPH_outflow_cfs_hist']
    hist_out['R26_Flow'] = hist['R26_Flow']
    hist_out['R5L_Flow'] = hist['R5L_Flow']
    hist_out['R20_Flow'] = hist['R20_Flow']
    hist_out['R4_Flow'] = hist['R4_Flow']
    hist_out['R30_Flow'] = hist['R30_Flow']
    hist_out['MFRA_MW'] = hist['MFRA_MW']
    hist_out['MF_1_2_MW'] = hist['MF_1_2_MW']
    hist_out['MF_1_2_cfs'] = hist['MF_1_2_cfs']
    hist_out['ABAY_ft'] = hist['ABAY_ft']
    hist_out['ABAY_af'] = hist['ABAY_af']
    hist_out['Expected_ABAY_ft'] = hist['Expected_ABAY_ft']
    hist_out['Expected_ABAY_af'] = hist['Expected_ABAY_af']
    hist_out['abay_error_cfs'] = hist['abay_error_cfs_hourly']
    hist_out['abay_error_af'] = hist['abay_error_af_hourly']
    hist_out['setpoint_change_time'] = hist['setpoint_change_time']
    hist_out['is_forecast'] = False
    hist_out = hist_out[core_cols]

    fc_out = pd.DataFrame(index=f_out.index)
    fc_out['timestamp_end'] = f_out['timestamp_end']
    fc_out['OXPH_setpoint_MW'] = f_out['OXPH_setpoint_MW']
    fc_out['OXPH_generation_MW'] = f_out['OXPH_generation_MW']
    fc_out['OXPH_outflow_cfs'] = f_out['OXPH_outflow_cfs']
    fc_out['R26_Flow'] = f_out['R26_Flow']
    fc_out['R5L_Flow'] = f_out['R5L_Flow']
    fc_out['R20_Flow'] = f_out['R20_Flow']
    fc_out['R4_Flow'] = f_out['R4_Flow']
    fc_out['R30_Flow'] = f_out['R30_Flow']
    fc_out['MFRA_MW'] = f_out['MFRA_MW']
    fc_out['MF_1_2_MW'] = f_out['MF_1_2_MW']
    fc_out['MF_1_2_cfs'] = f_out['MF_1_2_cfs']
    fc_out['ABAY_ft'] = f_out['ABAY_ft']
    fc_out['ABAY_af'] = f_out['ABAY_af']
    fc_out['Expected_ABAY_ft'] = np.nan
    fc_out['Expected_ABAY_af'] = np.nan
    fc_out['abay_error_cfs'] = f_out['bias_cfs']
    fc_out['abay_error_af'] = f_out['bias_cfs'] * AF_PER_CFS_HOUR
    fc_out['setpoint_change_time'] = f_out['setpoint_change_time']
    fc_out['is_forecast'] = True
    fc_out = fc_out[core_cols]

    hist_diag_cols = [
        'Mode',
        'Head_limit_MW',
        'FLOAT_FT',
        'ABAY_NET_expected_cfs',
        'ABAY_NET_actual_cfs',
        'bias_cfs_24h',
        'bias_af_24h',
        'OXPH_setpoint_MW_hist',
        'OXPH_outflow_cfs_hist',
        'Regulated_component_cfs',
        'MFRA_side_reduction_MW',
        'bias_cfs',
    ]
    fc_diag_cols = [
        'Mode',
        'Head_limit_MW',
        'FLOAT_FT',
        'bias_cfs',
        'ABAY_NET_expected_cfs_no_bias',
        'ABAY_NET_expected_cfs_with_bias',
        'Regulated_component_cfs',
        'MFRA_side_reduction_MW',
    ]

    hist_out = hist_out.join(hist[hist_diag_cols], how='left')
    fc_out = fc_out.join(f_out[fc_diag_cols], how='left')

    final = pd.concat([hist_out, fc_out], axis=0, ignore_index=False)

    if outfile:
        final.to_csv(outfile, index=False)
        print(f"Wrote schedule CSV to {outfile}")

    return final


def main():
    # ---------- helper: minute-resolution annotations ----------
    def compute_setpoint_change_annotations(idx_utc, g_end, s_target,
                                            initial_gen_mw, ramp_mw_per_min, tz_pt):
        """
        For each hour-ending UTC timestamp in idx_utc:
          - setpoint_change_time: the *latest* PT clock time within that hour when
            operators must change the setpoint to meet future end-of-hour targets
            under the 0.042 MW/min ramp.
          - setpoint_override: setpoint value we change *to* in that hour (e.g., 6.0).
          - g_avg: hour-average generation under a 'latest-start' ramp (head limit
            is already respected by the solver's g_end).
        """
        he = pd.DatetimeIndex(idx_utc)
        T = len(he)
        g_end = pd.Series(g_end, index=he, dtype=float)
        s_target = pd.Series(s_target, index=he, dtype=float)
        setpoint_override = s_target.copy()
        change_time_str = pd.Series([""] * T, index=he, dtype=object)

        # Hour-average from piecewise(hold->ramp) with 'latest-start'
        r = float(ramp_mw_per_min)
        g_avg_vals = []
        g_prev = float(initial_gen_mw)
        for t in range(T):
            delta = float(g_end.iloc[t] - g_prev)
            t_need = min(abs(delta) / r, 60.0)  # minutes in this hour
            g_avg_vals.append(g_prev + (t_need / 120.0) * delta)
            g_prev = float(g_end.iloc[t])
        g_avg = pd.Series(g_avg_vals, index=he)

        # Latest-start minute that lands inside each hour
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
                    # Set the hour's setpoint to the value we change *to* (e.g., rafting floor)
                    setpoint_override.iloc[h] = max(setpoint_override.iloc[h], float(s_target.iloc[t]))
                    break
                g_left = g_right
        return setpoint_override, change_time_str, g_avg

    # ---------- args ----------
    parser = argparse.ArgumentParser(description="Optimize OXPH setpoints to manage ABAY elevation.")
    parser.add_argument("--horizon", type=int, default=72, help="Forecast horizon in hours (default 72).")
    parser.add_argument("--forecast-source", type=str, default=None,
                        help="Upstream forecast source ('hydroforecast-short-term' or 'cnrfc').")
    parser.add_argument("--outfile", type=str, default="./abay_schedule.csv", help="Path to write the CSV output.")
    parser.add_argument("--historical-start", type=str, default=None,
                        help='Historical start datetime (e.g. "2025-06-28T00:00" PT or UTC).')
    parser.add_argument("--use-actual-as-forecast", action="store_true",
                        help="In historical mode, use actual MFRA/R4/R30/etc as the forecast series.")
    args = parser.parse_args()

    # ---------- inputs ----------
    lookback, forecast, state, bias_cfs, mfra_source = build_inputs(
        horizon_hours=args.horizon,
        forecast_source=args.forecast_source,
        historical_start_pt=args.historical_start,
        # default to True when historical_start is set, unless you deliberately pass the flag
        use_actual_as_forecast=(args.use_actual_as_forecast or args.historical_start is not None)
    )
    print(f"MFRA forecast source: {mfra_source}")

    # ---------- optimizer config ----------
    cfg = OptimizeConfig(
        min_elev_ft=constants.ABAY_MIN_ELEV_FT,
        float_buffer_ft=getattr(constants, 'ABAY_FLOAT_BUFFER_FT', 0.5),
        smoothing_weight_day=getattr(constants, 'SMOOTHING_WEIGHT_DAY', 1.0),
        smoothing_weight_night=getattr(constants, 'SMOOTHING_WEIGHT_NIGHT', 10.0),
        summer_setpoint_floor_mw=getattr(constants, 'SUMMER_OXPH_TARGET_MW', 6.0),
        summer_tracking_weight=getattr(constants, 'SUMMER_TRACKING_WEIGHT', 1000.0),
        summer_floor_penalty=getattr(constants, 'SUMMER_FLOOR_PENALTY', 1e6)
    )

    # Initial conditions (hour-ending semantics)
    initial_elev_ft = float(lookback['Afterbay_Elevation'].iloc[-1])
    initial_gen_mw  = float(lookback['Oxbow_Power'].iloc[-1])

    smoothing_weights = forecast['smooth_weight'].tolist()
    morning_flags     = forecast['is_summer_window'].tolist()

    # ---------- solve ----------
    result_df, model = build_and_solve(
        forecast_df=forecast,
        initial_elev_ft=initial_elev_ft,
        initial_gen_mw=initial_gen_mw,
        smoothing_weights=smoothing_weights,
        morning_window_flags=morning_flags,
        cfg=cfg
    )

    # ---------- add operator-friendly ramp annotations ----------
    s_over, change_times, g_avg = compute_setpoint_change_annotations(
        idx_utc=result_df.index,
        g_end=result_df['OXPH_generation_MW'],   # solver's end-of-hour MW
        s_target=result_df['OXPH_setpoint_MW'],  # solver's setpoint (≥ 6.0 in rafting windows)
        initial_gen_mw=initial_gen_mw,
        ramp_mw_per_min=constants.OXPH_RAMP_RATE_MW_PER_MIN,  # 0.042 MW/min
        tz_pt=constants.PACIFIC_TZ
    )
    # Replace per your spec:
    result_df['OXPH_setpoint_MW']   = s_over.values         # setpoint changed-to value
    result_df['OXPH_generation_MW'] = g_avg.values          # hour-average generation
    result_df['setpoint_change_time'] = change_times.values # PT clock time like '07:11 AM'

    final = generate_final_output(lookback, forecast, result_df, bias_cfs, outfile=args.outfile)

    return final


if __name__ == "__main__":
    main()
