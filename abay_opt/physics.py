
import numpy as np
import pandas as pd
from .utils import AF_PER_CFS_HOUR, CFS_PER_AF_HOUR, to_numeric_series
from . import constants

# ---------- Stage–storage (quadratic fit confirmed) ----------
# ABAY_AF = 0.6311303 * ft^2 - 1403.8 * ft + 780566
A_COEF = 0.6311303
B_COEF = -1403.8
C_COEF = 780566.0

def abay_feet_to_af(ft):
    ft = to_numeric_series(ft)
    return A_COEF * ft**2 + B_COEF * ft + C_COEF

def abay_af_to_feet(af):
    # Solve A_COEF*x^2 + B_COEF*x + (C_COEF - af) = 0 (take the positive/larger root)
    af = to_numeric_series(af)
    a = A_COEF
    b = B_COEF
    c = C_COEF - af
    disc = b*b - 4*a*c
    disc = np.maximum(disc, 0.0)
    return (-b + np.sqrt(disc)) / (2*a)


# --- Normalize CCS mode: PI gives 0 (GEN) / 1 (SPILL) ---
def normalize_mode_series(mode):
    """
    Accepts a pandas Series (preferred) or scalar with values like:
      0, 1, '0', '1', 'GEN', 'SPILL' (case-insensitive)
    Returns a Series/scalar of 'GEN' or 'SPILL'.
    """
    import pandas as pd
    import numpy as np

    if isinstance(mode, pd.Series):
        # Try numeric first
        as_num = pd.to_numeric(mode, errors='coerce')
        out = pd.Series(index=mode.index, dtype=object)
        # numeric: >=0.5 -> SPILL, else GEN
        mask_num = as_num.notna()
        out.loc[mask_num] = np.where(as_num[mask_num] >= 0.5, 'SPILL', 'GEN')
        # non-numeric: map strings
        s = mode.astype(str).str.upper()
        out.loc[~mask_num] = s[~mask_num].replace({'0': 'GEN', '1': 'SPILL'})
        out = out.where(out.isin(['GEN', 'SPILL']), 'GEN')
        return out

    # scalar
    try:
        v = float(mode)
        return 'SPILL' if v >= 0.5 else 'GEN'
    except Exception:
        t = str(mode).upper()
        if t in ('SPILL', 'GEN'):
            return t
        if t == '1':
            return 'SPILL'
        if t == '0':
            return 'GEN'
        return 'GEN'


# ---------- Powerhouse & MF_1_2 conversions ----------

def oxph_cfs_from_mw_linear(mw: pd.Series) -> pd.Series:
    """Use the *linear* curve from the goal doc: cfs = 163.73*MW + 83."""
    mw = to_numeric_series(mw)
    return constants.OXPH_MW_TO_CFS_FACTOR * mw + constants.OXPH_MW_TO_CFS_OFFSET

def mf12_mw_from_mfra(mfra_mw: pd.Series, r4_cfs: pd.Series, r5l_cfs: pd.Series, mode: pd.Series) -> pd.Series:
    """Apply GEN/SPILL rule to get MF_1_2 MW from MFRA MW and side-water (R4-R5L)."""
    mfra_mw = to_numeric_series(mfra_mw)
    r4 = to_numeric_series(r4_cfs)
    r5l = to_numeric_series(r5l_cfs)
    mode = normalize_mode_series(mode)

    reduction = np.minimum(86.0, np.maximum(0.0, (r4 - r5l) / 10.0))
    mf12_gen = (mfra_mw - reduction) * 0.59
    mf12_spill = mfra_mw * 0.59
    out = np.where(mode.eq('SPILL'), mf12_spill, mf12_gen)
    return pd.Series(out, index=mfra_mw.index).clip(lower=0.0)

def mf12_cfs_from_mw_quadratic(mw: pd.Series) -> pd.Series:
    """Use confirmed quadratic MW->cfs for MF_1_2 (coeffs from constants)."""
    mw = to_numeric_series(mw).clip(lower=0.0)
    return (constants.MFRA_MW2_TO_CFS_FACTOR * (mw**2)
            + constants.MFRA_MW_TO_CFS_FACTOR * mw
            + constants.MFRA_MW_TO_CFS_OFFSET)

# ---------- Net inflow (ABAY_NET) formulas ----------

def regulated_component_gen(mf12_cfs: pd.Series, r4_cfs: pd.Series, r5l_cfs: pd.Series) -> pd.Series:
    r4 = to_numeric_series(r4_cfs)
    r5l = to_numeric_series(r5l_cfs)
    mf = to_numeric_series(mf12_cfs)
    term1 = np.minimum(886.0, (mf + r4) - r5l)
    term2 = np.maximum(0.0, r4 - r5l)
    return pd.Series(np.maximum(term1, term2), index=mf.index)

def expected_abay_net_cfs(df: pd.DataFrame) -> pd.Series:
    """
    Compute expected ABAY_NET (cfs) given a DataFrame containing historical series:
    R30_Flow, R4_Flow, R20_Flow, R5L_Flow, R26_Flow, MFP_Total_Gen_GEN_MDFK_and_RA (MW),
    Oxbow_Power (MW), CCS_Mode.
    """
    r30 = to_numeric_series(df['R30_Flow'])
    r4 = to_numeric_series(df['R4_Flow'])
    r20 = to_numeric_series(df['R20_Flow'])
    r5l = to_numeric_series(df['R5L_Flow'])
    r26 = to_numeric_series(df['R26_Flow'])
    oxph_mw = to_numeric_series(df['Oxbow_Power'])
    mfra_mw = to_numeric_series(df['MFP_Total_Gen_GEN_MDFK_and_RA'])
    mode = normalize_mode_series(df['CCS_Mode'])

    mf12_mw = mf12_mw_from_mfra(mfra_mw, r4, r5l, mode)
    mf12_cfs = mf12_cfs_from_mw_quadratic(mf12_mw)
    oxph_cfs = oxph_cfs_from_mw_linear(oxph_mw)

    base = r30 + r4 + (r20 - r5l) - r26
    regulated = regulated_component_gen(mf12_cfs, r4, r5l)

    gen_mask = ~mode.eq('SPILL')
    net_gen = base + regulated - oxph_cfs   # If in GEN mode
    net_spill = base + mf12_cfs - oxph_cfs  # If in SPILL mode
    return pd.Series(np.where(gen_mask, net_gen, net_spill), index=df.index)

def expected_abay_series_from_net(start_af: float, net_cfs_series: pd.Series) -> pd.DataFrame:
    """
    Integrate net cfs to AF and convert to ft, returning a DataFrame with columns
    ABAY_af and ABAY_ft. Assumes hour-ending time steps.
    """
    af = [start_af]
    for c in net_cfs_series:
        af.append(af[-1] + c * AF_PER_CFS_HOUR)
    af_series = pd.Series(af[1:], index=net_cfs_series.index)
    ft_series = abay_af_to_feet(af_series)
    return pd.DataFrame({'Expected_ABAY_af': af_series, 'Expected_ABAY_ft': ft_series})
