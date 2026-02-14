# PRD Update: ABAY Forecast Intelligence & Operator Decision Support

**Version:** 2.0
**Date:** February 2026
**Status:** Proposed
**Owner:** PCWA Energy Marketing Group
**Audience:** Development Team

---

## 1. Problem Statement

The ABAY optimization engine (MILP via PuLP/CBC) produces sound generation schedules, but operators lack the tools to **understand why the forecast is tracking the way it is**, **what might change**, and **how to adjust effectively**. Three specific gaps exist:

1. **MFRA beyond Day 1 is a guess.** DA awards cover ~24 hours. Hours 25–168 default to 7-day persistence — a naïve "no change" assumption that ignores day-of-week dispatch patterns and seasonal trends.

2. **Bias correction is too blunt.** A single 24-hour average CFS scalar is applied uniformly across the entire 7-day horizon. Bias from a recent storm event should fade; a persistent calibration offset should not.

3. **No forecast confidence visibility.** The Upstream API already returns quantiles (q05–q95) for R4 and R30, but `data_fetcher.py` discards them. Operators see one deterministic elevation line with no sense of how uncertain the future is.

This PRD addresses these gaps with five targeted improvements, ordered by impact.

---

## 2. Optimization Method Assessment

**Recommendation: Keep MILP.** The current PuLP/CBC solver is well-suited to this problem:

- Constraints are linear or piecewise-linear (head loss, ramp rate, water balance, PWL ft↔AF).
- The objective is a weighted sum of penalties — a natural LP formulation.
- Solve time is <2 seconds for 168-hour horizons.
- The setpoint/generation separation with rafting tracking is correctly modeled.

The weaknesses are **not in the solver** but in what feeds it. The improvements below focus on better inputs, better bias, and better operator visibility — all of which improve the optimizer's output without touching `optimizer.py`.

---

## 3. Improvement #1 — Tiered MFRA Forecast Strategy

### 3.1 Current State

| Component | File | Lines | Behavior |
|-----------|------|-------|----------|
| DA awards fetch | `abay_opt/caiso_da.py` | 73–138 | Queries CAISO DAM for MFP1, aggregates hourly MW |
| DA awards lookup | `abay_opt/caiso_da.py` | 144–203 | Queries `CAISODAAwardSummary` for hours overlapping forecast |
| Persistence fallback | `abay_opt/build_inputs.py` | 96–101 | Last 7 days of `MFP_Total_Gen_GEN_MDFK_and_RA`, repeated if shorter than horizon |
| Blending | `abay_opt/build_inputs.py` | 103–109 | DA fills covered hours; persistence fills gaps |

**Problem:** DA awards typically cover only the next delivery day (~24 hours). For a 168-hour forecast, 144 hours (86%) use raw persistence.

### 3.2 Proposed: Three-Tier MFRA Forecast

```
Tier 1 (hours 1–24):   DA awards (high confidence)
Tier 2 (hours 25–48):  Blended DA-to-historical (medium confidence)
Tier 3 (hours 49+):    Historical hourly pattern (low confidence)
```

**Tier 1** — No change. DA awards from `CAISODAAwardSummary` already work.

**Tier 2** — Weighted blend between the last DA award hour's value and the historical mean for that hour-of-day / day-of-week:

```python
blend_weight = 1 - ((hour - 24) / 24)  # Linear decay from 1.0 at hour 25 to 0.0 at hour 48
mfra[t] = blend_weight * da_last_hour + (1 - blend_weight) * historical_pattern[t]
```

**Tier 3** — Historical hourly pattern derived from stored `CAISODAAward` records (past 30–90 days). Compute median MW by `(day_of_week, hour_of_day)` bucket. This captures weekly dispatch cycles (weekday vs weekend) that persistence misses entirely.

### 3.3 Implementation

#### New function in `abay_opt/caiso_da.py`:

```python
def get_historical_mfra_pattern(lookback_days: int = 60) -> pd.DataFrame:
    """
    Query CAISODAAwardSummary for the past `lookback_days` and return
    median total_mw by (day_of_week, hour_of_day_pt).

    Returns DataFrame with columns: [day_of_week, hour, median_mw, count]
    """
```

#### Modify `abay_opt/build_inputs.py` (lines 95–109):

Replace the binary DA-or-persistence logic with the three-tier strategy. New helper:

```python
def _build_tiered_mfra_forecast(
    idx_forecast: pd.DatetimeIndex,
    da_series: Optional[pd.Series],
    persist_raw: pd.Series,
    historical_pattern: pd.DataFrame,
    tier2_hours: int = 24,  # configurable
) -> Tuple[pd.Series, pd.Series]:
    """
    Returns:
      mfra_forecast: pd.Series of MW values
      mfra_confidence: pd.Series of 'high'/'medium'/'low' labels (for UI)
    """
```

#### New constants in `abay_opt/constants.py`:

```python
MFRA_TIER2_BLEND_HOURS = 24       # Duration of Tier 2 blend window
MFRA_HISTORICAL_LOOKBACK_DAYS = 60  # Days of DA history for pattern extraction
```

#### Model change: None required — `CAISODAAwardSummary` already stores the needed history.

### 3.4 Testing

- Run optimizer with historical date where DA awards exist for day 1 only
- Compare Tier 3 (historical pattern) vs persistence against actuals for days 2–3
- Expect: lower RMSE for MFRA forecast at 48h+ lead times

---

## 4. Improvement #2 — Time-Decaying Bias Profile

### 4.1 Current State

| Component | File | Lines | Behavior |
|-----------|------|-------|----------|
| Bias computation | `abay_opt/bias.py` | 6–20 | 24h mean of `(actual_net - expected_net)`, clipped ±2000 CFS |
| Bias application | `abay_opt/build_inputs.py` | 131 | Single scalar applied to all forecast hours: `forecast['bias_cfs'] = float(bias_cfs)` |

**Problem:** A bias caused by a passing storm front should decay as the event ends. A persistent measurement offset should remain. The current approach treats both identically and never decays.

### 4.2 Proposed: Exponential Decay Profile

```python
bias_profile[t] = bias_24h * exp(-t / (half_life_hours * ln(2)))
```

With `half_life_hours = 12` (default, configurable):
- Hour 1: 94% of bias retained
- Hour 12: 50% retained
- Hour 24: 25% retained
- Hour 48: 6% retained
- Hour 72+: ~0% (forecast trusts raw model)

This is intentionally conservative — if the bias is real and persistent, the operator can apply a manual bias override (already supported via the bias adjustment panel).

### 4.3 Implementation

#### New function in `abay_opt/bias.py`:

```python
def compute_decaying_bias_profile(
    lookback_df: pd.DataFrame,
    horizon_hours: int,
    half_life_hours: float = 12.0,
) -> pd.Series:
    """
    Compute a time-decaying bias profile for the forecast horizon.

    Returns pd.Series indexed 0..horizon_hours-1 with decaying bias values (CFS).
    The caller reindexes this to the forecast DatetimeIndex.
    """
    base_bias = compute_bias_cfs_24h(lookback_df)
    hours = np.arange(horizon_hours)
    decay = np.exp(-hours * np.log(2) / half_life_hours)
    return pd.Series(base_bias * decay, index=hours, name='bias_cfs')
```

#### Modify `abay_opt/build_inputs.py` line 131:

```python
# Before:
forecast['bias_cfs'] = float(bias_cfs)

# After:
from .bias import compute_decaying_bias_profile
bias_profile = compute_decaying_bias_profile(lookback, horizon_hours)
forecast['bias_cfs'] = bias_profile.values
```

#### New constant in `abay_opt/constants.py`:

```python
BIAS_DECAY_HALF_LIFE_HOURS = 12.0  # Exponential decay half-life for bias correction
```

#### No changes to `optimizer.py` — it already reads `bias` per-row from `forecast_df['bias_cfs']` (line 71).

### 4.4 Testing

- Compare elevation forecast accuracy (MAE at 24h, 48h, 72h) with static vs decaying bias
- Use historical simulation mode to replay past events
- Expect: improved accuracy at 48h+ lead times; comparable or better at 24h

---

## 5. Improvement #3 — Elevation Confidence Bands

### 5.1 Current State

| Component | File | Lines | Behavior |
|-----------|------|-------|----------|
| Quantile columns requested | `abay_opt/constants.py` | 151–155 | `UPSTREAM_HYDROFORECAST_REQUEST_COLUMNS` includes q05–q95 |
| Quantile extraction | `abay_opt/data_fetcher.py` | 99–184 | `forecasts_to_dataframe()` extracts **only** `target_column_name` (discharge_mean); all quantiles discarded |

**Problem:** The API already sends 7 quantile columns per site. Discarding them means operators have zero visibility into forecast uncertainty.

### 5.2 Proposed: Propagate q10/q90 Through Water Balance

**Approach:** Run two additional deterministic forward simulations (not MILP re-solves) using the q10 and q90 R4+R30 values as inputs while holding OXPH generation fixed at the optimized schedule. This produces a "likely range" for ABAY elevation at each hour.

```
Elevation band:
  - Upper bound: q90 inflows → higher elevation trajectory
  - Central:     mean inflows → optimizer's solution (existing)
  - Lower bound: q10 inflows → lower elevation trajectory
```

### 5.3 Implementation

#### Step 1: Extract quantiles in `abay_opt/data_fetcher.py`

Add a new function alongside `forecasts_to_dataframe()`:

```python
def forecasts_to_dataframe_with_quantiles(
    response_data, site_short_name, forecast_source
) -> pd.DataFrame:
    """
    Like forecasts_to_dataframe but extracts ALL available quantile columns.
    Returns DataFrame with columns like:
      R4_discharge_mean, R4_discharge_q0.1, R4_discharge_q0.9, etc.
    """
```

Alternatively, modify the existing `forecasts_to_dataframe()` to accept `extra_columns: list[str] = None` and extract them alongside the target column.

#### Step 2: Propagate quantiles in `abay_opt/build_inputs.py`

Add optional columns to the forecast DataFrame:

```python
forecast['R4_q10_CFS'] = ...  # from quantile extraction
forecast['R4_q90_CFS'] = ...
forecast['R30_q10_CFS'] = ...
forecast['R30_q90_CFS'] = ...
```

#### Step 3: Generate elevation bands in a new module `abay_opt/confidence.py`

```python
def compute_elevation_bands(
    forecast_df: pd.DataFrame,
    optimized_gen_mw: pd.Series,
    initial_elev_ft: float,
    initial_gen_mw: float,
) -> pd.DataFrame:
    """
    Run deterministic forward simulation with q10 and q90 inflows,
    holding OXPH generation at the optimized schedule.

    Returns DataFrame with columns:
      ABAY_ft_q10, ABAY_ft_q90
    """
```

This reuses the water balance logic from `recalc.py` (`recalc_abay_path`). No new physics needed.

#### Step 4: Store and serve bands

- Add `abay_ft_q10` and `abay_ft_q90` columns to the `OptimizationResult` model (or store in the existing `raw_values` JSON field).
- Return these columns from `OptimizationResultsView` in the chart data payload.

#### Step 5: Display in `dashboard.js`

Add ECharts `areaStyle` between q10 and q90 on the elevation chart:

```javascript
// Add shaded confidence band between q10 and q90
{
    name: 'Confidence Band',
    type: 'line',
    stack: 'confidence',
    areaStyle: { opacity: 0.15, color: '#00d4ff' },
    data: abay_ft_q90,
    lineStyle: { opacity: 0 },
    symbol: 'none',
},
{
    name: 'Lower Bound',
    type: 'line',
    stack: 'confidence',
    areaStyle: { opacity: 0 },
    data: abay_ft_q10.map((v, i) => v - abay_ft_q90[i]),  // negative offset
    lineStyle: { opacity: 0 },
    symbol: 'none',
}
```

### 5.4 MFRA Uncertainty

MFRA has no probabilistic forecast (DA awards are deterministic). To account for MFRA uncertainty:

- **Tier 1 (DA hours):** No additional uncertainty (awards are firm).
- **Tier 2–3:** Add ±1 standard deviation from historical pattern to create MFRA high/low scenarios. Combine with R4/R30 quantiles in the forward simulation.

### 5.5 Testing

- Verify that q10/q90 elevation bands bracket observed actuals ~80% of the time
- Check that bands widen appropriately over the forecast horizon
- Ensure no performance regression (forward sim is lightweight, <100ms)

---

## 6. Improvement #4 — Forecast Tracking & Accuracy Dashboard

### 6.1 Purpose

Let operators answer: *"How well has the forecast been performing? Is it consistently over-predicting? Should I trust the current forecast or apply a bias?"*

### 6.2 Components

#### A. Forecast Snapshot Storage

Each optimization run's forecast is saved as a snapshot for later comparison against actuals.

**New model in `optimization_api/models.py`:**

```python
class ForecastSnapshot(models.Model):
    """Stores the forecast produced by each optimization run for later accuracy analysis."""
    optimization_run = models.ForeignKey(OptimizationRun, on_delete=models.CASCADE, related_name='snapshots')
    timestamp_utc = models.DateTimeField()
    lead_time_hours = models.IntegerField()  # hours from run start
    predicted_abay_ft = models.FloatField()
    predicted_oxph_mw = models.FloatField()
    predicted_net_inflow_cfs = models.FloatField(null=True)
    r4_forecast_cfs = models.FloatField(null=True)
    r30_forecast_cfs = models.FloatField(null=True)
    mfra_forecast_mw = models.FloatField(null=True)
    mfra_source = models.CharField(max_length=20)  # 'da_awards', 'blend', 'historical'
    bias_cfs_applied = models.FloatField(null=True)

    class Meta:
        unique_together = ('optimization_run', 'timestamp_utc')
        indexes = [models.Index(fields=['timestamp_utc', 'lead_time_hours'])]
```

**Population:** At the end of each optimization run in `tasks.py`, bulk-create `ForecastSnapshot` records from the result DataFrame.

#### B. Forecast Accuracy Metrics

A background task computes accuracy once actuals are available.

**New model in `optimization_api/models.py`:**

```python
class ForecastAccuracyLog(models.Model):
    """Per-run accuracy metrics computed once actuals become available."""
    optimization_run = models.OneToOneField(OptimizationRun, on_delete=models.CASCADE, related_name='accuracy')
    computed_at = models.DateTimeField(auto_now_add=True)

    # MAE by lead time bucket
    mae_1h_ft = models.FloatField(null=True)
    mae_6h_ft = models.FloatField(null=True)
    mae_12h_ft = models.FloatField(null=True)
    mae_24h_ft = models.FloatField(null=True)
    mae_48h_ft = models.FloatField(null=True)

    # Component-level accuracy
    r4_mae_24h_cfs = models.FloatField(null=True)
    r30_mae_24h_cfs = models.FloatField(null=True)
    mfra_mae_24h_mw = models.FloatField(null=True)

    # Overall bias direction
    mean_bias_cfs = models.FloatField(null=True)  # positive = model under-predicts inflow
```

**Background task in `tasks.py`:**

```python
@shared_task
def compute_forecast_accuracy(run_id: int):
    """
    Compare ForecastSnapshot predictions against PIDatum actuals.
    Called ~24h after an optimization run completes.
    """
```

Trigger: Schedule via Celery Beat (every hour, check for runs >24h old without accuracy records).

#### C. Bias Trend Chart

**New API endpoint:** `GET /api/forecast-accuracy/bias-trend/?days=7`

Returns hourly rolling 24h bias over the past N days, using `hourly_abay_error_diagnostics()` from `abay_opt/bias.py` (line 27).

**Frontend (dashboard.js):** New ECharts chart (or sub-panel in the existing diagnostics section) showing:
- Rolling 24h bias CFS over time (line chart)
- ±threshold bands (e.g., ±50 CFS) as reference lines
- Color-coded: green when within threshold, amber/red when outside

#### D. Forecast vs Actual Overlay ("Spaghetti Plot")

**New API endpoint:** `GET /api/forecast-accuracy/history/?hours_back=72`

Returns the last N optimization runs' predicted elevation curves alongside the actual observed elevation (from `PIDatum`).

**Frontend (dashboard.js):** Toggle-able overlay on the elevation chart:
- Actual elevation: solid bold line
- Past forecast curves: semi-transparent lines, labeled by run time
- Shows how forecasts have converged (or diverged) over successive runs

### 6.3 Implementation Priority

1. **Snapshot storage** (required by all other components) — add model + populate in `tasks.py`
2. **Bias trend chart** — leverages existing `hourly_abay_error_diagnostics()`; minimal backend work
3. **Accuracy metrics** — background task + new API endpoint
4. **Spaghetti plot** — frontend-heavy, requires snapshot API

---

## 7. Improvement #5 — Operator Adjustment & Alert Tools

### 7.1 Current State

Operators can already:
- Edit MFRA, OXPH, R4, R30 in the Handsontable (`dashboard.js`)
- Trigger `recalc_abay_path()` via `POST /api/recalculate/` to see elevation impact
- Apply a manual bias via `POST /api/optimization-runs/apply-bias/`

### 7.2 Proposed Enhancements

#### A. Live Impact Preview

When the operator edits a cell in Handsontable, show the elevation impact **immediately on the chart** without requiring a "Save" button click. Debounce recalculation calls to avoid API spam (e.g., 500ms after last keystroke).

**Implementation:** Frontend-only change in `dashboard.js`. On Handsontable `afterChange` event, debounce → call `/api/recalculate/` → update elevation chart with a "preview" dashed line alongside the optimized solid line.

#### B. MFRA Override Workflow

Operators sometimes receive advance notice of MDFK dispatch changes (phone calls, emails from dispatch). They need a fast path to:

1. Select a time range in the forecast
2. Set a new MFRA MW value for those hours
3. See the immediate ABAY elevation impact
4. Optionally re-run the optimizer with the updated MFRA profile

**Implementation:**
- Add a "MFRA Override" input mode to Handsontable (highlight overridden cells differently)
- Store overrides as metadata on the `OptimizationResult` (use existing `raw_values` JSON field)
- Add a "Re-optimize with overrides" button that calls `POST /api/run-optimization/` with `customParameters.mfra_overrides`

#### C. Forecast Deviation Alerts

Auto-detect when the actual ABAY trajectory diverges from the forecast and alert the operator.

**Implementation in `optimization_api/alerting.py`:**

Add a new special alert type `forecast_deviation` to `AlertingService._check_special_alert()`:

```python
def _check_forecast_deviation(self, alert, system_data):
    """
    Compare current actual ABAY elevation against the most recent forecast.
    Trigger if |actual - forecast| > threshold for > N consecutive hours.
    """
    latest_run = OptimizationRun.objects.filter(status='completed').latest('completed_at')
    snapshot = ForecastSnapshot.objects.filter(
        optimization_run=latest_run,
        timestamp_utc__lte=now_utc,
    ).order_by('-timestamp_utc').first()

    if snapshot:
        deviation = abs(system_data['abay_elevation_ft'] - snapshot.predicted_abay_ft)
        if deviation > alert.threshold_value:
            return True, deviation
    return False, None
```

**Alert metadata:** Suggest action in the alert message:
- *"ABAY is 1.2 ft below forecast. Consider applying +30 CFS bias or checking for unexpected MFRA changes."*

#### D. Scenario Comparison

Let operators save what-if scenarios and compare them side-by-side.

**New model in `optimization_api/models.py`:**

```python
class OperatorScenario(models.Model):
    """Saved what-if scenario from operator edits."""
    name = models.CharField(max_length=100)
    base_run = models.ForeignKey(OptimizationRun, on_delete=models.CASCADE)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    overrides = models.JSONField()  # {timestamp: {mfra: X, oxph: Y, r4: Z, r30: W}}
    result_elevation_ft = models.JSONField()  # [ft values after recalc]
    notes = models.TextField(blank=True)
```

**API endpoints:**
- `POST /api/scenarios/` — Save current edits as a named scenario
- `GET /api/scenarios/` — List saved scenarios
- `GET /api/scenarios/<id>/` — Retrieve scenario for overlay on chart

---

## 8. Implementation Phases

### Phase 1: Core Forecast Intelligence (Highest Impact)

**Goal:** Better inputs → better optimization output, no UI changes required.

| Task | Files | Effort |
|------|-------|--------|
| Tiered MFRA forecast (3-tier strategy) | `caiso_da.py`, `build_inputs.py`, `constants.py` | Medium |
| Time-decaying bias profile | `bias.py`, `build_inputs.py`, `constants.py` | Small |
| Unit tests for new functions | `tests/` (new) | Small |

**Verification:** Run historical simulations comparing old vs new MFRA/bias strategy. Measure MAE at 24h, 48h, 72h lead times.

### Phase 2: Confidence Bands

**Goal:** Operators see forecast uncertainty on the elevation chart.

| Task | Files | Effort |
|------|-------|--------|
| Extract quantile columns from Upstream API | `data_fetcher.py` | Small |
| Forward-sim with q10/q90 inputs | `confidence.py` (new), `build_inputs.py` | Medium |
| Store bands in OptimizationResult | `models.py`, `views.py`, `tasks.py` | Small |
| Display bands on elevation chart | `dashboard.js` | Medium |

**Verification:** Visual inspection that bands bracket actuals ~80% of the time. Check bands widen over horizon.

### Phase 3: Forecast Tracking Dashboard

**Goal:** Operators can evaluate forecast performance over time.

| Task | Files | Effort |
|------|-------|--------|
| ForecastSnapshot model + population | `models.py`, `tasks.py` | Medium |
| ForecastAccuracyLog model + background task | `models.py`, `tasks.py` | Medium |
| Bias trend API + chart | `views.py`, `dashboard.js` | Medium |
| Spaghetti plot API + chart | `views.py`, `dashboard.js` | Medium |

**Verification:** After 1 week of runs, verify accuracy metrics are computed and displayed correctly. Confirm bias trend chart matches manual calculations.

### Phase 4: Enhanced Operator Tools

**Goal:** Operators can quickly adjust and compare scenarios.

| Task | Files | Effort |
|------|-------|--------|
| Live impact preview (debounced recalc) | `dashboard.js` | Small |
| MFRA override workflow | `dashboard.js`, `views.py` | Medium |
| Forecast deviation alerts | `alerting.py`, `models.py` | Medium |
| Scenario save/compare | `models.py`, `views.py`, `dashboard.js` | Large |

**Verification:** End-to-end test: operator edits MFRA → sees elevation change → saves scenario → compares against original.

---

## 9. Files to Modify (Summary)

| File | Phase | Changes |
|------|-------|---------|
| `abay_opt/caiso_da.py` | 1 | Add `get_historical_mfra_pattern()` |
| `abay_opt/build_inputs.py` | 1, 2 | Tiered MFRA, decaying bias, quantile propagation |
| `abay_opt/bias.py` | 1 | Add `compute_decaying_bias_profile()` |
| `abay_opt/constants.py` | 1, 2 | New config constants (half-life, tier hours, lookback days) |
| `abay_opt/data_fetcher.py` | 2 | Extract quantile columns from Upstream API response |
| `abay_opt/confidence.py` (new) | 2 | Elevation band computation via forward simulation |
| `django_backend/optimization_api/models.py` | 3, 4 | `ForecastSnapshot`, `ForecastAccuracyLog`, `OperatorScenario` |
| `django_backend/optimization_api/views.py` | 3, 4 | New API endpoints for accuracy, scenarios |
| `django_backend/optimization_api/tasks.py` | 3 | Snapshot population, accuracy background task |
| `django_backend/optimization_api/alerting.py` | 4 | Forecast deviation alert type |
| `django_backend/static/js/dashboard.js` | 2, 3, 4 | Confidence bands, bias trend, spaghetti plot, live preview |

---

## 10. What This Enables for Operators

After all phases are complete, an operator's workflow looks like:

1. **Morning check:** Open dashboard. See the elevation forecast with confidence bands. Immediately know: "Am I in a tight window or do I have margin?"

2. **Assess trust:** Glance at the bias trend chart. If the model has been consistently under-predicting by 40 CFS for the past 3 days, they know to mentally adjust (or apply a manual bias).

3. **React to dispatch changes:** Phone call says MDFK is ramping up 50 MW in 2 hours. Override MFRA in the table for those hours, see the elevation impact instantly. Save as a scenario. Re-optimize if needed.

4. **Track accuracy:** At end of shift, review the spaghetti plot. See how this morning's forecast compared to what actually happened. Note that R4 consistently over-forecasts during dry weather — useful tribal knowledge confirmed by data.

5. **Get alerted:** If ABAY deviates >1 ft from forecast for 2+ hours, receive a notification suggesting a bias check or forecast refresh. No need to manually monitor the chart.

---

## Appendix A: Key Equations Reference

| Equation | Source | Used In |
|----------|--------|---------|
| `ABAY_AF = 0.6311303 * ft² - 1403.8 * ft + 780566` | `physics.py:9-11` | Stage-storage mapping |
| `OXPH_CFS = 163.73 * MW + 83` | `constants.py:98-99` | Water balance |
| `g_max = 0.0912 * H - 101.42` | `constants.py:114-115` | Head loss constraint |
| `MF12_MW = (MFRA - min(86, max(0, (R4-R5L)/10))) * 0.59` | `physics.py:80-81` | GEN mode reduction |
| `bias[t] = bias_24h * exp(-t * ln(2) / half_life)` | Proposed | Decaying bias |

## Appendix B: Data Source Coverage

| Input | Source | Forecast Coverage | Confidence |
|-------|--------|-------------------|------------|
| R4 Flow | Upstream API (HydroForecast / CNRFC) | 7 days, with quantiles | High (days 1–2), Medium (days 3–7) |
| R30 Flow | Upstream API (HydroForecast / CNRFC) | 7 days, with quantiles | High (days 1–2), Medium (days 3–7) |
| MFRA MW | CAISO DA awards + tiered fallback | 1 day (DA), 2 days (blend), 4 days (pattern) | High → Low |
| R20, R5L, R26 | Last observed (persistence) | Held constant | Low beyond 6h |
| Float setpoint | Operator-set PI tag | Held constant | N/A (operator decision) |
| Bias | 24h rolling average, decaying | Decays over horizon | High (hours 1–12), Low (hours 24+) |
