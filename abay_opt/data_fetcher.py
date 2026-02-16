# data_fetcher.py
import requests
import json
import pandas as pd
import numpy as np
# Ensure datetime, timedelta, time are imported correctly
from datetime import datetime, timedelta, time as dt_time
import pytz
import logging
from scipy import stats
import os
import time
import configparser
from pathlib import Path

# Assume constants.py and calculations.py are accessible
from . import constants


# Set timezone objects from constants
PACIFIC_TZ = constants.PACIFIC_TZ
UTC_TZ = constants.UTC_TZ

#logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# === Upstream API Functions ===
# === Upstream API Functions ===
def get_single_site_forecasts(api_key, site_id, forecast_source, columns_to_request):
    """
    Fetches forecasts for a single site from the Upstream API using issueTimeAfterDate
    to get the most recent forecasts.

    Args:
        api_key (str): The API key for authentication.
        site_id (str): The ID of the site to fetch forecasts for.
        forecast_source (str): The source of the forecast (e.g., "hydroforecast-short-term", "cnrfc").
        columns_to_request (list): A list of column names to request for the given source.

    Returns:
        dict or None: The JSON response from the API, or None if an error occurs.
    """
    url = constants.UPSTREAM_API_URL
    now_utc = datetime.now(UTC_TZ)

    # Set issueTimeAfterDate to fetch forecasts issued recently
    # e.g., in the last 24-48 hours to ensure capturing the latest.
    # This duration can be made a constant if needed.
    issue_after_utc = now_utc - timedelta(hours=getattr(constants, 'UPSTREAM_ISSUE_TIME_LOOKBACK_HOURS', 48))
    issue_after_str = issue_after_utc.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'

    logger.info(f"Requesting Upstream API data for site: {site_id}, source: {forecast_source}")
    logger.info(f"Fetching forecasts issued after: {issue_after_str}")
    logger.info(f"Requesting columns: {columns_to_request}")

    payload = {
        "queries": [
            {
                "source": forecast_source,
                "siteId": site_id,
                "columns": columns_to_request,
                "unitSystem": "US",
                "rateVolumeMode": "rate",
                "timeAggregation": "1H", # Assuming 1H is desired for both
                "aggregationMethod": "mean", # Assuming mean is desired for both
                "issueTimeAfterDate": issue_after_str # Use issueTimeAfterDate
                # "initializationTimes" is removed as per new understanding
            }
        ]
    }

    response = None
    try:
        resp = requests.post(
            url,
            data=json.dumps(payload),
            headers={"Authorization": api_key, "Content-Type": "application/json"},
            timeout=60
        )
        response = resp
        logger.info(f"API Response Status for {site_id} ({forecast_source}): {resp.status_code}")
        if resp.status_code == 404:
            logger.error(f"API returned 404 Not Found for site {site_id}, source {forecast_source}.")
            logger.error(f"Response Text: {resp.text[:500]}...")
            return None
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as e:
        status_code = response.status_code if response is not None else 'N/A'
        response_text = response.text if response is not None else 'No response text'
        logger.error(f"Upstream API request failed for {site_id} ({forecast_source}): Status {status_code}, Error: {e}")
        logger.error(f"Failed URL: {url}")
        # Log payload without API Key
        payload_log = json.loads(json.dumps(payload)) # Deep copy
        logger.error(f"Request Payload: {json.dumps(payload_log, indent=2)}")
        logger.error(f"Response Text: {response_text[:500]}...")
        return None

def forecasts_to_dataframe(response_data, site_short_name, forecast_source, target_column_name):
    """
    Converts forecast JSON data to a pandas DataFrame.
    It expects that the response_data might contain multiple forecasts (e.g., if multiple
    were issued after issueTimeAfterDate) and will select the one with the LATEST issueTime.

    Args:
        response_data (dict): The JSON response from the Upstream API.
        site_short_name (str): Short name for the site (e.g., "R4", "R30").
        forecast_source (str): The source of the forecast (e.g., "hydroforecast-short-term", "cnrfc").
        target_column_name (str): The specific column from the API response to extract as the primary forecast value
                                 (e.g., "discharge_mean" or "ensemble_forecast_avg").

    Returns:
        pd.DataFrame: A DataFrame with the forecast data, or an empty DataFrame on error.
                      The primary forecast column will be named f"{site_short_name}_{target_column_name}".
    """
    if not response_data:
        logger.warning(f"No response data provided for {site_short_name} from {forecast_source}")
        return pd.DataFrame()

    if "data" not in response_data or not response_data["data"]:
        logger.warning(f"No 'data' key in Upstream API response for {site_short_name} ({forecast_source})")
        return pd.DataFrame()

    # The API returns a list of query responses, typically one if one query was sent.
    query_response_obj = response_data["data"][0] if isinstance(response_data["data"], list) and response_data["data"] else None
    if not query_response_obj:
        logger.warning(f"Query response object empty/invalid for {site_short_name} ({forecast_source})")
        return pd.DataFrame()

    # 'forecasts' is a list within the query_response_obj
    forecasts_list = query_response_obj.get("forecasts", [])
    if not forecasts_list:
        logger.warning(f"No 'forecasts' array in API response for {site_short_name} ({forecast_source}). This might be normal if no new forecasts were issued since 'issueTimeAfterDate'.")
        return pd.DataFrame()

    try:
        # Select the forecast with the latest issueTime from the list
        latest_forecast_data = max(forecasts_list, key=lambda f: pd.Timestamp(f["issueTime"]))
        logger.info(f"Using forecast issued at: {latest_forecast_data['issueTime']} (Initialization: {latest_forecast_data['initializationTime']}) for {site_short_name} ({forecast_source})")

        valid_times = latest_forecast_data["validTimes"]
        # data_dict contains the actual forecast series, e.g., {"discharge_mean": [...], "discharge_q0.5": [...]}
        forecast_series_data_dict = latest_forecast_data["data"]

        rows = []
        # We are interested in the target_column_name specifically for the main forecast value
        if target_column_name not in forecast_series_data_dict:
            logger.warning(f"Target column '{target_column_name}' not found in data for {site_short_name} ({forecast_source}). Available keys in data: {list(forecast_series_data_dict.keys())}")
            return pd.DataFrame()

        series_values = forecast_series_data_dict[target_column_name]

        if series_values is None or (isinstance(series_values, (list, tuple)) and len(series_values) == 0):
            logger.warning(f"Target column '{target_column_name}' exists but contains no data (null/empty) for {site_short_name} ({forecast_source}). "
                           f"The upstream API returned an empty series — this may indicate the forecast has not been issued yet for the requested period.")
            return pd.DataFrame()

        for i, vt_str in enumerate(valid_times):
            try:
                # API validTimes are usually UTC, ensure this
                vt = pd.Timestamp(vt_str).tz_convert(constants.UTC_TZ)
            except Exception as ts_err:
                logger.warning(f"Could not parse validTime timestamp '{vt_str}' for {site_short_name}: {ts_err}. Skipping.")
                continue

            row_data = {"validTimeUTC": vt}
            # This will be the column name in the intermediate DataFrame, e.g., "R4_discharge_mean"
            output_col_name_intermediate = f"{site_short_name}_{target_column_name}"

            if i < len(series_values) and series_values[i] is not None:
                try:
                    row_data[output_col_name_intermediate] = float(series_values[i])
                except (ValueError, TypeError):
                    row_data[output_col_name_intermediate] = np.nan
                    logger.warning(f"Non-numeric value '{series_values[i]}' for {target_column_name} at index {i} in validTime {vt_str} for {site_short_name}")
            else:
                row_data[output_col_name_intermediate] = np.nan
                if i >= len(series_values):
                    logger.debug(f"Missing or incomplete data for {target_column_name} at index {i} in validTime {vt_str} for {site_short_name}")

            rows.append(row_data)

        df = pd.DataFrame(rows)
        if df.empty:
            return df

        df.set_index("validTimeUTC", inplace=True)
        df.sort_index(inplace=True)
        return df

    except Exception as e:
        logger.exception(f"Error processing forecast data for {site_short_name} ({forecast_source}): {e}")
        return pd.DataFrame()

def get_combined_r4_r30_forecasts(forecast_source=constants.DEFAULT_UPSTREAM_FORECAST_SOURCE,
                                  fallback_to_cnrfc=True):
    """
    Fetch and combine R4 and R30 forecasts with per-site fallback to CNRFC if HydroForecast is missing.
    Returns a DataFrame with columns ['R30_Forecast_CFS', 'R4_Forecast_CFS'] (whichever are available).
    """
    # --- Load API key (same logic as before) ---
    try:
        config = configparser.ConfigParser()
        current_file = Path(__file__).resolve()
        project_root = current_file.parent.parent  # Oxbow_Django_Optimization
        config_path = project_root / 'abay_opt' / 'config'
        if not config_path.exists():
            config_path = Path('config')
            if not config_path.exists():
                raise FileNotFoundError(f"Upstream API config file not found at {config_path}")
        config.read(str(config_path))
        api_key = config.get("UPSTREAM_API_KEY", "api_key", fallback=None)
        if not api_key:
            raise ValueError("api_key not found in config file.")
    except Exception as e:
        logger.error(f"Failed to get Upstream API key: {e}")
        return pd.DataFrame()

    def _target_for_source(src: str):
        if src == constants.UPSTREAM_FORECAST_SOURCE_CNRFC:
            return constants.UPSTREAM_CNRFC_REQUEST_COLUMNS, constants.UPSTREAM_CNRFC_TARGET_COLUMN
        elif src == constants.UPSTREAM_FORECAST_SOURCE_HYDROFORECAST:
            return constants.UPSTREAM_HYDROFORECAST_REQUEST_COLUMNS, constants.UPSTREAM_HYDROFORECAST_TARGET_COLUMN
        else:
            return None, None

    def _fetch_site(site_key: str, src: str) -> pd.DataFrame:
        """Return one-column DF named '<site>_Forecast_CFS' resampled & in UTC, or empty DF on failure."""
        cols, target = _target_for_source(src)
        if not cols or not target:
            logger.error(f"Unsupported forecast source '{src}' for site {site_key}")
            return pd.DataFrame()

        site_id = constants.UPSTREAM_SITE_IDS.get(site_key)
        if not site_id:
            logger.error(f"Unknown site_key {site_key}; expected 'R4' or 'R30'.")
            return pd.DataFrame()

        j = get_single_site_forecasts(api_key, site_id, src, cols)
        df = forecasts_to_dataframe(j, site_key, src, target) if j else pd.DataFrame()
        if df.empty:
            return pd.DataFrame()

        old_col = f"{site_key}_{target}"
        new_col = f"{site_key}_Forecast_CFS"
        if old_col in df.columns:
            df = df.rename(columns={old_col: new_col})[[new_col]]
        else:
            logger.warning(f"Column {old_col} not found in {src} payload for {site_key}.")
            return pd.DataFrame()

        # Ensure datetime index, UTC tz, and resample to SIMULATION_INTERVAL_MINUTES
        if not isinstance(df.index, pd.DatetimeIndex):
            try:
                df.index = pd.to_datetime(df.index)
            except Exception as e:
                logger.error(f"{site_key} forecast index not convertible to datetime: {e}")
                return pd.DataFrame()

        if df.index.tz is None:
            df = df.tz_localize(constants.UTC_TZ)
        else:
            df = df.tz_convert(constants.UTC_TZ)

        target_interval = f'{constants.SIMULATION_INTERVAL_MINUTES}min'
        try:
            df = df.resample(target_interval, label='left', closed='left').mean()
            interp_limit = (3 * 60) // constants.SIMULATION_INTERVAL_MINUTES if constants.SIMULATION_INTERVAL_MINUTES > 0 else 3
            df = df.interpolate(method='time', limit=interp_limit).ffill().bfill()
        except Exception as e:
            logger.error(f"Resample/interpolate failed for {site_key} ({src}): {e}")

        return df

    primary = forecast_source
    df_r4 = _fetch_site("R4", primary)
    df_r30 = _fetch_site("R30", primary)

    # --- Per-site fallback to CNRFC when primary is HydroForecast (requested behavior) ---
    if fallback_to_cnrfc and primary == constants.UPSTREAM_FORECAST_SOURCE_HYDROFORECAST:
        if df_r4.empty:
            logger.warning("R4 forecast missing from HydroForecast; trying CNRFC fallback...")
            df_r4 = _fetch_site("R4", constants.UPSTREAM_FORECAST_SOURCE_CNRFC)
        if df_r30.empty:
            logger.warning("R30 forecast missing from HydroForecast; trying CNRFC fallback...")
            df_r30 = _fetch_site("R30", constants.UPSTREAM_FORECAST_SOURCE_CNRFC)

    # If still empty for both, give up
    if df_r4.empty and df_r30.empty:
        logger.warning(f"Both R4 and R30 forecasts failed (primary={primary}, fallback_to_cnrfc={fallback_to_cnrfc}).")
        return pd.DataFrame()

    # If one is present, return it; if both present, outer-merge
    if df_r4.empty:
        logger.warning("R4 forecast unavailable after fallback; returning R30 only.")
        return df_r30
    if df_r30.empty:
        logger.warning("R30 forecast unavailable after fallback; returning R4 only.")
        return df_r4

    return pd.merge(df_r30, df_r4, left_index=True, right_index=True, how="outer")



# === PI Web API Functions ===
def drop_numerical_outliers(df, z_thresh=3):
    # ... (Keep the version from the previous response) ...
    if 'Value' not in df.columns:
        logger.debug("No 'Value' column found for outlier detection.")
        return df
    numeric_values = pd.to_numeric(df['Value'], errors='coerce')
    original_index = df.index
    valid_numeric_mask = numeric_values.notna()
    df_numeric = df[valid_numeric_mask].copy()
    df_non_numeric = df[~valid_numeric_mask].copy()
    if df_numeric.empty:
        logger.debug("No valid numeric data found for outlier detection.")
        return df_non_numeric.reindex(original_index.union(df_non_numeric.index)).loc[original_index]

    numeric_values_clean = numeric_values[valid_numeric_mask]
    if numeric_values_clean.nunique() <= 1 or len(numeric_values_clean) < 3:
        logger.debug("Skipping z-score outlier detection (constant or small dataset).")
        outlier_removed_numeric_df = df_numeric
    else:
        try:
            z_scores = np.abs(stats.zscore(numeric_values_clean))
            is_outlier = z_scores >= z_thresh
            if is_outlier.any():
                num_outliers = is_outlier.sum()
                tag_name = df['tag_key'].iloc[0] if 'tag_key' in df.columns and not df.empty else 'Unknown Tag'
                logger.warning(f"Detected {num_outliers} outliers (z-score >= {z_thresh}) in numeric data for {tag_name}. Removing them.")
                outlier_removed_numeric_df = df_numeric[~is_outlier]
            else:
                outlier_removed_numeric_df = df_numeric
        except Exception as e:
            logger.warning(f"Could not perform z-score calculation: {e}. Skipping outlier removal.")
            outlier_removed_numeric_df = df_numeric

    result_df = pd.concat([outlier_removed_numeric_df, df_non_numeric])
    result_df = result_df.reindex(original_index)
    return result_df


class PiRequest:
    # ... (Keep the version from the previous response) ...
    base_pi_url = constants.PI_BASE_URL
    def __init__(self, db, element_type, meter_name, attribute, interpolated=True, interval_mins=constants.SIMULATION_INTERVAL_MINUTES):
        self.db = db
        self.meter_name = meter_name
        self.attribute = attribute
        self.interpolated = interpolated
        self.interval_str = f'{interval_mins}m'
        self.session = requests.Session()
        self.web_id = None
        self.meter_element_type = element_type
        try:
            self._fetch_web_id()
        except Exception as e:
             logger.error(f"Failed to initialize PiRequest due to WebID fetch error for {self.meter_name}|{self.attribute}: {e}")
             self.web_id = None

    def _construct_pi_path(self):
        base_path = f"\\\\BUSINESSPI2\\{self.db}"
        if self.meter_element_type:
            base_path += f"\\{self.meter_element_type}"
        if self.meter_name:
            base_path += f"\\{self.meter_name}"
        if self.attribute:
             base_path += f"|{self.attribute}"
        pi_path = base_path
        return pi_path

    def _fetch_web_id(self):
        attribute_lookup_url = f"{self.base_pi_url}/attributes"
        pi_path = self._construct_pi_path()
        params = {"path": pi_path}
        logger.info(f"Requesting WebId for path: {pi_path}")
        response = None
        try:
            response = self.session.get(attribute_lookup_url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            self.web_id = data.get("WebId")
            if not self.web_id:
                logger.error(f"WebId not found for path: {pi_path}. Response: {data}")
                raise ValueError(f"WebId not found for {self.meter_name}|{self.attribute}")
            logger.debug(f"Found WebId: {self.web_id} for {pi_path}")
        except requests.exceptions.RequestException as e:
            status = response.status_code if response is not None else "N/A"
            logger.error(f"Failed to fetch WebId for {pi_path}: Status {status}, Error: {e}")
            self.web_id = None
            raise
        except (ValueError, KeyError, json.JSONDecodeError) as e:
             logger.error(f"Failed to parse WebId response for {pi_path}: {e}")
             self.web_id = None
             raise

    def _get_data_url_endpoint(self):
        if not self.web_id: raise ValueError("Cannot get data URL without a valid WebId.")
        if self.interpolated: return f"{self.base_pi_url}/streams/{self.web_id}/interpolated"
        else: return f"{self.base_pi_url}/streams/{self.web_id}/summary"

    def get_data(self, start_time_utc, end_time_utc):
        if not self.web_id:
            logger.error(f"Cannot fetch data for {self.meter_name}|{self.attribute}: WebId is missing.")
            return []

        data_url = self._get_data_url_endpoint()
        start_str = start_time_utc.strftime('%Y-%m-%dT%H:%M:%SZ')
        end_str = end_time_utc.strftime('%Y-%m-%dT%H:%M:%SZ')

        if self.interpolated:
            params = {
                "startTime": start_str,
                "endTime": end_str,
                "interval": self.interval_str,
            }
            fetch_type = "Interpolated"
        else:
            # Parameters for Summary (Average) - REMOVED timeType
            params = {
                "startTime": start_str,
                "endTime": end_str,
                "summaryType": "Average",
                "summaryDuration": self.interval_str,
                # "timeType": "TimeAtEnd", # REMOVED as not supported
                "calculationBasis": "TimeWeighted",
            }
            fetch_type = "TimeAveraged Summary (Start Time)" # Indicate timestamp is start

        logger.info(f"Requesting PI data for {self.meter_name}|{self.attribute} ({fetch_type})")
        logger.debug(f"URL: {data_url}, Params: {params}")
        response = None; all_items = []; next_url = data_url
        while next_url:
            try:
                current_params = params if next_url == data_url else {}
                response = self.session.get(next_url, params=current_params, timeout=90)
                response.raise_for_status()
                j = response.json()
                items = j.get("Items", [])
                logger.info(f"Full url for {self.meter_name}|{self.attribute} request: {response.url}")
                if not items: logger.debug(f"No items received in this page for {self.meter_name}|{self.attribute}.")
                else: all_items.extend(items); logger.debug(f"Received {len(items)} items (Total: {len(all_items)}) for {self.meter_name}|{self.attribute}")
                next_url = j.get("Links", {}).get("Next")
                if next_url: logger.debug(f"Following pagination link..."); params = {}
                else: break
            except requests.exceptions.RequestException as e:
                status_code = response.status_code if response is not None else 'N/A'; response_text = response.text if response is not None else 'N/A'
                logger.error(f"PI data request failed for {self.meter_name}|{self.attribute}: Status {status_code}, Error: {e}"); logger.error(f"URL attempted: {response.url if response else next_url}"); logger.error(f"Response Text (first 500 chars): {response_text[:500]}...")
                return []
            except (json.JSONDecodeError, KeyError) as e: logger.error(f"Failed to parse PI response JSON for {self.meter_name}|{self.attribute}: {e}"); return []
            except Exception as e: logger.exception(f"Unexpected error processing PI data for {self.meter_name}|{self.attribute}: {e}"); return []

        logger.info(f"Total items received after pagination for {self.meter_name}|{self.attribute}: {len(all_items)}")
        return all_items


def process_pi_data(raw_items_list: list[dict],
                    tag_key: str,
                    tag_config: dict) -> pd.DataFrame:
    """
    Normalises & cleans PI data returned by either the interpolated,
    recorded, or summary endpoints – including enum‑style tags such as
    CCS_MODE (nested Name/Value pairs).

    If `tag_config["interpolated"]` is False the timestamp index is
    shifted forward by one simulation interval so that each point
    represents the *end* of the averaging window.
    """
    # ------------------------------------------------------------------
    # Quick sanity check
    # ------------------------------------------------------------------
    if not raw_items_list:
        logger.warning(f"No raw PI items provided for processing tag: {tag_key}")
        return pd.DataFrame()

    # ------------------------------------------------------------------
    # 1)  FLATTEN *all* supported PI payload shapes into a single list
    #     of dicts that each contain scalar 'Timestamp' and 'Value'.
    # ------------------------------------------------------------------
    processed_list: list[dict] = []

    for item in raw_items_list:
        # -- 1‑A  TRUE *summary* rows: {'Type': 'Average', 'Value': {...}}
        if 'Type' in item and isinstance(item.get('Value'), dict):
            processed_list.append(item['Value'].copy())
            continue

        # -- 1‑B  ENUM / STATE rows: {'Timestamp': ..., 'Value': {'Name': 'GEN', 'Value': 0}}
        if isinstance(item.get('Value'), dict):
            flat = item.copy()
            enum = flat.pop('Value', {})
            flat['EnumName'] = enum.get('Name')          # keep the label (optional)
            flat['Value']    = enum.get('Value')         # numeric bit or code
            processed_list.append(flat)
            continue

        # -- 1‑C  Simple numeric rows already flat
        processed_list.append(item)

    if not processed_list:
        logger.warning(f"No valid data items to process for {tag_key} after flattening.")
        return pd.DataFrame()

    # ------------------------------------------------------------------
    # 2)  Build DataFrame, basic validations
    # ------------------------------------------------------------------
    try:
        df = pd.DataFrame(processed_list)

        if {'Timestamp', 'Value'}.difference(df.columns):
            logger.warning(f"Processed PI data missing 'Timestamp' or 'Value' for {tag_key}.")
            return pd.DataFrame()

        # ------------------------------------------------------------------
        # 3)  Cleaning & conversions
        # ------------------------------------------------------------------
        df['Timestamp'] = pd.to_datetime(df['Timestamp'], errors='coerce')
        df = df.dropna(subset=['Timestamp'])
        if df.empty:
            return df

        bad_strings = getattr(constants, 'PI_BAD_DATA_STRINGS', [])
        if bad_strings:
            df['Value'] = df['Value'].replace(bad_strings, np.nan)

        df['Value'] = pd.to_numeric(df['Value'], errors='coerce')

        if 'Good' in df.columns:
            df['Good'] = df['Good'].apply(
                lambda x: str(x).lower() == 'true' if pd.notna(x) else False
            )
            df = df[df['Good']]

        df = df.dropna(subset=['Value'])
        if df.empty:
            return df

        # ------------------------------------------------------------------
        # 4)  Indexing & optional time‑shift for summary data
        # ------------------------------------------------------------------
        df = df.set_index('Timestamp')
        if df.index.tz is None:
            df = df.tz_localize(constants.UTC_TZ)
        else:
            df = df.tz_convert(constants.UTC_TZ)
        df.sort_index(inplace=True)

        if not tag_config.get('interpolated', True):
            # summary endpoint: shift index forward one simulation interval
            shift = pd.Timedelta(minutes=constants.SIMULATION_INTERVAL_MINUTES)
            df.index = df.index + shift
            logger.debug(f"Shifted index by {shift} for summary tag {tag_key}.")

        # ------------------------------------------------------------------
        # 5)  Final formatting
        # ------------------------------------------------------------------
        final_col = tag_key
        df.rename(columns={'Value': final_col}, inplace=True)
        return df[[final_col]]

    except Exception as exc:
        logger.exception(f"Error processing PI data for {tag_key}: {exc}")
        return pd.DataFrame()


def get_historical_and_current_data(historical_sim_date_pt=None, return_both: bool = False):
    """
    Fetches PI data using PiRequest, handling potential errors and combining results.
    Determines initial state based on mode (Forecast or Historical).
    """
    sim_horizon_delta = timedelta(days=constants.FORECAST_HORIZON_DAYS)
    lookback_delta = timedelta(days=constants.HISTORICAL_LOOKBACK_DAYS)
    fetch_buffer = timedelta(hours=1)

    if historical_sim_date_pt is None:
        run_mode = "Forecast"
        now_utc = datetime.now(UTC_TZ)
        current_state_target_utc = now_utc.replace(minute=0, second=0, microsecond=0)
        logger.info(f"Target time for current state (Forecast Mode): {current_state_target_utc}")
        fetch_end_utc = now_utc + fetch_buffer
        fetch_start_utc = current_state_target_utc - lookback_delta
        logger.info(f"Running in {run_mode} mode.")
        logger.info(f"Fetching PI data from {fetch_start_utc} to {fetch_end_utc}")
    else:
        run_mode = "Historical Simulation"
        try:
            sim_start_base = pd.Timestamp(historical_sim_date_pt)
            sim_start_pt_ts = sim_start_base.tz_convert(constants.PACIFIC_TZ) if sim_start_base.tz else constants.PACIFIC_TZ.localize(sim_start_base)
            sim_start_utc = sim_start_pt_ts.tz_convert(UTC_TZ)
            sim_start_utc = sim_start_utc.replace(minute=0, second=0, microsecond=0)
            fetch_start_utc = sim_start_utc - lookback_delta
            fetch_end_utc = sim_start_utc + sim_horizon_delta + fetch_buffer
            current_state_target_utc = sim_start_utc
            logger.info(f"Running in {run_mode} mode for date/time: {sim_start_pt_ts.strftime('%Y-%m-%d %H:%M:%S %Z%z')} (Target UTC: {current_state_target_utc})")
            logger.info(f"Fetching PI data from {fetch_start_utc} to {fetch_end_utc}")
        except Exception as e:
            logger.exception(f"Error processing historical simulation date {historical_sim_date_pt}: {e}")
            raise ValueError("Failed to process historical simulation start date.") from e

    # --- Fetch and Process PI Data ---
    if not hasattr(constants, 'PI_TAG_MAP') or not isinstance(constants.PI_TAG_MAP, dict):
         logger.error("constants.PI_TAG_MAP is not defined or is not a dictionary.")
         return None, None

    pi_requests = {}
    for tag_key, tag_config in constants.PI_TAG_MAP.items():
        try:
             use_interpolated_endpoint = tag_config.get('interpolated', True)
             pi_req = PiRequest(
                 db=tag_config.get('db'),
                 element_type=tag_config.get('type'),
                 meter_name=tag_config.get('meter'),
                 attribute=tag_config.get('attr'),
                 interpolated=use_interpolated_endpoint,
                 interval_mins=constants.SIMULATION_INTERVAL_MINUTES
             )
             if pi_req.web_id: pi_requests[tag_key] = pi_req
             else: logger.warning(f"Skipping tag {tag_key} due to missing WebId.")
        except KeyError as ke: logger.error(f"Missing required key in PI_TAG_MAP for {tag_key}: {ke}")
        except Exception as e: logger.exception(f"Error creating PiRequest object for {tag_key}: {e}")

    if not pi_requests:
         logger.error("No valid PI tags configured or accessible.")
         return None, None

    retry_delay = 5; max_retries = 2; processed_dfs = {}
    for tag_key, pi_req in pi_requests.items():
        attempt = 0; success = False; tag_config = constants.PI_TAG_MAP[tag_key] # Get config again for process_pi_data
        while attempt <= max_retries and not success:
            try:
                raw_data_items = pi_req.get_data(fetch_start_utc, fetch_end_utc)
                if raw_data_items:
                    processed_df = process_pi_data(raw_data_items, tag_key, tag_config) # Pass tag_config
                    if not processed_df.empty:
                        processed_dfs[tag_key] = processed_df; success = True
                    else:
                        logger.warning(f"Processing returned empty DataFrame for {tag_key} on attempt {attempt+1}.")
                        if attempt < max_retries: time.sleep(retry_delay)
                        else: logger.error(f"Max retries reached for {tag_key} processing."); success = True
                else:
                    logger.warning(f"PI get_data returned no items for {tag_key} on attempt {attempt+1}.")
                    if attempt < max_retries: time.sleep(retry_delay)
                    else: logger.error(f"Max retries reached for {tag_key} fetching."); success = True
            except Exception as e:
                logger.exception(f"Unhandled error during fetch/process for {tag_key} attempt {attempt+1}: {e}")
                if attempt < max_retries: time.sleep(retry_delay)
                else: logger.error(f"Max retries reached for {tag_key} due to unhandled error."); success = True
            attempt += 1
        if not success: logger.error(f"Failed to get data for {tag_key} after {max_retries+1} attempts.")

    # --- Combine processed historical data ---
    if not processed_dfs:
        logger.error("Failed to fetch/process ANY PI tags successfully.")
        return None, None

    try:
        combined_hist_df = pd.concat(processed_dfs.values(), axis=1, join='outer')
        combined_hist_df.sort_index(inplace=True)

        if combined_hist_df.empty:
             logger.error("Combined historical DataFrame is empty after processing all tags.")
             return None, None

        # --- Determine Current/Initial State ---
        if not combined_hist_df.index.is_monotonic_increasing: combined_hist_df.sort_index(inplace=True)

        # Find the latest timestamp AT or BEFORE the target state time
        valid_times_before_target = combined_hist_df.index[combined_hist_df.index <= current_state_target_utc]
        if valid_times_before_target.empty:
            first_ts = combined_hist_df.index[0]
            if first_ts > current_state_target_utc:
                 logger.warning(f"No PI data found at or before target state time {current_state_target_utc}. Using first point at {first_ts} as state time.")
                 state_time_index = first_ts
            else:
                 logger.error(f"Cannot determine state time relative to {current_state_target_utc}. No suitable data found.")
                 return None, None
        else: state_time_index = valid_times_before_target[-1]

        logger.info(f"Selected state time index: {state_time_index} (Target was: {current_state_target_utc})")

        # Use .loc to get the series at that time, then ffill NaNs
        current_state_series = combined_hist_df.loc[state_time_index].ffill()
        current_state = current_state_series.to_dict()
        current_state['Timestamp_UTC'] = state_time_index.isoformat()

        # --- Interpolate missing values *after* state extraction ---
        numeric_cols = combined_hist_df.select_dtypes(include=np.number).columns
        combined_hist_df[numeric_cols] = combined_hist_df[numeric_cols].interpolate(method='time', limit=3).ffill().bfill()

        # --- Final Checks ---
        cols_all_nan = combined_hist_df.columns[combined_hist_df.isna().all()].tolist()
        if cols_all_nan: logger.warning(f"PI tags with no valid data after processing: {cols_all_nan}.")
        essential_tags = ['Afterbay_Elevation', 'Oxbow_Power', 'Afterbay_Elevation_Setpoint', 'R4_Flow', 'R30_Flow', 'R20_Flow', 'R5L_Flow', 'R26_Flow', 'MFP_Total_Gen_GEN_MDFK_and_RA', 'CCS_Mode']
        missing_essential = [tag for tag in essential_tags if tag in cols_all_nan or tag not in combined_hist_df.columns]
        if missing_essential: logger.error(f"Essential PI tags missing all data: {missing_essential}. Critical failure."); return None, None

        nan_in_state = {k: v for k, v in current_state.items() if pd.isna(v) and k != 'Timestamp_UTC'}
        if nan_in_state:
             logger.error(f"NaN values found in determined initial state for keys: {list(nan_in_state.keys())} at time {state_time_index}.")
             essential_state_keys = ['Afterbay_Elevation', 'Oxbow_Power', 'Afterbay_Elevation_Setpoint', 'CCS_Mode']
             if any(k in nan_in_state for k in essential_state_keys): logger.error("NaN in essential state values. Aborting."); return None, None

        state_log_str = {k: f'{v:.2f}' if isinstance(v, float) else v for k, v in current_state.items() if k != 'Timestamp_UTC'}
        logger.info(f"Current/Initial state snapshot determined for time {state_time_index}: {state_log_str}")

        # --- Return based on mode ---
        if run_mode == "Forecast":
            lookback_df = combined_hist_df[combined_hist_df.index <= state_time_index].copy()
            return current_state, lookback_df
        else: # Historical Simulation Mode
            lookback_df = combined_hist_df[combined_hist_df.index <= state_time_index].copy()
            forward_df = combined_hist_df[combined_hist_df.index >= state_time_index].copy()
            if forward_df.empty:
                logger.error(f"No data at or after sim start time: {state_time_index}")
                return None, None
            if return_both:
                return current_state, lookback_df, forward_df
            # backward‑compatibility: original 2‑tuple sha
            return current_state, forward_df


    except Exception as e:
        logger.exception(f"Failed during final combination or state extraction: {e}")
        return None, None