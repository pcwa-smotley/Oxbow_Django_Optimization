# abay_opt/caiso_da.py
"""
CAISO Day Ahead Awards service for MFRA (Middle Fork) forecast.

Wraps caiso_config/Programs/caiso_api.py to fetch DAM awards for MFP1
and provide hourly MW Series aligned to the optimization forecast index.

Gracefully degrades to (None, 'persistence') on any failure.
"""

import logging
import os
import sys
from datetime import date, datetime, timedelta, timezone
from typing import Optional, Tuple

import pandas as pd
import pytz

logger = logging.getLogger(__name__)

PACIFIC_TZ = pytz.timezone('America/Los_Angeles')

# ---------------------------------------------------------------------------
# Lazy import of caiso_api — adds Programs/ to sys.path on first call
# ---------------------------------------------------------------------------
_caiso_api = None


def _get_caiso_api():
    """Lazy-load caiso_api module, handling import path issues."""
    global _caiso_api
    if _caiso_api is not None:
        return _caiso_api

    try:
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        programs_dir = os.path.join(project_root, 'caiso_config', 'Programs')
        if programs_dir not in sys.path:
            sys.path.insert(0, programs_dir)

        from caiso_config.Programs import caiso_api
        _caiso_api = caiso_api
        return _caiso_api
    except ImportError as e:
        logger.warning(f"Cannot import caiso_api: {e}. DA awards will not be available.")
        return None


# ---------------------------------------------------------------------------
# Core fetch + aggregation
# ---------------------------------------------------------------------------

def _trade_date_to_utc_range(trade_dt: date) -> Tuple[str, str]:
    """
    Convert a CAISO trade/delivery date to UTC start/end for the API query.

    CAISO market days run in Pacific Prevailing Time.
    Delivery date Feb 8 → midnight-to-midnight PPT → UTC range.
    """
    start_pt = PACIFIC_TZ.localize(datetime(trade_dt.year, trade_dt.month, trade_dt.day, 0, 0, 0))
    end_pt = start_pt + timedelta(days=1)

    start_utc = start_pt.astimezone(timezone.utc)
    end_utc = end_pt.astimezone(timezone.utc)

    return (
        start_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        end_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
    )


def fetch_mfp1_da_awards(trade_dt: date) -> Optional[pd.DataFrame]:
    """
    Fetch DAM awards for SC_ID='MFP1' for a given delivery date.

    Returns DataFrame with columns [resource, intervalStartTime, intervalEndTime, MW, ...]
    or None on failure.
    """
    api = _get_caiso_api()
    if api is None:
        return None

    try:
        start_str, end_str = _trade_date_to_utc_range(trade_dt)
        logger.info(f"Fetching CAISO DA awards for {trade_dt} ({start_str} to {end_str})")
        df = api.fetch_dam_awards(start_str, end_str)

        if df is None or df.empty:
            logger.info(f"No DA awards returned for {trade_dt}")
            return None

        logger.info(f"Received {len(df)} DA award records for {trade_dt}")
        return df

    except Exception as e:
        logger.error(f"Error fetching CAISO DA awards for {trade_dt}: {e}", exc_info=True)
        return None


MDFK_RESOURCE = 'MDFKRL_2_PROJCT'


def aggregate_hourly_mw(awards_df: pd.DataFrame) -> Optional[pd.Series]:
    """
    Extract MDFKRL_2_PROJCT CLEARED energy awards per hour.

    CAISO returns multiple schedule types per resource:
      - CLEARED = the actual DA award (what we want)
      - MARKET  = the bid that cleared (duplicate MW, don't double-count)
      - SELF    = self-scheduled portion

    We filter to resource=MDFKRL_2_PROJCT, product=EN, scheduleType=CLEARED.

    Returns a pd.Series indexed by interval_start (UTC datetime), values = MW.
    """
    if awards_df is None or awards_df.empty:
        return None

    try:
        df = awards_df.copy()

        # Log all resources for diagnostics
        if 'resource' in df.columns:
            resources = df['resource'].unique().tolist()
            logger.info(f"DA awards contain resources: {resources}")
        if 'scheduleType' in df.columns:
            stypes = df['scheduleType'].unique().tolist()
            logger.info(f"DA awards contain scheduleTypes: {stypes}")

        # Filter to MDFKRL_2_PROJCT resource
        if 'resource' in df.columns:
            mdfk_mask = df['resource'].str.upper() == MDFK_RESOURCE.upper()
            if not mdfk_mask.any():
                logger.warning(f"No records for resource {MDFK_RESOURCE}. "
                               f"Available: {df['resource'].unique().tolist()}")
                return None
            df = df[mdfk_mask]
            logger.info(f"Filtered to {MDFK_RESOURCE}: {len(df)} records")

        # Filter to CLEARED schedule type (the actual DA award)
        if 'scheduleType' in df.columns:
            cleared_mask = df['scheduleType'].str.upper() == 'CLEARED'
            if cleared_mask.any():
                df = df[cleared_mask]
                logger.info(f"Filtered to CLEARED: {len(df)} records")
            else:
                logger.warning("No CLEARED records found — using all schedule types")

        # Filter to energy product
        if 'productType' in df.columns:
            en_mask = df['productType'].str.upper().isin(['EN', 'ENERGY'])
            if en_mask.any():
                df = df[en_mask]

        if 'MW' not in df.columns or 'intervalStartTime' not in df.columns:
            logger.warning(f"DA awards missing required columns. Have: {list(df.columns)}")
            return None

        # Parse interval start times to datetime
        df['interval_start'] = pd.to_datetime(df['intervalStartTime'], utc=True)
        df['mw_value'] = pd.to_numeric(df['MW'], errors='coerce').fillna(0)

        # Sum MW per hour (should be one row per hour after filtering, but sum to be safe)
        hourly = df.groupby('interval_start')['mw_value'].sum().sort_index()
        hourly.name = 'MFRA_MW_forecast'

        logger.info(f"Aggregated DA awards for {MDFK_RESOURCE}: {len(hourly)} hours, "
                     f"avg={hourly.mean():.1f} MW, range=[{hourly.min():.1f}, {hourly.max():.1f}]")
        return hourly

    except Exception as e:
        logger.error(f"Error aggregating DA awards: {e}", exc_info=True)
        return None


# ---------------------------------------------------------------------------
# High-level interface for build_inputs.py
# ---------------------------------------------------------------------------

def get_da_awards_for_forecast(forecast_index: pd.DatetimeIndex) -> Tuple[Optional[pd.Series], str]:
    """
    Look up stored DA awards that overlap with the forecast time range.

    Queries the Django CAISODAAwardSummary model. If no Django ORM is available
    (e.g., running from CLI), falls back gracefully.

    Returns:
        (series_or_none, source_label)
        source_label is 'da_awards' or 'persistence'
    """
    try:
        # Import Django model — may fail if Django isn't configured
        from django.db import OperationalError, ProgrammingError
        from optimization_api.models import CAISODAAwardSummary

        # Determine which trade dates cover the forecast window
        start_utc = forecast_index.min()
        end_utc = forecast_index.max()

        summaries = CAISODAAwardSummary.objects.filter(
            interval_start_utc__gte=start_utc,
            interval_start_utc__lte=end_utc,
        ).order_by('interval_start_utc')

        if not summaries.exists():
            logger.info("No stored DA awards found for forecast window")
            return None, 'persistence'

        # Build a Series from stored summaries
        # Django DateTimeField values are already tz-aware; avoid double-tz error
        data = {}
        for s in summaries:
            ts = pd.Timestamp(s.interval_start_utc)
            if ts.tzinfo is None:
                ts = ts.tz_localize('UTC')
            data[ts] = s.total_mw
        da_series = pd.Series(data, name='MFRA_MW_forecast').sort_index()

        # Align to forecast index; return whatever hours we have.
        # DA awards typically cover only 24 h but the forecast may be 72 h,
        # so we return partial coverage and let build_inputs fill the gaps.
        aligned = da_series.reindex(forecast_index, method='nearest', tolerance='30min')
        covered = int(aligned.notna().sum())
        coverage = covered / len(forecast_index)

        if covered == 0:
            logger.info("No DA awards align with forecast window")
            return None, 'persistence'

        logger.info(f"Using stored DA awards for MFRA forecast ({coverage:.0%} coverage, "
                     f"{covered}/{len(forecast_index)} hours)")
        return aligned, 'da_awards'

    except (ImportError, OperationalError, ProgrammingError) as e:
        logger.debug(f"Cannot query DA awards from DB: {e}")
        return None, 'persistence'
    except Exception as e:
        logger.warning(f"Unexpected error querying DA awards: {e}")
        return None, 'persistence'
