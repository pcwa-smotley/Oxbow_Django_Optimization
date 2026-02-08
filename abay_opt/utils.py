
import pandas as pd

# Conversions
AF_PER_CFS_HOUR = 3600.0 / 43560.0
CFS_PER_AF_HOUR = 1.0 / AF_PER_CFS_HOUR

def to_numeric_series(s, default=0.0):
    """
    Returns:
      - pandas.Series when input is a Series/list/ndarray (numeric, NaNs filled with default)
      - float when input is a scalar
    """
    import pandas as pd, numpy as np
    if isinstance(s, pd.Series):
        return pd.to_numeric(s, errors="coerce").fillna(default)
    if isinstance(s, (list, tuple, np.ndarray)):
        ser = pd.Series(s)
        return pd.to_numeric(ser, errors="coerce").fillna(default)
    # scalar
    try:
        val = float(s)
        if np.isnan(val):
            return float(default)
        return val
    except Exception:
        return float(default)


def hour_ending_range(start_ts_utc, periods, minutes=60):
    """
    Create a DatetimeIndex (UTC) with 'hour-ending' semantics: timestamps are
    the *end* of each interval.
    """
    freq = f"{minutes}min"
    return pd.date_range(start=start_ts_utc, periods=periods, freq=freq, tz="UTC")

def is_daytime_hour_pt(ts_pt: pd.Timestamp) -> bool:
    # 08:00 through 20:00 inclusive
    h = ts_pt.hour
    return 8 <= h <= 20

def clip_series(s: pd.Series, lo=None, hi=None) -> pd.Series:
    if lo is not None: s = s.clip(lower=lo)
    if hi is not None: s = s.clip(upper=hi)
    return s
