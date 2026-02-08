# abay_opt/optimizer.py
import pandas as pd
import numpy as np
from typing import List, Tuple
from dataclasses import dataclass
from pulp import (
    LpProblem, LpMinimize, LpVariable, LpStatus, PULP_CBC_CMD, LpContinuous, LpBinary, lpSum, value
)
from . import constants
from .physics import (
    abay_feet_to_af, mf12_mw_from_mfra, mf12_cfs_from_mw_quadratic,
    regulated_component_gen
)
from .utils import AF_PER_CFS_HOUR

@dataclass
class OptimizeConfig:
    min_elev_ft: float
    float_buffer_ft: float = 0.5
    oxph_min_mw: float = None
    oxph_max_mw: float = None
    ramp_mw_per_hour: float = None
    summer_setpoint_floor_mw: float = 6.0
    smoothing_weight_day: float = 1.0
    smoothing_weight_night: float = 10.0
    slack_penalty: float = 1e6  # elevation violation penalty
    # NEW: rafting‑window tracking/floor penalties
    summer_tracking_weight: float = 1000.0      # penalty on (setpoint - generation)+ in MW
    summer_floor_penalty: float = 1e6           # penalty on violating 6.0 MW floor (soft)

    def __post_init__(self):
        if self.oxph_min_mw is None:
            self.oxph_min_mw = constants.OXPH_MIN_MW
        if self.oxph_max_mw is None:
            self.oxph_max_mw = constants.OXPH_MAX_MW
        if self.ramp_mw_per_hour is None:
            self.ramp_mw_per_hour = constants.OXPH_RAMP_RATE_MW_PER_MIN * 60.0

def piecewise_storage_breakpoints(h_min: float, h_max: float, n_breaks: int = 14) -> Tuple[List[float], List[float]]:
    """Return lists H_i, A_i over [h_min, h_max] using the quadratic ft->AF mapping."""
    if h_max <= h_min:
        h_max = h_min + 1.0
    H_vals = np.linspace(h_min, h_max, n_breaks)
    from .physics import abay_feet_to_af
    A_vals = abay_feet_to_af(pd.Series(H_vals)).values
    return list(H_vals), list(A_vals)

def build_and_solve(forecast_df: pd.DataFrame,
                    initial_elev_ft: float,
                    initial_gen_mw: float,
                    smoothing_weights: List[float],
                    morning_window_flags: List[bool],
                    cfg: OptimizeConfig):
    """
    Solve MILP for OXPH schedule over the forecast horizon.
    forecast_df must have columns:
      ['R4_Forecast_CFS','R30_Forecast_CFS','R20_Flow','R5L_Flow','R26_Flow',
       'MFRA_MW_forecast','FLOAT_FT','bias_cfs','Mode']
    The timeline is the DatetimeIndex (UTC, hour-ending).
    """
    idx = forecast_df.index
    T = len(idx)

    # Parameters
    r4 = forecast_df['R4_Forecast_CFS'].astype(float)
    r30 = forecast_df['R30_Forecast_CFS'].astype(float)
    r20 = forecast_df['R20_Flow'].astype(float)
    r5l = forecast_df['R5L_Flow'].astype(float)
    r26 = forecast_df['R26_Flow'].astype(float)
    mfra = forecast_df['MFRA_MW_forecast'].astype(float)
    bias = forecast_df['bias_cfs'].astype(float).fillna(0.0)
    mode = forecast_df['Mode'].fillna('GEN').astype(str).str.upper()

    mf12_mw = mf12_mw_from_mfra(mfra, r4, r5l, mode)
    mf12_cfs = mf12_cfs_from_mw_quadratic(mf12_mw)

    base = r30 + r4 + (r20 - r5l) - r26 + bias
    regulated = regulated_component_gen(mf12_cfs, r4, r5l)  # used only in GEN

    H_max = forecast_df['FLOAT_FT'].astype(float) - cfg.float_buffer_ft
    H_min = pd.Series(cfg.min_elev_ft, index=idx)

    # Common breakpoints for PWL ft<->AF mapping over the reachable band
    global_h_min = float(min(H_min.min(), initial_elev_ft))
    global_h_max = float(max(H_max.max(), initial_elev_ft))
    H_pts, A_pts = piecewise_storage_breakpoints(global_h_min, global_h_max, n_breaks=14)
    n_pts = len(H_pts); n_seg = n_pts - 1

    # Model
    m = LpProblem("OXPH_Schedule", LpMinimize)

    # Decision vars
    g = LpVariable.dicts("gen_MW", range(T), lowBound=cfg.oxph_min_mw, upBound=cfg.oxph_max_mw, cat=LpContinuous)
    s = LpVariable.dicts("setpoint_MW", range(T), lowBound=0, upBound=10.0, cat=LpContinuous)
    H = LpVariable.dicts("ABAY_ft", range(T), lowBound=0, upBound=2000, cat=LpContinuous)
    A = LpVariable.dicts("ABAY_af", range(T), lowBound=0, upBound=1e7, cat=LpContinuous)

    # Convex‑combination lambdas & segment selectors (PWL hull)
    lam = {(t, i): LpVariable(f"lam_{t}_{i}", lowBound=0, upBound=1, cat=LpContinuous) for t in range(T) for i in range(n_pts)}
    seg = {(t, k): LpVariable(f"seg_{t}_{k}", lowBound=0, upBound=1, cat=LpBinary) for t in range(T) for k in range(n_seg)}

    # Elevation slack (hardly ever used; massive penalty)
    slack_hi = LpVariable.dicts("slack_high", range(T), lowBound=0, upBound=10.0, cat=LpContinuous)
    slack_lo = LpVariable.dicts("slack_low", range(T), lowBound=0, upBound=10.0, cat=LpContinuous)

    # Smoothing (setpoint) via pos/neg parts
    dpos = LpVariable.dicts("ds_pos", range(T), lowBound=0, upBound=cfg.oxph_max_mw, cat=LpContinuous)
    dneg = LpVariable.dicts("ds_neg", range(T), lowBound=0, upBound=cfg.oxph_max_mw, cat=LpContinuous)

    # NEW: rafting tracking shortfall: (s - g)+
    shortfall = LpVariable.dicts("summer_shortfall", range(T), lowBound=0, upBound=cfg.oxph_max_mw, cat=LpContinuous)
    # NEW: soft floor slack for g >= 6.0 during rafting window
    floor_slack = LpVariable.dicts("summer_floor_slack", range(T), lowBound=0, upBound=10.0, cat=LpContinuous)

    # Initial AF
    A0 = float(abay_feet_to_af(initial_elev_ft))

    # PWL mapping & bounds
    for t in range(T):
        m += lpSum(lam[(t, i)] for i in range(n_pts)) == 1, f"lam_sum_{t}"
        m += lpSum(seg[(t, k)] for k in range(n_seg)) == 1, f"seg_one_{t}"
        m += lam[(t, 0)] <= seg[(t, 0)], f"lam0_seg_{t}"
        m += lam[(t, n_pts-1)] <= seg[(t, n_seg-1)], f"lamN_seg_{t}"
        for i in range(1, n_pts-1):
            m += lam[(t, i)] <= seg[(t, i-1)] + seg[(t, i)], f"lam_adj_{t}_{i}"

        m += H[t] == lpSum(lam[(t, i)] * H_pts[i] for i in range(n_pts)), f"H_link_{t}"
        m += A[t] == lpSum(lam[(t, i)] * A_pts[i] for i in range(n_pts)), f"A_link_{t}"

        m += H[t] <= float(H_max.iloc[t]) + slack_hi[t], f"H_max_{t}"
        m += H[t] >= float(H_min.iloc[t]) - slack_lo[t], f"H_min_{t}"

        # Head limit: g_t <= 0.0912*H_t - 101.42  (constants)
        m += g[t] <= constants.OXPH_HEAD_LOSS_SLOPE * H[t] + constants.OXPH_HEAD_LOSS_INTERCEPT, f"head_limit_{t}"

    # Water balance (AF)
    oxph_cfs_factor = constants.OXPH_MW_TO_CFS_FACTOR   # linear MW->cfs per goal doc
    oxph_cfs_offset = constants.OXPH_MW_TO_CFS_OFFSET

    known_GEN = base + regulated - oxph_cfs_offset
    known_SPILL = base + mf12_cfs - oxph_cfs_offset

    for t in range(T):
        known_t = float(known_GEN.iloc[t]) if mode.iloc[t] != 'SPILL' else float(known_SPILL.iloc[t])
        if t == 0:
            m += A[0] == A0 + AF_PER_CFS_HOUR * (known_t - oxph_cfs_factor * g[0]), f"wb_{t}"
        else:
            m += A[t] == A[t-1] + AF_PER_CFS_HOUR * (known_t - oxph_cfs_factor * g[t]), f"wb_{t}"

    # Ramping
    m += g[0] - initial_gen_mw <= cfg.ramp_mw_per_hour, "ramp_up_0"
    m += initial_gen_mw - g[0] <= cfg.ramp_mw_per_hour, "ramp_dn_0"
    for t in range(1, T):
        m += g[t] - g[t-1] <= cfg.ramp_mw_per_hour, f"ramp_up_{t}"
        m += g[t-1] - g[t] <= cfg.ramp_mw_per_hour, f"ramp_dn_{t}"

    # Setpoint/generation linkage + rafting tracking
    for t in range(T):
        if morning_window_flags[t]:
            # Rafting window: setpoint must be ≥ floor, must be ≥ generation
            m += s[t] >= cfg.summer_setpoint_floor_mw, f"sp_floor_{t}"
            m += s[t] >= g[t], f"sp_ge_gen_{t}"
            # Soft generation floor at 6.0 MW, with slack (penalized heavily).
            m += g[t] >= cfg.summer_setpoint_floor_mw - floor_slack[t], f"summer_floor_{t}"
            # Shortfall = (s - g)+  (minimised in objective)
            m += shortfall[t] >= s[t] - g[t], f"track_short_{t}"
        else:
            # Outside window: setpoint == generation (the normal behavior)
            m += s[t] == g[t], f"sp_eq_gen_{t}"
            # No shortfall needed here, keep it non-negative
            m += shortfall[t] >= 0, f"track_short_nowin_{t}"

    # Smoothing: setpoint changes only (we prefer changes during 08:00–20:00 PT)
    m += s[0] - initial_gen_mw == dpos[0] - dneg[0], "smooth_0"
    for t in range(1, T):
        m += s[t] - s[t-1] == dpos[t] - dneg[t], f"smooth_{t}"

    # Objective
    smooth_terms = [w * (dpos[t] + dneg[t]) for t, w in enumerate(smoothing_weights)]
    slack_terms  = [cfg.slack_penalty * (slack_hi[t] + slack_lo[t]) for t in range(T)]
    # Tracking only during rafting window
    track_terms  = [cfg.summer_tracking_weight * shortfall[t] for t in range(T) if morning_window_flags[t]]
    floor_terms  = [cfg.summer_floor_penalty  * floor_slack[t] for t in range(T)]  # penalize any floor violation

    m += lpSum(smooth_terms + slack_terms + track_terms + floor_terms)

    # Solve
    try:
        status = m.solve(PULP_CBC_CMD(msg=False))
    except Exception:
        status = m.solve()

    status_name = LpStatus[m.status]

    # Results
    out = pd.DataFrame(index=idx)
    out['OXPH_generation_MW'] = [value(g[t]) for t in range(T)]
    out['OXPH_setpoint_MW']   = [value(s[t]) for t in range(T)]
    out['ABAY_ft']            = [value(H[t]) for t in range(T)]
    out['ABAY_af']            = [value(A[t]) for t in range(T)]
    out['SolverStatus']       = status_name
    out.attrs['objective']    = value(m.objective) if m.objective is not None else None
    return out, m
