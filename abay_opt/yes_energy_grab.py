import requests
import pandas as pd
import numpy as np
import json
import logging
import configparser
import os
import time
import pytz
from datetime import datetime, timedelta
from requests.auth import HTTPBasicAuth

# Assuming 'constants' module exists and defines SIMULATION_INTERVAL_MINUTES
# For demonstration, let's define a placeholder for constants if not available.
try:
    import constants
except ImportError:
    class Constants:
        SIMULATION_INTERVAL_MINUTES = 60  # Default to 60 minutes for resampling


    constants = Constants()

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# YES Energy API constants
YES_ENERGY_BASE_URL = "https://services.yesenergy.com/PS/rest/timeseries/multiple.json"
YES_ENERGY_DATE_COLLECTION = "103028"  # Yesterday, Today, Tomorrow

# Price type mappings
PRICE_TYPES = {
    'DALMP': 'Day_Ahead_Price',
    'LMP_15MIN': 'Fifteen_Min_Price',
    'RTLMP': 'Real_Time_Price'
}


class YesEnergyPriceFetcher:
    """
    Fetches electricity price data from YES Energy API
    """

    def __init__(self, config_file_path='config'):
        self.config_file_path = config_file_path
        self.username = None
        self.password = None
        self.session = requests.Session()
        self._load_credentials()

        if self.username and self.password:
            self.session.auth = HTTPBasicAuth(self.username, self.password)
            logger.info("YES Energy API credentials loaded successfully")
        else:
            logger.error("YES Energy API credentials not found or invalid. Please check your config file.")

    def _load_credentials(self):
        try:
            if not os.path.exists(self.config_file_path):
                logger.error(f"Config file not found: {self.config_file_path}")
                return
            config = configparser.ConfigParser()
            config.read(self.config_file_path)
            if 'YES_ENERGY' in config:
                self.username = config.get('YES_ENERGY', 'username', fallback=None)
                self.password = config.get('YES_ENERGY', 'password', fallback=None)
                if self.username and self.password:
                    logger.info("YES Energy credentials found in config")
                else:
                    logger.error("YES Energy username or password missing in config file under [YES_ENERGY] section.")
            else:
                logger.error("YES_ENERGY section not found in config file.")
        except Exception as e:
            logger.error(f"Error loading YES Energy credentials: {e}")

    def fetch_price_data(self, node_id="20000002064", retry_attempts=3, retry_delay=5):
        if not (self.username and self.password):
            logger.error("Cannot fetch price data: credentials not available or invalid.")
            return pd.DataFrame()

        items = ','.join(f"{pt}:{node_id}" for pt in PRICE_TYPES)
        params = {
            'agglevel': '5min',  # API returns 5-minute data
            'datecollections': YES_ENERGY_DATE_COLLECTION,
            'items': items
        }
        logger.info(f"Attempting to fetch YES Energy price data for node {node_id} and items: {items}")

        for attempt in range(1, retry_attempts + 1):
            try:
                resp = self.session.get(
                    YES_ENERGY_BASE_URL,
                    params=params,
                    timeout=60
                )
                logger.info(f"API response status: {resp.status_code} (Attempt {attempt}/{retry_attempts})")

                if resp.status_code == 200:
                    df = self._parse_price_response(resp.text)
                    if isinstance(df, pd.DataFrame) and not df.empty:
                        logger.info(f"Successfully fetched and parsed {len(df)} price records.")
                        return df
                    else:
                        logger.warning("No data parsed from API response or empty DataFrame returned by parser.")
                        # If parsing yields no data, it's not a network error, don't retry same way
                        return pd.DataFrame()
                elif resp.status_code in (401, 404):
                    logger.error(f"API error {resp.status_code}: {resp.text}. This is a critical error, not retrying.")
                    return pd.DataFrame()
                else:
                    logger.error(f"Unexpected API status code {resp.status_code}: {resp.text}")
                    if attempt < retry_attempts:
                        logger.info(f"Retrying in {retry_delay}s (attempt {attempt}/{retry_attempts})...")
                        time.sleep(retry_delay)
                    else:
                        logger.error(
                            f"Failed to fetch data after {retry_attempts} attempts due to unexpected status code.")
                        return pd.DataFrame()

            except requests.exceptions.Timeout:
                logger.error(f"Request timed out (Attempt {attempt}/{retry_attempts}).")
                if attempt < retry_attempts:
                    logger.info(f"Retrying in {retry_delay}s...")
                    time.sleep(retry_delay)
                else:
                    logger.error(f"Failed to fetch data after {retry_attempts} attempts due to timeout.")
                    return pd.DataFrame()
            except requests.exceptions.RequestException as e:
                logger.error(f"Network or request error (Attempt {attempt}/{retry_attempts}): {e}")
                if attempt < retry_attempts:
                    logger.info(f"Retrying in {retry_delay}s...")
                    time.sleep(retry_delay)
                else:
                    logger.error(f"Failed to fetch data after {retry_attempts} attempts due to network error.")
                    return pd.DataFrame()
            except Exception as e:
                logger.error(f"An unexpected error occurred during fetch attempt {attempt}: {e}")
                import traceback
                logger.error(f"Full traceback: {traceback.format_exc()}")
                if attempt < retry_attempts:
                    logger.info(f"Retrying in {retry_delay}s...")
                    time.sleep(retry_delay)
                else:
                    logger.error(f"Failed to fetch data after {retry_attempts} attempts due to an unexpected error.")
                    return pd.DataFrame()

        logger.error(f"Failed to fetch data after {retry_attempts} attempts.")
        return pd.DataFrame()

    def _parse_price_response(self, response_text):
        logger.debug(f"Raw response snippet: {response_text[:500]}...")  # Log a longer snippet
        try:
            data = json.loads(response_text)
            logger.debug(f"Loaded JSON type: {type(data)}")
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}. Response was not valid JSON.")
            return pd.DataFrame()

        records = []
        if isinstance(data, dict):
            # This handles a potential structure where 'data' is nested under keys
            for section_key, section_value in data.items():
                if isinstance(section_value, dict) and isinstance(section_value.get('data'), list):
                    records.extend([rec for rec in section_value['data'] if isinstance(rec, dict)])
                elif isinstance(section_value, list):
                    records.extend([rec for rec in section_value if isinstance(rec, dict)])
                else:
                    logger.debug(f"Skipping section '{section_key}' with unexpected type: {type(section_value)}")
        elif isinstance(data, list):
            # This handles the direct list of records structure, as shown in the sample
            records.extend([rec for rec in data if isinstance(rec, dict)])
        else:
            logger.error(f"Unexpected top-level JSON structure: {type(data)}. Expected dict or list.")
            return pd.DataFrame()

        if not records:  # Use not records for empty list check
            logger.warning("No valid price records found in JSON response.")
            return pd.DataFrame()

        try:
            df = pd.DataFrame(records)
            logger.debug(f"DataFrame created with {len(df)} records. Columns: {df.columns.tolist()}")

            # Identify datetime column
            dt_keywords = ('timestamp', 'time', 'date', 'datetime')
            # Prefer 'DATETIME' exactly if present, otherwise look for keywords
            dt_col = None
            if 'DATETIME' in df.columns:
                dt_col = 'DATETIME'
            else:
                dt_candidates = [c for c in df.columns if any(k in c.lower() for k in dt_keywords)]
                if dt_candidates:
                    dt_col = dt_candidates[0]

            if dt_col is None:
                logger.error(
                    f"No suitable datetime column found based on keywords {dt_keywords}; available columns: {df.columns.tolist()}")
                return pd.DataFrame()
            logger.debug(f"Using datetime column: '{dt_col}'")

            # Parse datetime - handle your specific format
            # The sample shows '%m/%d/%Y %H:%M:%S'
            df[dt_col] = pd.to_datetime(df[dt_col], format='%m/%d/%Y %H:%M:%S', errors='coerce')

            # Remove rows where datetime parsing failed
            before_count = len(df)
            df.dropna(subset=[dt_col], inplace=True)
            after_count = len(df)
            if before_count != after_count:
                logger.warning(f"Dropped {before_count - after_count} rows with invalid datetime after parsing.")

            if df.empty:  # Use df.empty for empty DataFrame check
                logger.error("No valid datetime records remaining after cleanup.")
                return pd.DataFrame()

            df.set_index(dt_col, inplace=True)

            # Handle timezone - assume source is US/Eastern and convert to UTC
            try:
                if df.index.tz is None:
                    eastern = pytz.timezone('US/Eastern')
                    # Use Series.dt accessor for timezone operations on datetime index
                    df.index = df.index.tz_localize(eastern)
                # Convert to UTC only if localization was successful or already present
                if df.index.tz is not None:
                    df.index = df.index.tz_convert(pytz.UTC)
                else:
                    logger.warning("Could not localize timezone. Index remains naive.") # Updated warning message
            except Exception as e:
                logger.error(
                    f"Error handling timezone: {e}. Proceeding with potentially naive/incorrectly localized index.")
                # Don't return empty DataFrame just for timezone error, let downstream handle if needed

            # Column mapping to standardized names
            col_map = {}
            for original_suffix, standardized_name in PRICE_TYPES.items():
                # Find columns that contain the original suffix, case-insensitive check for robustness
                matching_cols = [col for col in df.columns if original_suffix.lower() in col.lower()]
                if matching_cols:
                    # Assuming only one match per suffix is expected for a given node_id
                    col_map[matching_cols[0]] = standardized_name
                else:
                    logger.debug(f"No column found for original price type suffix '{original_suffix}'.")

            if not col_map:
                logger.error("No recognized price columns found for renaming after parsing.")
                logger.debug(f"Original DataFrame columns: {df.columns.tolist()}")
                return pd.DataFrame()

            logger.debug(f"Applying column mapping: {col_map}")
            df.rename(columns=col_map, inplace=True)

            # Convert price columns to numeric, coercing errors (like 'null' strings or empty) to NaN
            for std_col in PRICE_TYPES.values():
                if std_col in df.columns:
                    # Check if column exists before conversion
                    df[std_col] = pd.to_numeric(df[std_col], errors='coerce')
                else:
                    logger.debug(f"Standardized price column '{std_col}' not found after renaming.")

            # Keep only the price columns we need
            final_cols = [std for std in PRICE_TYPES.values() if std in df.columns]
            if not final_cols:  # Use not final_cols for empty list check
                logger.error("No recognized price columns available after all processing steps.")
                logger.error(f"DataFrame columns after rename: {df.columns.tolist()}")
                return pd.DataFrame()

            df = df[final_cols]
            logger.info(f"Final parsed DataFrame columns: {df.columns.tolist()}")

            # Sort and remove duplicates (should be handled by index setting, but good safeguard)
            df.sort_index(inplace=True)
            df = df.loc[~df.index.duplicated(keep='first')]
            logger.info(f"Parsed and cleaned {len(df)} records. First: {df.index.min()}, Last: {df.index.max()}")

            return df

        except Exception as e:
            logger.error(f"Error processing DataFrame in _parse_price_response: {e}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            return pd.DataFrame()

    def get_price_data_for_optimization(self, node_id="20000002064"):
        raw = self.fetch_price_data(node_id)

        # Safe check for empty DataFrame
        if not isinstance(raw, pd.DataFrame) or raw.empty:
            logger.warning("No raw price data fetched for optimization. Returning empty DataFrame.")
            return pd.DataFrame()

        try:
            interval = f"{constants.SIMULATION_INTERVAL_MINUTES}min"
            # Resample all columns to the specified interval, taking the mean of values within each interval
            resampled = raw.resample(interval, label='left', closed='left').mean()

            # Strategy for filling NaNs:
            # 1. Forward fill short gaps (e.g., 1-2 missing intervals)
            resampled = resampled.ffill(limit=2)
            logger.debug(f"After initial ffill(limit=2), NaNs remaining: {resampled.isnull().sum().to_dict()}")

            # 2. Fill Real-Time and 15-Min prices with Day-Ahead Price for longer gaps (e.g., future data)
            # This assumes Day_Ahead_Price is a reasonable proxy when RT/15min are not available yet.
            if 'Real_Time_Price' in resampled.columns and 'Day_Ahead_Price' in resampled.columns:
                initial_rt_nan_count = resampled['Real_Time_Price'].isnull().sum()
                resampled['Real_Time_Price'] = resampled['Real_Time_Price'].fillna(resampled['Day_Ahead_Price'])
                filled_rt_count = initial_rt_nan_count - resampled['Real_Time_Price'].isnull().sum()
                if filled_rt_count > 0:
                    logger.info(f"Filled {filled_rt_count} Real_Time_Price NaNs with Day_Ahead_Price.")

            if 'Fifteen_Min_Price' in resampled.columns and 'Day_Ahead_Price' in resampled.columns:
                initial_15m_nan_count = resampled['Fifteen_Min_Price'].isnull().sum()
                resampled['Fifteen_Min_Price'] = resampled['Fifteen_Min_Price'].fillna(resampled['Day_Ahead_Price'])
                filled_15m_count = initial_15m_nan_count - resampled['Fifteen_Min_Price'].isnull().sum()
                if filled_15m_count > 0:
                    logger.info(f"Filled {filled_15m_count} Fifteen_Min_Price NaNs with Day_Ahead_Price.")

            logger.debug(f"After proxy fill, NaNs remaining: {resampled.isnull().sum().to_dict()}")

            # 3. Final comprehensive fill for any remaining NaNs (e.g., if Day_Ahead_Price itself had NaNs)
            # Use a combination of ffill and bfill to cover all cases if data appears/disappears.
            resampled = resampled.ffill().bfill()
            logger.debug(f"After final ffill/bfill, NaNs remaining: {resampled.isnull().sum().to_dict()}")

            # 4. Drop rows where ALL relevant price columns are still NaN (should be rare now)
            final_cols_to_check = [c for c in PRICE_TYPES.values() if c in resampled.columns]
            if not final_cols_to_check:
                logger.warning("No relevant price columns found to perform final NaN check. Returning as is.")
                return resampled  # Or pd.DataFrame() if no price columns means unusable data

            initial_row_count = len(resampled)
            resampled.dropna(subset=final_cols_to_check, how='all', inplace=True)
            dropped_row_count = initial_row_count - len(resampled)
            if dropped_row_count > 0:
                logger.warning(f"Dropped {dropped_row_count} rows where all relevant price columns were NaN.")

            if resampled.empty:
                logger.warning("Resampling and NaN filling resulted in an empty DataFrame.")
                return pd.DataFrame()

            logger.info(f"Resampled data prepared for optimization to {interval} intervals: {len(resampled)} records. "
                        f"From {resampled.index.min()} to {resampled.index.max()}.")
            return resampled
        except Exception as e:
            logger.error(f"Error during resampling and filling for optimization: {e}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            return pd.DataFrame()


def get_current_electricity_prices(node_id="20000002064", config_file='config'):
    """
    Convenience function to fetch and prepare electricity price data.
    """
    try:
        fetcher = YesEnergyPriceFetcher(config_file)
        if not (fetcher.username and fetcher.password):
            logger.error("Fetcher not initialized with valid credentials. Cannot get prices.")
            return pd.DataFrame()
        return fetcher.get_price_data_for_optimization(node_id)
    except Exception as e:
        logger.error(f"Error in get_current_electricity_prices: {e}")
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")
        return pd.DataFrame()


def get_price_statistics(price_data):
    # Safe check for empty DataFrame
    if not isinstance(price_data, pd.DataFrame) or price_data.empty:
        logger.warning("No price data provided for statistics calculation. Returning empty dict.")
        return {}

    stats = {}
    for col in price_data.columns:
        series = price_data[col].dropna()
        if series.empty:  # Use series.empty instead of len() == 0 for Series
            logger.debug(f"Column '{col}' is empty after dropping NaNs, skipping statistics.")
            continue
        stats[col] = {
            'current': float(series.iloc[-1]),
            'min': float(series.min()),
            'max': float(series.max()),
            'mean': float(series.mean()),
            'std': float(series.std()),
            'count': int(series.count())
        }
    logger.info(f"Calculated statistics for {len(stats)} price columns.")
    return stats


if __name__ == "__main__":
    # Create a dummy config file for testing purposes if it doesn't exist
    # In a real scenario, this would be manually created and secured.
    config_path = 'config'
    if not os.path.exists(config_path):
        logger.warning(f"Dummy config file '{config_path}' created for testing. "
                       "Please replace with actual YES Energy credentials for live use.")
        with open(config_path, 'w') as f:
            f.write("[YES_ENERGY]\n")
            f.write("username=YOUR_USERNAME\n")
            f.write("password=YOUR_PASSWORD\n")
    else:
        logger.info(f"Using existing config file at '{config_path}'.")

    logger.info("Testing YES Energy price fetcher...")
    # NOTE: To run this successfully, ensure you have a 'config' file
    # with a [YES_ENERGY] section containing 'username' and 'password'
    # as valid YES Energy API credentials.
    # Also, ensure 'constants.py' exists or define SIMULATION_INTERVAL_MINUTES
    # within this script for testing.

    # Temporarily set logging level to DEBUG to see more parsing details during test
    logging.getLogger(__name__).setLevel(logging.DEBUG)

    df_prices = get_current_electricity_prices(node_id="20000002064", config_file=config_path)

    if isinstance(df_prices, pd.DataFrame) and not df_prices.empty:
        print("\n=== Sample of Processed Price Data ===")
        print(df_prices.head())
        print(df_prices.tail())
        print("\n=== Data Info ===")
        df_prices.info()
        print("\n=== Missing Values Check ===")
        print(df_prices.isnull().sum())
        print("\n=== Price Statistics ===")
        stats = get_price_statistics(df_prices)
        for price_type, s_data in stats.items():
            print(f"--- {price_type} ---")
            for stat_name, value in s_data.items():
                print(f"  {stat_name}: {value:.4f}")
    else:
        print("\nNo price data retrieved or processed.")

    # Reset logging level
    logging.getLogger(__name__).setLevel(logging.INFO)