
# abay_opt/recalc.py

"""
Deterministic forward recalculation of ABAY (no MILP).

This module recomputes ABAY_af / ABAY_ft and derived diagnostics when an operator
manually edits *forecast* values for any hour (MFRA_MW, OXPH_generation_MW,
R4_Flow, R30_Flow). It integrates mass-balance **from the earliest edited hour
forward** and preserves hour-ending semantics.

Key properties
--------------
- Uses the same physics you approved for the optimizer pipeline:
  * GEN vs SPILL formula (regulated component vs direct MF_1_2)
  * MF_1_2 from MFRA + side-water reduction (GEN mode)
  * OXPH MW -> cfs linear curve (163.73 * MW + 83)
  * ABAY ft <-> AF quadratic mapping (via physics module)
  * Bias (cfs) applied additively to the net inflow
- Enforces head-pressure limit per hour using a closed-form clamp so no iteration
  is needed. (Clamps to the feasible MW at that hour given end-of-hour elevation.)
- Only hours at/after the earliest edit are recomputed; earlier hours are left intact.

Inputs
------
- df: pandas DataFrame with the *forecast* portion of the schedule (hour-ending UTC index)
  Required columns:
    ['R26_Flow','R5L_Flow','R20_Flow','R4_Flow','R30_Flow','MFRA_MW',
     'FLOAT_FT','Mode','bias_cfs','OXPH_generation_MW']
  Optional but recommended columns:
    ['ABAY_af','ABAY_ft'] (for continuity if editing mid-table)

- overrides: dict mapping variable name -> {timestamp_str: value}, e.g.:
    {
      "MFRA_MW": {"2025-06-28T16:00Z": 140.0},
      "OXPH_generation_MW": {"2025-06-28T17:00Z": 2.4},
      "R4_Flow": {"2025-06-28T16:00Z": 200.0}
    }
  Timestamps may be naive (assumed UTC) or timezone-aware.

- initial_abay_ft: float elevation (ft) for the hour BEFORE df.index[0].
  If you edit the very first hour, we need this to seed the integration. If you
  edit later hours, we will, by default, seed from df['ABAY_af'] at the previous
  hour when available; otherwise, we fall back to initial_abay_ft.

Returns
-------
- A *new* DataFrame with the same index as input df and updated columns:
    'ABAY_af','ABAY_ft','OXPH_generation_MW','OXPH_outflow_cfs',
    'MF_1_2_MW','MF_1_2_cfs','Regulated_component_cfs','Head_limit_MW',
    'violates_min','violates_float','violates_head'
  Only rows >= earliest edited hour will differ from the input unless
  you pass `edit_from` explicitly.

Usage
-----
from abay_opt.recalc import recalc_abay_path

updated = recalc_abay_path(
    forecast_df,
    overrides={ "MFRA_MW": {"2025-06-28T16:00Z": 140.0} },
    initial_abay_ft=1169.2
)
"""

from __future__ import annotations
from typing import Dict, Optional, Tuple
import numpy as np
import pandas as pd

from . import constants
from .utils import AF_PER_CFS_HOUR
from .physics import abay_feet_to_af, abay_af_to_feet

# ---- Helpers ---------------------------------------------------------------

def _to_utc(ts_like: pd.Timestamp) -> pd.Timestamp:
    ts = pd.Timestamp(ts_like)
    if ts.tz is None:
        ts = ts.tz_localize(constants.UTC_TZ)
    else:
        ts = ts.tz_convert(constants.UTC_TZ)
    return ts

def normalize_mode_series(mode) -> pd.Series:
    """
    Convert PI CCS mode (0/1, '0'/'1', 'GEN'/'SPILL') to 'GEN'/'SPILL' strings.
    """
    if isinstance(mode, pd.Series):
        as_num = pd.to_numeric(mode, errors='coerce')
        out = pd.Series(index=mode.index, dtype=object)
        mask_num = as_num.notna()
        out.loc[mask_num] = np.where(as_num[mask_num] >= 0.5, 'SPILL', 'GEN')
        s = mode.astype(str).str.upper()
        out.loc[~mask_num] = s[~mask_num].replace({'0': 'GEN', '1': 'SPILL'})
        out = out.where(out.isin(['GEN','SPILL']), 'GEN')
        return out
    # scalar
    try:
        v = float(mode)
        return 'SPILL' if v >= 0.5 else 'GEN'
    except Exception:
        t = str(mode).upper()
        if t in ('SPILL','GEN'):
            return t
        if t == '1':
            return 'SPILL'
        if t == '0':
            return 'GEN'
        return 'GEN'

def mf12_mw_from_mfra(mfra_mw, r4_cfs, r5l_cfs, mode) -> pd.Series:
    """
    Vectorised MF_1_2 MW from MFRA, side-water reduction, and mode.
    GEN:   (MFRA - min(86, max(0,(R4-R5L))/10)) * 0.59
    SPILL: (MFRA) * 0.59
    """
    mode_norm = normalize_mode_series(mode)
    mfra = pd.to_numeric(pd.Series(mfra_mw), errors='coerce').fillna(0.0)
    r4 = pd.to_numeric(pd.Series(r4_cfs), errors='coerce').fillna(0.0)
    r5l = pd.to_numeric(pd.Series(r5l_cfs), errors='coerce').fillna(0.0)
    side = np.minimum(86.0, np.maximum(0.0, (r4 - r5l) / 10.0))
    out = np.where((mode_norm.values == 'SPILL'), mfra * 0.59, (mfra - side) * 0.59)
    return pd.Series(np.maximum(out, 0.0), index=mfra.index)

def mf12_cfs_from_mw_quadratic(mw) -> pd.Series:
    a = constants.MFRA_MW2_TO_CFS_FACTOR
    b = constants.MFRA_MW_TO_CFS_FACTOR
    c = constants.MFRA_MW_TO_CFS_OFFSET
    mwv = pd.to_numeric(pd.Series(mw), errors='coerce').fillna(0.0)
    return a * (mwv ** 2) + b * mwv + c

def regulated_component_gen(mf12_cfs, r4_cfs, r5l_cfs) -> pd.Series:
    r4 = pd.to_numeric(pd.Series(r4_cfs), errors='coerce').fillna(0.0)
    r5l = pd.to_numeric(pd.Series(r5l_cfs), errors='coerce').fillna(0.0)
    mf = pd.to_numeric(pd.Series(mf12_cfs), errors='coerce').fillna(0.0)
    term1 = np.minimum(886.0, (mf + r4) - r5l)
    term2 = np.maximum(0.0, r4 - r5l)
    return pd.Series(np.maximum(term1, term2), index=r4.index)

def oxph_cfs_from_mw_linear(mw) -> pd.Series:
    f = constants.OXPH_MW_TO_CFS_FACTOR
    off = constants.OXPH_MW_TO_CFS_OFFSET
    mv = pd.to_numeric(pd.Series(mw), errors='coerce').fillna(0.0)
    return f * mv + off

def _head_limited_cap_mw(H_prev_ft: float, known_cfs: float) -> float:
    """
    Closed-form head limit for hour t with previous elevation H_prev and known_t:
      A_t = A_{t-1} + k*(known_t - f*g_t)
      g_t <= a*H_t + b
      H_t = f(A_t) [we only need linear form via the equation below]
    Derivation eliminates H_t:
      g*(1 + a*k*f) <= a*H_prev + a*k*known + b
      => cap = RHS / (1 + a*k*f)
    where:
      a = OXPH_HEAD_LOSS_SLOPE
      b = OXPH_HEAD_LOSS_INTERCEPT
      f = OXPH_MW_TO_CFS_FACTOR
      k = AF_PER_CFS_HOUR
    """
    a = constants.OXPH_HEAD_LOSS_SLOPE
    b = constants.OXPH_HEAD_LOSS_INTERCEPT
    f = constants.OXPH_MW_TO_CFS_FACTOR
    k = AF_PER_CFS_HOUR
    rhs = a * H_prev_ft + a * k * known_cfs + b
    denom = 1.0 + a * k * f
    return rhs / denom

# ---- Core ------------------------------------------------------------------

def recalc_abay_path(
    forecast_df: pd.DataFrame,
    overrides: Optional[Dict[str, Dict[str, float]]] = None,
    initial_abay_ft: Optional[float] = None,
    edit_from: Optional[pd.Timestamp] = None,
    clamp_to_head: bool = True,
    clamp_to_minmax: bool = True,
    inplace: bool = False
) -> pd.DataFrame:
    """
    Apply `overrides` and recompute ABAY path and dependent columns from the earliest
    edited hour (or `edit_from` if provided) to the end of horizon.

    Parameters
    ----------
    forecast_df : DataFrame
        Forecast schedule DataFrame (hour-ending UTC index).
    overrides : dict
        Mapping of column -> {timestamp_str: value}. Supported keys:
          'MFRA_MW', 'OXPH_generation_MW', 'R4_Flow', 'R30_Flow'.
    initial_abay_ft : float
        Elevation (ft) at the hour **before** forecast_df.index[0]. Required if
        the first row is edited or ABAY_af is missing for the row prior to edit.
    edit_from : Timestamp
        If provided, begin recomputation from this hour (UTC). Otherwise, compute
        from the earliest timestamp present in `overrides`.
    clamp_to_head : bool
        If True, clamp OXPH_generation_MW to the head limit implied by end-of-hour
        elevation (closed-form).
    clamp_to_minmax : bool
        If True, clamp OXPH_generation_MW to [OXPH_MIN_MW, OXPH_MAX_MW].
    inplace : bool
        If True, mutate `forecast_df`; else return a new DataFrame.

    Returns
    -------
    DataFrame with updated columns for all rows >= edit_from.
    """
    if not inplace:
        df = forecast_df.copy()
    else:
        df = forecast_df

    if overrides:
        # Apply overrides (case-insensitive column keys)
        key_map = {k.lower(): k for k in df.columns}
        for col, edits in overrides.items():
            target_col = key_map.get(col.lower(), col)
            if target_col not in df.columns:
                continue  # ignore unknown keys
            for ts_str, val in edits.items():
                ts = _to_utc(ts_str)
                if ts in df.index:
                    df.at[ts, target_col] = float(val)

    # Determine edit start time
    if edit_from is None:
        if overrides:
            all_ts = []
            for edits in overrides.values():
                all_ts.extend([_to_utc(k) for k in edits.keys()])
            edit_from = min(all_ts) if all_ts else df.index[0]
        else:
            edit_from = df.index[0]
    else:
        edit_from = _to_utc(edit_from)

    # Find starting row index
    if edit_from not in df.index:
        # Snap to the next available hour-ending timestamp
        pos = df.index.searchsorted(edit_from)
        if pos >= len(df.index):
            raise ValueError("edit_from is after the last forecast hour.")
        edit_from = df.index[pos]

    start_idx = df.index.get_loc(edit_from)

    # Seed AF at the hour before we start recomputation
    if start_idx == 0:
        if initial_abay_ft is None:
            raise ValueError("initial_abay_ft is required when editing the first forecast hour.")
        AF_prev = float(abay_feet_to_af(initial_abay_ft))
        H_prev = float(initial_abay_ft)
    else:
        prev_ts = df.index[start_idx - 1]
        if 'ABAY_af' in df.columns and pd.notna(df.at[prev_ts, 'ABAY_af']):
            AF_prev = float(df.at[prev_ts, 'ABAY_af'])
            H_prev  = float(df.at[prev_ts, 'ABAY_ft']) if 'ABAY_ft' in df.columns and pd.notna(df.at[prev_ts, 'ABAY_ft']) else float(abay_af_to_feet(AF_prev))
        else:
            if initial_abay_ft is None:
                raise ValueError("Need initial_abay_ft to seed recalculation (ABAY_af missing at previous hour).")
            AF_prev = float(abay_feet_to_af(initial_abay_ft))
            H_prev = float(initial_abay_ft)

    # Normalise mode once for vector ops
    mode_norm = normalize_mode_series(df['Mode'])

    # Pre-pull series to avoid repeated lookups
    r4  = pd.to_numeric(df['R4_Flow'], errors='coerce').fillna(0.0)
    r30 = pd.to_numeric(df['R30_Flow'], errors='coerce').fillna(0.0)
    r20 = pd.to_numeric(df['R20_Flow'], errors='coerce').fillna(0.0)
    r5l = pd.to_numeric(df['R5L_Flow'], errors='coerce').fillna(0.0)
    r26 = pd.to_numeric(df['R26_Flow'], errors='coerce').fillna(0.0)
    bias = pd.to_numeric(df.get('bias_cfs', 0.0), errors='coerce').fillna(0.0)
    mfra = pd.to_numeric(df['MFRA_MW'], errors='coerce').fillna(0.0)
    g_user = pd.to_numeric(df['OXPH_generation_MW'], errors='coerce').fillna(0.0)
    float_ft = pd.to_numeric(df.get('FLOAT_FT', np.nan), errors='coerce')

    # MF_1_2
    mf12_mw = mf12_mw_from_mfra(mfra, r4, r5l, mode_norm)
    mf12_cfs = mf12_cfs_from_mw_quadratic(mf12_mw)

    # Containers for recomputed columns
    ABAY_AF = df.get('ABAY_af', pd.Series(index=df.index, dtype=float)).copy()
    ABAY_FT = df.get('ABAY_ft', pd.Series(index=df.index, dtype=float)).copy()
    G_USED  = g_user.copy()
    OXPH_CFS = df.get('OXPH_outflow_cfs', pd.Series(index=df.index, dtype=float)).copy()
    REG = df.get('Regulated_component_cfs', pd.Series(index=df.index, dtype=float)).copy()
    HEAD = df.get('Head_limit_MW', pd.Series(index=df.index, dtype=float)).copy()

    VIOL_MIN = pd.Series(False, index=df.index)
    VIOL_FLOAT = pd.Series(False, index=df.index)
    VIOL_HEAD = pd.Series(False, index=df.index)

    f = constants.OXPH_MW_TO_CFS_FACTOR
    off = constants.OXPH_MW_TO_CFS_OFFSET

    for t in range(start_idx, len(df.index)):
        ts = df.index[t]

        # Base inflow & bias
        base = r30.iloc[t] + r4.iloc[t] + (r20.iloc[t] - r5l.iloc[t]) - r26.iloc[t] + bias.iloc[t]

        if mode_norm.iloc[t] == 'SPILL':
            known = base + mf12_cfs.iloc[t] - off
            regulated = np.nan  # not used in SPILL
        else:
            # Scalar regulated component for this hour
            term1 = min(886.0, (float(mf12_cfs.iloc[t]) + float(r4.iloc[t])) - float(r5l.iloc[t]))
            term2 = max(0.0, float(r4.iloc[t]) - float(r5l.iloc[t]))
            regulated = max(term1, term2)
            known = base + regulated - off

        # Apply head cap first, then enforce min/max bounds.
        # Head cap limits the maximum based on elevation physics, but can go
        # negative in pathological cases (very low known_cfs). The min/max
        # clamp MUST run last so generation never goes below OXPH_MIN_MW.
        g = G_USED.iloc[t]

        if clamp_to_head:
            cap = _head_limited_cap_mw(H_prev, known)
            if g > cap + 1e-9:
                g = cap
                VIOL_HEAD.iloc[t] = True

        if clamp_to_minmax:
            g = max(constants.OXPH_MIN_MW, min(constants.OXPH_MAX_MW, g))

        # Update storage
        AF_t = AF_prev + AF_PER_CFS_HOUR * (known - f * g)
        H_t = float(abay_af_to_feet(AF_t))

        # Operational float cap: once float is reached, bypass gates hold ABAY at float.
        if not np.isnan(float_ft.iloc[t]) and H_t > float(float_ft.iloc[t]):
            H_t = float(float_ft.iloc[t])
            AF_t = float(abay_feet_to_af(H_t))

        # Diagnostics & limits
        head_lim = constants.OXPH_HEAD_LOSS_SLOPE * H_t + constants.OXPH_HEAD_LOSS_INTERCEPT
        HEAD.iloc[t] = head_lim
        OXPH_CFS.iloc[t] = f * g + off
        REG.iloc[t] = (regulated.iloc[0] if isinstance(regulated, pd.Series) else regulated) if regulated is not None else np.nan
        ABAY_AF.iloc[t] = AF_t
        ABAY_FT.iloc[t] = H_t
        G_USED.iloc[t] = g

        if not np.isnan(float_ft.iloc[t]):
            VIOL_FLOAT.iloc[t] = H_t > float_ft.iloc[t]
        VIOL_MIN.iloc[t] = H_t < float(constants.ABAY_MIN_ELEV_FT)

        # Carry forward
        AF_prev = AF_t
        H_prev = H_t

    # Write back
    df.loc[df.index[start_idx]:, 'ABAY_af'] = ABAY_AF.loc[df.index[start_idx]:]
    df.loc[df.index[start_idx]:, 'ABAY_ft'] = ABAY_FT.loc[df.index[start_idx]:]
    df.loc[df.index[start_idx]:, 'OXPH_generation_MW'] = G_USED.loc[df.index[start_idx]:]
    df.loc[df.index[start_idx]:, 'OXPH_outflow_cfs'] = OXPH_CFS.loc[df.index[start_idx]:]
    df.loc[df.index[start_idx]:, 'Head_limit_MW'] = HEAD.loc[df.index[start_idx]:]
    df.loc[df.index[start_idx]:, 'Regulated_component_cfs'] = REG.loc[df.index[start_idx]:].astype(float)
    df.loc[df.index[start_idx]:, 'MF_1_2_MW'] = mf12_mw.loc[df.index[start_idx]:]
    df.loc[df.index[start_idx]:, 'MF_1_2_cfs'] = mf12_cfs.loc[df.index[start_idx]:]

    df.loc[df.index[start_idx]:, 'violates_min'] = VIOL_MIN.loc[df.index[start_idx]:]
    df.loc[df.index[start_idx]:, 'violates_float'] = VIOL_FLOAT.loc[df.index[start_idx]:]
    df.loc[df.index[start_idx]:, 'violates_head'] = VIOL_HEAD.loc[df.index[start_idx]:]

    return df
