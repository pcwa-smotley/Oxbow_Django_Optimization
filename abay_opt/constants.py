# constants.py
import pytz
from datetime import time
import os

# Timezones
PACIFIC_TZ = pytz.timezone('America/Los_Angeles')
UTC_TZ = pytz.utc

# --- Get the directory where constants.py resides ---
_constants_dir = os.path.dirname(os.path.abspath(__file__))

# ==========================================
# CONSTRAINT ENABLE/DISABLE FLAGS
# ==========================================
# These flags allow turning constraints on/off without changing penalty weights
ENABLE_SPILLAGE_PENALTY = True             # P1: Penalize water spillage
ENABLE_SUMMER_MW_REWARD = True             # P2: Reward summer peak generation
ENABLE_SMOOTHING_PENALTY = True            # P3: Penalize OXPH MW changes
ENABLE_MIDPOINT_ELEVATION_PENALTY = False  # P4: Guide to midpoint elevation
ENABLE_HEAD_LOSS_CONSTRAINT = True         # Apply head loss based on elevation (applied in recalculation, not LP)
ENABLE_PWL_APPROXIMATION = False            # Use PWL vs simple equation for OXPH

# ==========================================
# HARD CONSTRAINTS (Cannot be violated)
# ==========================================
FORCE_OXPH_ALWAYS_ON = True             # OXPH must run 24/7/365
FORCE_OXPH_MIN_OPERATION = True         # Must be >= OXPH_MIN_MW when on
PROHIBIT_SUMMER_SPILL = True            # No spilling during summer season
SPILL_ONLY_ABOVE_MW = 4.5               # Outside summer, only spill if OXPH > this MW
ENABLE_CONDITIONAL_SPILL = True         # Enable the conditional spill logic

# ==========================================
# OBJECTIVE PRIORITIES (Default values for UI)
# ==========================================
# 1 = highest priority, 5 = lowest
# These can be overridden by UI parameters
PRIORITY_AVOID_SUMMER_SPILL = 1         # Critical - never spill in summer
PRIORITY_AVOID_SPILL = 1                # High - avoid spilling anytime
PRIORITY_SUMMER_RAFTING = 2             # High - meet recreational flows
PRIORITY_SMOOTH_OPERATION = 6           # Very Low - avoid frequent changes
PRIORITY_MIDPOINT_ELEVATION = 6         # Very Low - nice to have

# ==========================================
# PRIORITY TO WEIGHT MAPPING
# ==========================================
# Base weight for each priority level
BASE_WEIGHT_BY_PRIORITY = {
    1: 100000.0,   # Critical
    2: 1000.0,    # High
    3: 100.0,     # Medium
    4: 10.0,      # Low
    5: 1.0,        # Minimal
    6: 0.1         # Very Minimal
}

# ==========================================
# CALCULATED PENALTY WEIGHTS
# ==========================================
# These are calculated from priorities but can be overridden directly
LP_SUMMER_SPILLAGE_PENALTY_WEIGHT = BASE_WEIGHT_BY_PRIORITY[PRIORITY_AVOID_SUMMER_SPILL] * 5  # Extra multiplier
LP_SPILLAGE_PENALTY_WEIGHT = BASE_WEIGHT_BY_PRIORITY[PRIORITY_AVOID_SPILL]
LP_SUMMER_MW_REWARD_WEIGHT = BASE_WEIGHT_BY_PRIORITY[PRIORITY_SUMMER_RAFTING]
LP_BASE_SMOOTHING_PENALTY_WEIGHT = BASE_WEIGHT_BY_PRIORITY[PRIORITY_SMOOTH_OPERATION]
LP_TARGET_ELEV_MIDPOINT_WEIGHT = BASE_WEIGHT_BY_PRIORITY[PRIORITY_MIDPOINT_ELEVATION]

# ==========================================
# UI ADJUSTABLE PARAMETERS
# ==========================================
# These define the ranges/options available in the UI
UI_PRIORITY_RANGE = (1, 5)              # Min and max priority values
UI_SMOOTHING_WEIGHT_RANGE = (0, 1000)  # Range for smoothing weight if directly adjustable
UI_ALLOW_DISABLE_SMOOTHING = True       # Whether UI can turn smoothing OFF completely

# ==========================================
# SUMMER SCHEDULE CONSTRAINTS
# ==========================================
ENABLE_SUMMER_HOLD_CONSTRAINT = True    # Force OXPH ON during summer hold
ENABLE_SUMMER_RAMP_FLOOR = True         # Minimum MW during summer ramp-up


# Simulation Parameters
FORECAST_HORIZON_DAYS = 7
HISTORICAL_LOOKBACK_DAYS = 3
SIMULATION_INTERVAL_MINUTES = 60 # Hourly simulation steps
BIAS_CALC_LOOKBACK_DAYS = 1 # Use 1 day (24 hours) for bias calculation

# ABAY Reservoir Constants
ABAY_MIN_ELEV_FT = 1168.0
ABAY_MAX_ELEV_BUFFER_FT = 1.0 # Buffer to prevent overfilling and hitting minimum elevation

# OXPH Generator Constants
OXPH_MIN_MW = 0.8
OXPH_MAX_MW = 5.8
OXPH_RAMP_RATE_MW_PER_MIN = 0.042
# Derived: Max MW change per simulation interval
OXPH_MAX_RAMP_PER_INTERVAL = OXPH_RAMP_RATE_MW_PER_MIN * SIMULATION_INTERVAL_MINUTES
OXPH_MW_TO_CFS_FACTOR = 163.73 # Used if OXPH_CFS_METHOD is 'equation'
OXPH_MW_TO_CFS_OFFSET = 83.0   # Used if OXPH_CFS_METHOD is 'equation'

# MFRA Generator Constants
MFRA_MAX_MW_GEN_MODE = 210.0
MFRA_MAX_MW_SPILL_MODE = 210.0
MFRA_MW2_TO_CFS_FACTOR = 0.00943
MFRA_MW_TO_CFS_FACTOR = 5.6653
MFRA_MW_TO_CFS_OFFSET = 18.54

# OLD VERSION
# MFRA_MW2_TO_CFS_FACTOR = 0.0049
# MFRA_MW_TO_CFS_FACTOR = 6.262
# MFRA_MW_TO_CFS_OFFSET = 18.0

# OXPH Head Loss Analysis Constants
OXPH_HEAD_LOSS_SLOPE = 0.0912
OXPH_HEAD_LOSS_INTERCEPT = -101.42

# Use this to determine if the OXPH_Schedule_MW is being impacted by head loss.
# A value of 0.1 means that if the OXPH_Schedule_MW is within 0.1 MW of the head loss calculation, OXPH may be
# impacted by head loss. This is ONLY used to determine if a setpoint change occurred AFTER the optimization is
# complete. It does NOT impact the optimization itself. This should be very small since the optimization already
# took this into consideration.
HEAD_LOSS_TOLERANCE_MW = -0.1

# Summer Schedule (Pacific Time)
SUMMER_START_MONTH = 6
SUMMER_START_DAY = 1
# Labor Day is calculated dynamically in calculations.py
SUMMER_TARGET_START_TIME = time(8, 0)  # 8 AM PT
SUMMER_TARGET_END_TIME = time(12, 0) # 12 PM PT
SUMMER_OXPH_TARGET_MW = 5.8 # Target MW during the summer window

# --- API and PI Tag Configuration ---

# Upstream API Details
UPSTREAM_API_URL = "https://api.upstream.tech/api/v2/timeseries/forecasts"
UPSTREAM_SITE_IDS = {
    "R30": "pcwa-r30-rubicon-river-abv-ralston-power-house",
    "R4": "pcwa-r4-middle-fork-american-abv-power-house-total"
}

# Define available forecast sources and their columns for Upstream API
UPSTREAM_FORECAST_SOURCE_HYDROFORECAST = "hydroforecast-short-term"
UPSTREAM_FORECAST_SOURCE_CNRFC = "cnrfc"

# Default forecast source (can be overridden by command-line argument)
DEFAULT_UPSTREAM_FORECAST_SOURCE = UPSTREAM_FORECAST_SOURCE_HYDROFORECAST

# Columns for each Upstream API forecast source
# For hydroforecast, we primarily care about 'discharge_mean' for the optimizer,
# but you might want to fetch others for analysis.
UPSTREAM_HYDROFORECAST_REQUEST_COLUMNS = [
    "discharge_mean", # Primarily used
    "discharge_q0.05", "discharge_q0.1", "discharge_q0.25",
    "discharge_q0.5", "discharge_q0.75", "discharge_q0.9", "discharge_q0.95"
]
# The column that will be extracted and renamed to (e.g.) R4_Forecast_CFS
UPSTREAM_HYDROFORECAST_TARGET_COLUMN = "discharge_mean"

UPSTREAM_CNRFC_REQUEST_COLUMNS = ["ensemble_forecast_avg"]

# The column that will be extracted and renamed to (e.g.) R4_Forecast_CFS
UPSTREAM_CNRFC_TARGET_COLUMN = "ensemble_forecast_avg"

# Number of hours to look back for forecasts using issueTimeAfterDate
UPSTREAM_ISSUE_TIME_LOOKBACK_HOURS = 48 # Default to 48 hours

# PI Web API Base URL
# To get a direct path to see what's available:
# https://flows.pcwa.net/piwebapi/assetservers/F1RSvXCmerKddk-VtN6YtBmF5AQlVTSU5FU1NQSTI/assetdatabases
PI_BASE_URL = "https://flows.pcwa.net/piwebapi"

# Mapping of descriptive names to PI tag details needed for get_historical_and_current_data
# Structure: 'Descriptive_Name': {'db': 'Database', 'type': 'ElementType' or None if in 'Energy Marketing' db,
#                                  'meter': 'MeterName', 'attr': 'Attribute', }
# Structure: 'db' = 'OPS' or 'Energy Marketing'
#            'type' = 'Gauging Stations', 'Reservoirs', 'Generation Units', 'Additions for PI Vision',
#                      ***if db is 'Energy Marketing' then type is likely 'Misc Tags'***
#            'meter' => If it's a flow meter: R10, R11, R20, R26, R30, R4, R5L
#                    => If it's a reservoir: Afterbay, French Meadows, Hell Hole
#                    => If it's a generation unit: Oxbow, Ralston, French Meadows, Hell Hole, Middle Fork,
#                       Middle Fork 1, Middle Fork 2,
#            'attr' => This is the final output you're looking for (e.g. Flow, Elevation Setpoint, etc.) You will
#                      likely need to look this up, as it changes with every tag.
#            You can look up 'attr' values here:
#            https://flows.pcwa.net/piwebapi/assetservers/F1RSvXCmerKddk-VtN6YtBmF5AQlVTSU5FU1NQSTI/assetdatabases
#

# Interpolated = False means the data will be averaged over the time period.
# Interpolated = True means the data will use the last value of in the time period (Set to TRUE from all binary data
# and for Afterbay Elevation to get the most recent value)
PI_TAG_MAP = {
    'Afterbay_Elevation': {'db': 'OPS', 'type': 'Reservoirs', 'meter': 'Afterbay', 'attr': 'Elevation','interpolated': True},
    'Afterbay_Elevation_Setpoint': {'db': 'OPS', 'type': 'Reservoirs', 'meter': 'Afterbay', 'attr': 'Elevation Setpoint'}, # FLOAT
    'Oxbow_Power': {'db': 'OPS', 'type': 'Generation Units', 'meter': 'Oxbow', 'attr': 'Power', 'interpolated': False},
    'MFP_Total_Gen_GEN_MDFK_and_RA': {'db': 'Energy_Marketing', 'type': 'Misc Tags', 'meter': None, 'attr': "GEN_MDFK_and_RA", 'interpolated': False}, # MFRA Total
    'CCS_Mode': {'db': 'OPS', 'type': 'Additions for PI Vision', 'meter': None, 'attr': 'CCS Mode', 'interpolated': True},
    'R4_Flow': {'db': 'OPS', 'type': 'Gauging Stations', 'meter': 'R4', 'attr': 'Flow', 'interpolated': False},
    'R30_Flow': {'db': 'OPS', 'type': 'Gauging Stations', 'meter': 'R30', 'attr': 'Flow_EM', 'interpolated': False}, # New QC Pi Tag Made 8/5/2025
    'R20_Flow': {'db': 'OPS', 'type': 'Gauging Stations', 'meter': 'R20', 'attr': 'Flow', 'interpolated': False},
    'R5L_Flow': {'db': 'OPS', 'type': 'Gauging Stations', 'meter': 'R5L', 'attr': 'Flow', 'interpolated': False},
    'R26_Flow': {'db': 'OPS', 'type': 'Gauging Stations', 'meter': 'R26', 'attr': 'Flow', 'interpolated': False},
    'OXPH_ADS': {'db': 'OPS', 'type': 'Generation Units', 'meter': 'Oxbow', 'attr': 'Gov Setpoint', 'interpolated': True}
}


# --- OXPH MW to CFS Conversion Method ---
# Method to use for OXPH MW -> CFS conversion. Options:
# 'equation': Uses the linear formula OXPH_MW_TO_CFS_FACTOR * mw + OXPH_MW_TO_CFS_OFFSET
# 'lookup': Uses a CSV lookup table specified by OXPH_LOOKUP_TABLE_PATH
OXPH_CFS_METHOD = 'lookup'  # Change to 'lookup' to use the table

# Location of the OXPH MW → CFS lookup table
OXPH_LOOKUP_TABLE_PATH = os.path.join(_constants_dir, "data", "OXPH_to_CFS_Rand_forest.csv")

# Update based on B120: https://cdec.water.ca.gov/reportapp/javareports?name=B120DIST
# CURRENT_WATER_YEAR_TYPE = 'Wet'
# CURRENT_WATER_YEAR_TYPE = 'Above Normal'
CURRENT_WATER_YEAR_TYPE = 'Below Normal'
# CURRENT_WATER_YEAR_TYPE = 'Dry'
# CURRENT_WATER_YEAR_TYPE = 'Critical'
# CURRENT_WATER_YEAR_TYPE = 'Extreme Critical'

# RAFTING SEASON DATES (replaces fixed June 1 start)
RAFTING_SEASON_END_DATE = (9, 30)  # September 30th (month, day)


EARLY_RELEASE_SATURDAYS = [
    (5, 24, 2025),  # Memorial Day Weekend
    (5, 31, 2025),
    (6, 7, 2025),
    (6, 21, 2025),
    (6, 28, 2025),  # Western States Weekend
    (7, 5, 2025),
    (7, 12, 2025),  # Tevis Cup Weekend
    (7, 19, 2025),
    (8, 2, 2025),
    (8, 16, 2025),
    (9, 20, 2025),
]

# RAFTING SCHEDULES BY WATER YEAR TYPE
RAFTING_SCHEDULES = {
    'Wet': {
        'main_season': {
            'weekdays': {
                'days': ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday'],
                'start_time': time(9, 0),   # 9:00 AM
                'end_time': time(12, 0),    # 12:00 PM
            },
            'weekends': {
                'days': ['Saturday', 'Sunday'],
                'start_time': time(8, 0),   # 8:00 AM
                'end_time': time(12, 0),    # 12:00 PM
            }
        },
        'post_labor_day': {
            'weekdays': {
                'days': ['Tuesday', 'Wednesday', 'Thursday', 'Friday'],
                'start_time': time(9, 0),
                'end_time': time(12, 0),
            },
            'weekends': {
                'days': ['Saturday', 'Sunday'],
                'start_time': time(8, 0),
                'end_time': time(12, 0),
            }
        }
    },
    'Above Normal': {
        'main_season': {
            'weekdays': {
                'days': ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday'],
                'start_time': time(9, 0),
                'end_time': time(12, 0),
            },
            'weekends': {
                'days': ['Saturday', 'Sunday'],
                'start_time': time(8, 0),
                'end_time': time(12, 0),
            }
        },
        'post_labor_day': {
            'weekdays': {
                'days': ['Tuesday', 'Wednesday', 'Friday'],
                'start_time': time(9, 0),
                'end_time': time(12, 0),
            },
            'weekends': {
                'days': ['Saturday', 'Sunday'],
                'start_time': time(8, 0),
                'end_time': time(12, 0),
            }
        }
    },
    'Below Normal': {
        'main_season': {
            'weekdays': {
                'days': ['Tuesday', 'Wednesday', 'Thursday', 'Friday'],
                'start_time': time(9, 0),
                'end_time': time(12, 0),
            },
            'weekends': {
                'days': ['Saturday', 'Sunday'],
                'start_time': time(8, 0),
                'end_time': time(12, 0),
            }
        },
        'post_labor_day': {
            'weekdays': {
                'days': ['Tuesday', 'Wednesday', 'Friday'],
                'start_time': time(9, 0),
                'end_time': time(12, 0),
            },
            'weekends': {
                'days': ['Saturday', 'Sunday'],
                'start_time': time(8, 0),
                'end_time': time(12, 0),
            }
        }
    },
    'Dry': {
        'main_season': {
            'weekdays': {
                'days': ['Tuesday', 'Wednesday', 'Thursday'],
                'start_time': time(8, 0),   # Earlier start time for dry years
                'end_time': time(11, 0),    # Shorter duration
            },
            'weekends': {
                'days': ['Saturday', 'Sunday'],
                'start_time': time(8, 0),
                'end_time': time(12, 0),
            }
        },
        'post_labor_day': {
            'weekdays': {
                'days': ['Wednesday', 'Friday'],
                'start_time': time(8, 0),
                'end_time': time(11, 0),
            },
            'weekends': {
                'days': ['Saturday', 'Sunday'],
                'start_time': time(8, 0),
                'end_time': time(12, 0),
            }
        }
    },
    'Critical': {
        'main_season': {
            'weekdays': {
                'days': ['Wednesday', 'Friday'],
                'start_time': time(8, 0),
                'end_time': time(11, 0),
            },
            'weekends': {
                'days': ['Saturday', 'Sunday'],
                'start_time': time(8, 0),
                'end_time': time(12, 0),
            }
        },
        'post_labor_day': {
            'weekdays': {
                'days': [],  # No weekday releases after Labor Day
                'start_time': None,
                'end_time': None,
            },
            'weekends': {
                'days': ['Saturday'],  # Only Saturday after Labor Day
                'start_time': time(8, 0),
                'end_time': time(12, 0),
            }
        }
    },
    'Extreme Critical': {
        'main_season': {
            'weekdays': {
                'days': ['Wednesday'],
                'start_time': time(8, 0),
                'end_time': time(11, 0),
            },
            'weekends': {
                'days': ['Saturday', 'Sunday'],
                'start_time': time(8, 0),
                'end_time': time(12, 0),
            }
        },
        'post_labor_day': {
            'weekdays': {
                'days': [],  # No weekday releases after Labor Day
                'start_time': None,
                'end_time': None,
            },
            'weekends': {
                'days': [],  # No weekend releases after Labor Day
                'start_time': None,
                'end_time': None,
            }
        }
    }
}

# Add these new penalty weights
LP_RECREATIONAL_FLOW_PENALTY_WEIGHT = 5000.0  # High priority for meeting recreation flows

# EARLY RELEASE CONFIGURATION
EARLY_RELEASE_START_TIME = time(4, 0)    # 4:00 AM on Saturday
EARLY_RELEASE_END_TIME = time(12, 0)     # 12:00 PM (Weekend End Time)
EARLY_RELEASE_TARGET_MW = OXPH_MAX_MW    # Ramp to maximum output (5.8 MW)

# RAFTING FLOW REQUIREMENTS
# Minimum flows required during recreational periods
RAFTING_MIN_FLOW_CFS = 300.0  # Minimum flow for rafting safety
RAFTING_OPTIMAL_FLOW_CFS = 500.0  # Optimal flow for rafting experience

# LINEAR PROGRAMMING WEIGHTS FOR RECREATIONAL PERIODS
# Higher weight = higher penalty for not meeting recreational flow requirements
LP_RECREATIONAL_FLOW_PENALTY_WEIGHT = 5000.0  # High priority, but below spillage