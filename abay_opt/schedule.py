
import pandas as pd
from datetime import date
from . import constants

def labor_day(year:int) -> date:
    # First Monday in September
    sept1 = pd.Timestamp(f"{year}-09-01")
    days = (0 - sept1.weekday() + 7) % 7
    return (sept1 + pd.Timedelta(days=days)).date()

def memorial_day_weekend_start(year:int) -> date:
    # Last Monday in May, then the preceding Saturday
    may_first = date(year, 5, 1)
    # Find first Monday in May
    d = pd.Timestamp(may_first)
    first_monday = d + pd.Timedelta(days=(0 - d.weekday()) % 7)
    # Find last Monday in May
    memorial = first_monday
    while (memorial + pd.Timedelta(days=7)).month == 5:
        memorial = memorial + pd.Timedelta(days=7)
    saturday_before = (memorial - pd.Timedelta(days=2)).date()
    return saturday_before

# Corrected early-release list (Western States fixed to 6/28/2025)
EARLY_RELEASE_SATURDAYS = [
    (5, 24, 2025),  # Memorial Day Weekend
    (5, 31, 2025),
    (6, 7, 2025),
    (6, 21, 2025),
    (6, 28, 2025),  # Western States Weekend (corrected from 7/28)
    (7, 5, 2025),
    (7, 12, 2025),  # Tevis Cup Weekend
    (7, 19, 2025),
    (8, 2, 2025),
    (8, 16, 2025),
    (9, 20, 2025),
]

def is_early_release_day(dt_pt: pd.Timestamp) -> bool:
    d = dt_pt.date()
    for m, day, y in EARLY_RELEASE_SATURDAYS:
        if d == date(y, m, day):
            return True
    return False

def summer_setpoint_required(dt_pt: pd.Timestamp) -> bool:
    """
    Returns True if the summer morning setpoint floor applies at this hour-ending timestamp in Pacific time.
    Uses Memorial-Day-weekend start through Sept 30, and WYT windows from constants.RAFTING_SCHEDULES.
    All 'xx:30' times are treated as *AM* per user's directive.
    """
    dt_pt = pd.Timestamp(dt_pt)

    if dt_pt.tz is None:
        dt_pt = constants.PACIFIC_TZ.localize(dt_pt)
    else:
        dt_pt = dt_pt.tz_convert(constants.PACIFIC_TZ)

    year = dt_pt.year
    day = dt_pt.strftime('%A')

    # Season
    if not (memorial_day_weekend_start(year) <= dt_pt.date() <= date(year, *constants.RAFTING_SEASON_END_DATE)):
        return False

    # Choose main vs post-Labor-Day
    schedule_period = 'main_season' if dt_pt.date() <= labor_day(year) else 'post_labor_day'

    wyt = constants.CURRENT_WATER_YEAR_TYPE
    sched = constants.RAFTING_SCHEDULES[wyt][schedule_period]

    is_weekend = day in ['Saturday', 'Sunday']
    block = sched['weekends'] if is_weekend else sched['weekdays']

    days = block.get('days', [])
    st = block.get('start_time'); et = block.get('end_time')
    if not days or st is None or et is None:
        return False
    if day not in days:
        return False

    # Early release Saturdays => start at 04:00
    if is_weekend and day == 'Saturday' and is_early_release_day(dt_pt):
        st = constants.EARLY_RELEASE_START_TIME
        # end time stays as weekend block's end

    t = dt_pt.time()
    return (st <= t <= et)
