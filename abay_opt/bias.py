# abay_opt/bias.py
import pandas as pd
from .physics import abay_feet_to_af, expected_abay_net_cfs, expected_abay_series_from_net
from .utils import CFS_PER_AF_HOUR, AF_PER_CFS_HOUR

def compute_bias_cfs_24h(lookback_df: pd.DataFrame) -> float:
    """24h average bias (cfs) = actual_net - expected_net (signed, can be ±)."""
    if lookback_df.empty:
        return 0.0
    exp_net = expected_abay_net_cfs(lookback_df).astype(float)
    elev = lookback_df['Afterbay_Elevation']
    af = elev.apply(abay_feet_to_af)
    dAF = af.diff()
    act_net = dAF * CFS_PER_AF_HOUR
    pair = pd.concat([exp_net.rename('exp'), act_net.rename('act')], axis=1).dropna()
    if pair.empty:
        return 0.0
    hourly_bias = pair['act'] - pair['exp']
    trimmed = hourly_bias.clip(lower=-2000.0, upper=2000.0)
    return float(trimmed.tail(24).mean())

def expected_series_for_lookback(lookback_df: pd.DataFrame) -> pd.DataFrame:
    exp_net = expected_abay_net_cfs(lookback_df).astype(float)
    start_af = float(abay_feet_to_af(float(lookback_df['Afterbay_Elevation'].iloc[0])))
    return expected_abay_series_from_net(start_af, exp_net)

def hourly_abay_error_diagnostics(lookback_df: pd.DataFrame) -> pd.DataFrame:
    """Per‑hour expected vs actual ABAY net and the error (cfs/AF)."""
    exp = expected_abay_net_cfs(lookback_df).astype(float).rename("ABAY_NET_expected_cfs")
    elev = lookback_df['Afterbay_Elevation']
    af = elev.apply(abay_feet_to_af)
    dAF = af.diff()  # hour‑ending deltas
    act = (dAF * CFS_PER_AF_HOUR).rename("ABAY_NET_actual_cfs")
    df = pd.concat([exp, act], axis=1)
    df['abay_error_cfs_hourly'] = df['ABAY_NET_actual_cfs'] - df['ABAY_NET_expected_cfs']
    df['abay_error_af_hourly']  = df['abay_error_cfs_hourly'] * AF_PER_CFS_HOUR
    return df
