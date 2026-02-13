# abay_opt/build_inputs.py

import pandas as pd
from . import constants
from .utils import hour_ending_range
from .bias import compute_bias_cfs_24h, expected_series_for_lookback
from .schedule import summer_setpoint_required
from .utils import is_daytime_hour_pt
from .caiso_da import get_da_awards_for_forecast

# Use your existing fetchers (unchanged)
from .data_fetcher import get_historical_and_current_data, get_combined_r4_r30_forecasts

def build_inputs(horizon_hours: int = 24,
                 forecast_source: str = None,
                 historical_start_pt=None,
                 use_actual_as_forecast: bool = True):
    """
       Assemble lookback and forecast inputs for either:
         - normal forecast mode (default), or
         - historical scenario mode (opt‑in), where actuals can be used as the
           'forecast' block starting from historical_start_pt.

       Returns: (lookback_df, forecast_df, current_state_dict, bias_cfs, mfra_source)
       """
    # 1) PI lookback + current state (+forward when in historical mode)
    if historical_start_pt is not None:
        fetched = get_historical_and_current_data(
            historical_sim_date_pt=historical_start_pt,
            return_both=True
        )
        if fetched is None or len(fetched) != 3:
            raise RuntimeError("Failed to fetch PI data for historical scenario.")
        current_state, lookback, forward = fetched
    else:
        current_state, lookback = get_historical_and_current_data()
        forward = None

    if current_state is None or lookback is None or lookback.empty:
        raise RuntimeError("Failed to fetch PI data for lookback/current state.")

    # Compute Expected_ABAY for lookback (for CSV) and bias
    expected_df = expected_series_for_lookback(lookback)
    lookback = lookback.join(expected_df, how='left')
    bias_cfs = compute_bias_cfs_24h(lookback)

    # 2) Build forecast index (hour‑ending) starting next hour after state time
    state_time_utc = pd.Timestamp(current_state['Timestamp_UTC']).tz_convert(constants.UTC_TZ)
    first_forecast_ts = state_time_utc + pd.Timedelta(hours=1)
    idx_forecast = hour_ending_range(first_forecast_ts, horizon_hours, constants.SIMULATION_INTERVAL_MINUTES)

    # 3) Build the forecast block
    forecast = pd.DataFrame(index=idx_forecast)

    mfra_source = 'persistence'  # default

    if historical_start_pt is not None and use_actual_as_forecast and forward is not None:
        # Use actual series as *forecast* (aligned to idx_forecast)
        fwd = forward.reindex(idx_forecast)

        forecast['R4_Forecast_CFS'] = fwd['R4_Flow']
        forecast['R30_Forecast_CFS'] = fwd['R30_Flow']
        forecast['R20_Flow'] = fwd['R20_Flow']
        forecast['R5L_Flow'] = fwd['R5L_Flow']
        forecast['R26_Flow'] = fwd['R26_Flow']
        forecast['MFRA_MW_forecast'] = fwd['MFP_Total_Gen_GEN_MDFK_and_RA']
        forecast['FLOAT_FT'] = fwd['Afterbay_Elevation_Setpoint']
        mfra_source = 'actual'

        # carry the last numeric CCS mode from PI (0=GEN,1=SPILL)
        last_mode = 0
        try:
            if fwd['CCS_Mode'].notna().any():
                last_mode = int(round(float(fwd['CCS_Mode'].dropna().iloc[0])))
        except Exception:
            last_mode = 0
        forecast['Mode'] = last_mode
    else:
        # Normal behavior (forecasts for R4/R30 + hold last values for the rest)
        fs = forecast_source or constants.DEFAULT_UPSTREAM_FORECAST_SOURCE
        r4r30 = get_combined_r4_r30_forecasts(forecast_source=fs)
        if r4r30.empty and fs == constants.UPSTREAM_FORECAST_SOURCE_HYDROFORECAST:
            r4r30 = get_combined_r4_r30_forecasts(forecast_source=constants.UPSTREAM_FORECAST_SOURCE_CNRFC)
        if not r4r30.empty:
            r4r30 = r4r30.reindex(idx_forecast).interpolate(method='time', limit=3).ffill().bfill()

        last_vals = lookback.iloc[-1]
        r4_last = float(last_vals['R4_Flow'])
        r30_last = float(last_vals['R30_Flow'])
        r20_last = float(last_vals['R20_Flow'])
        r5l_last = float(last_vals['R5L_Flow'])
        r26_last = float(last_vals['R26_Flow'])
        float_last = float(last_vals['Afterbay_Elevation_Setpoint'])

        # Build persistence baseline first (always needed as fallback)
        persist_raw = lookback['MFP_Total_Gen_GEN_MDFK_and_RA'].tail(horizon_hours)
        if persist_raw.shape[0] < horizon_hours:
            add = horizon_hours - persist_raw.shape[0]
            add_idx = idx_forecast[persist_raw.shape[0]:]
            persist_raw = pd.concat([persist_raw, pd.Series([persist_raw.iloc[-1]] * add, index=add_idx)])
        persist_raw.index = idx_forecast

        # Try DA awards — use for covered hours, fill gaps with persistence
        da_series, mfra_source = get_da_awards_for_forecast(idx_forecast)
        if da_series is not None and da_series.notna().any():
            mfra_hist = da_series.reindex(idx_forecast).fillna(persist_raw)
        else:
            mfra_source = 'persistence'
            mfra_hist = persist_raw

        def fill_or_hold(colname: str, last_value: float) -> pd.Series:
            if not r4r30.empty and colname in r4r30.columns:
                return r4r30[colname].fillna(last_value)
            return pd.Series(last_value, index=idx_forecast, dtype=float)

        forecast['R4_Forecast_CFS'] = fill_or_hold('R4_Forecast_CFS', r4_last)
        forecast['R30_Forecast_CFS'] = fill_or_hold('R30_Forecast_CFS', r30_last)
        forecast['R20_Flow'] = r20_last
        forecast['R5L_Flow'] = r5l_last
        forecast['R26_Flow'] = r26_last
        forecast['MFRA_MW_forecast'] = mfra_hist
        forecast['FLOAT_FT'] = float_last

        last_mode_raw = last_vals.get('CCS_Mode', 0)
        try:
            last_mode_numeric = int(round(float(last_mode_raw)))
        except Exception:
            last_mode_numeric = 0
        forecast['Mode'] = last_mode_numeric  # keep 0/1

    forecast['bias_cfs'] = float(bias_cfs)

    # 4) Summer window flags and smoothing weights (PT)
    flags = []
    for ts in forecast.index:
        ts_pt = ts.tz_convert(constants.PACIFIC_TZ)
        flags.append(summer_setpoint_required(ts_pt))
    forecast['is_summer_window'] = flags

    smooth_w = []
    for ts in forecast.index:
        ts_pt = ts.tz_convert(constants.PACIFIC_TZ)
        smooth_w.append(1.0 if (8 <= ts_pt.hour <= 20) else 10.0)
    forecast['smooth_weight'] = smooth_w

    return lookback, forecast, current_state, bias_cfs, mfra_source
