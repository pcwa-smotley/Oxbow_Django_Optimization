# PRD: ABAY Forecast Reliability and Operator Decision Support

## Document Control
- Version: 3.1 (consolidated from PRD.md v2.1, PRD_Update.md, PRD_udated_codex.md)
- Status: Active — Phase 0.5 complete, Phase A planning
- Date: March 13, 2026
- Owner: PCWA Energy Marketing Group / Optimization + Operations (ABAY)
- Scope: `abay_opt/` optimization flow, Django operator workflow, and alerting platform

---

## 1. Executive Summary

This PRD defines the phased roadmap for the ABAY optimization system. The core MILP optimizer and the operator-facing dashboard are now production-ready with a full UI overhaul completed in February 2026. The next phases focus on:

1. **SMS/voice alerting deployed** (Twilio approved March 2026, fully operational)
2. **Forecast intelligence** — tiered MFRA, decaying bias, confidence bands
3. **Operator decision support** — tracking, accuracy dashboard, scenario comparison

**Recommendation: Keep MILP.** The current PuLP/CBC solver is well-suited to this problem. The weaknesses are not in the solver but in what feeds it. The improvements below focus on better inputs, better bias, and better operator visibility — all of which improve the optimizer's output without touching `optimizer.py`.

## 2. Problem Statement

Current optimization logic produces useful schedules, but operators still need better confidence and control in three areas:

1. **MFRA beyond Day 1 is a guess.** DA awards cover ~24 hours. Hours 25-168 default to 7-day persistence — a naive "no change" assumption that ignores day-of-week dispatch patterns and seasonal trends.

2. **Bias correction is too blunt.** A single 24-hour average CFS scalar is applied uniformly across the entire 7-day horizon. Bias from a recent storm event should fade; a persistent calibration offset should not.

3. **No forecast confidence visibility.** The Upstream API already returns quantiles (q05-q95) for R4 and R30, but `data_fetcher.py` discards them. Operators see one deterministic elevation line with no sense of how uncertain the future is.

## 3. Current-State Assessment

### 3.1 What is working now

**Optimization Engine:**
- `abay_opt/optimizer.py` solves a constrained schedule with ABAY storage/elevation physics (piecewise ft<->AF), ramp limits, head limit constraints, rafting window handling, and strong penalties for elevation bound violations.
- `abay_opt/build_inputs.py` supports MFRA DA awards with persistence fallback.
- `abay_opt/bias.py` computes 24-hour signed bias applied additively to forecast net inflow.
- `abay_opt/recalc.py` supports forward recalculation from edited hours for operator interaction.
- Solve time is <2 seconds for 168-hour horizons.

**Dashboard UI (fully overhauled Feb 2026):**
- Apache ECharts 5 with synced charts, DataZoom, day dividers.
- Neon control room dark theme with glassmorphism.
- KPI gauge strip, system schematic, 7-day timeline, command palette.
- Smart alert toasts with severity icons and audio chimes.
- MFRA source indicator (DA Awards vs Persistence badge).
- Editable Handsontable data grid with physics-parity recalculation.

**Data Table Remediation (complete):**
- ABAY forecast visibility, physics-parity setpoint editing, correct timestamp semantics, R20 editing support, blinking current-row indicator.

**Alerting System (fully deployed March 2026):**
- Multi-channel engine (email, SMS, voice, browser) with Twilio integration, cooldown logic, per-user preferences, and category-based thresholds.
- Twilio API approved and operational — SMS/voice alerts live.
- Re-arm/hysteresis logic: alerts fire once on threshold crossing, disarm, then re-arm only after value returns to safe zone.
- Dashboard Alerts tab with full CRUD: flows (R4, R11, R30), Afterbay elevation, OXPH deviation, rafting ramp, MF RT vs DA deviation, ABAY forecast deviation.
- Test notification system (SMS, email, voice, browser) accessible from Alerts tab.
- Alert history with notification channel indicators.

**CAISO DA Awards Integration (operational):**
- Fetch, aggregate, query, and blend DA awards into the optimizer pipeline.

### 3.2 Gaps to close
- ~~SMS/voice alert delivery~~: Completed March 2026 — Twilio approved and operational.
- Forecast confidence and source not tracked per hour as first-class data.
- No explicit risk-reserve logic for unexpected MDFK dispatch shocks.
- Forecast-vs-actual tracking not formalized as an operator workflow.
- Run-comparison UX/API needs a complete, supported contract.
- Tiered MFRA forecasting, decaying bias, and confidence bands are designed but not yet implemented.

## 4. Product Vision

Create an operator-first optimization system where each run is:
- **Explainable**: operators can see exactly which assumptions and data sources drove each hour.
- **Trackable**: operators can see how the run performed as actuals arrived.
- **Adjustable**: operators can safely apply bias, flow, or dispatch overrides and immediately see impact.
- **Risk-aware**: schedules include explicit protection against likely uncertainty events.
- **Alert-driven**: critical conditions notify operators via SMS/voice/email without requiring active monitoring.

## 5. Goals and Non-Goals

### 5.1 Goals
- Deploy SMS/voice alerts via Twilio once API approval is obtained.
- Improve ABAY forecast reliability under uncertain inflow and MDFK dispatch conditions.
- Reduce spill risk caused by late schedule response to dispatch/flow shocks.
- Give operators a full forecast lifecycle view: planned -> tracking -> adjusted -> saved scenario.
- Preserve current production workflow and avoid destabilizing the existing optimization engine.

### 5.2 Non-Goals
- Replacing the MILP solver with a completely different optimizer.
- Building fully autonomous dispatch without operator review.
- Introducing a new database platform (SQLite remains acceptable for ~8 users).

## 6. Primary Users and Use Cases

### 6.1 Reservoir Operators
- Run forecast optimization for next 72 hours.
- See per-hour assumption provenance (DA vs persistence vs actual).
- Detect forecast drift and apply corrective bias/override adjustments.
- Save and compare scenarios.
- Receive SMS/voice alerts for critical conditions without active monitoring.

### 6.2 Optimization Engineers
- Validate solver behavior versus recalc behavior.
- Analyze errors by source component.
- Tune risk settings (dispatch shock margin, bias behavior, smoothing priorities).

### 6.3 Operations Leadership
- Review reliability metrics (bound compliance, spill avoidance, forecast error).
- Audit why a run changed and who adjusted assumptions.

---

## 7. Functional Requirements

### FR-1: SMS/Voice Alert Deployment (Immediate Priority)

The alerting backend is fully implemented. Deployment is blocked only on Twilio API approval.

Requirements:
- Once Twilio API approval is granted, configure production credentials and verify delivery.
- Operators receive SMS alerts within 60 seconds of threshold violation.
- Voice call escalation for critical unacknowledged alerts after cooldown.
- Per-user notification preferences (channel, phone number, email) managed via UserProfile.
- Alert logs persisted and queryable in the dashboard.

Acceptance criteria:
- End-to-end SMS delivery verified with `monitor_alerts --once --test-mode`.
- All configured alert categories (Flow, Afterbay, Rafting, Generation) trigger on the correct channels.
- Cooldown logic prevents alert fatigue.

### FR-2: Forecast Source and Confidence Layer

The system must store and expose forecast provenance per hour for MFRA and key inflow terms.

Requirements:
- For each forecast hour, store:
  - MFRA source type: `da_awards`, `persistence`, `actual`, `manual_override`.
  - Source coverage and freshness metadata (for DA).
  - Forecast confidence score (0-100) based on source quality + recent error.
- UI must show a per-hour provenance marker and a run-level summary (e.g., "DA 18/24h, persistence 6/24h").
- If DA coverage is partial, gaps must be explicitly marked as fallback hours.

Acceptance criteria:
- Operator can identify MFRA source for any hour without opening logs.
- API returns both values and provenance in a single response contract.

### FR-3: Robust Optimization Enhancements (Keep MILP Core)

The optimization method should remain MILP-based, with added robustness controls.

Requirements:
- Continue deterministic base solve (current path), then run risk checks:
  - Dispatch shock scenario (unexpected MDFK increase profile).
  - River flow error scenarios (R4/R30 high/low bands).
- Add configurable reserve/headroom objective or penalty so schedules pre-position ABAY when risk is elevated.
- Support scenario-aware recommendations without forcing hard infeasibility where not needed.

Acceptance criteria:
- In replay tests, high-risk periods show proactive OXPH positioning versus baseline-only behavior.
- Spill-risk metric improves versus current baseline for the same test windows.

### FR-4: Forecast Tracking Over Time

Operators need an explicit "tracking" experience for each run.

Requirements:
- For each saved run, track forecast-versus-actual error as actuals arrive.
- Show tracking views at minimum horizons: +1h, +6h, +24h.
- Provide error decomposition views: bias component, river forecast miss (R4/R30), MDFK/MFRA dispatch miss, mode change impacts (GEN/SPILL transitions).
- Show "what changed" between two runs (inputs, bias, setpoints, resulting ABAY path).

Acceptance criteria:
- Operator can select two runs and view delta in ABAY, OXPH, MFRA assumptions, and spill risk.
- Tracking metrics persist and are queryable per run.

### FR-5: Adjustment Workflow (Bias + Overrides + Scenarios)

Adjustments must be fast, traceable, and physically consistent.

Requirements:
- Support: global bias updates (existing), component-level bias overrides, hourly overrides for MFRA, R4, R30, R20, OXPH.
- Recalc from earliest edited hour forward with physics parity to optimization assumptions.
- Every adjustment save must include: user, timestamp, changed fields, reason/note, parent run.

Acceptance criteria:
- Operator can apply an adjustment and see updated ABAY trajectory within the current session.
- Saved adjusted runs are auditable and reloadable.

### FR-6: DA Awards Operationalization

DA awards must move from optional fetch to dependable operational input.

Requirements:
- Add scheduled DA fetch job and status health indicator.
- Surface publish/fetch timestamps and coverage completeness.
- If DA unavailable or stale, degrade gracefully and alert operator.

Acceptance criteria:
- Operators can see whether DA awards are fresh enough for the active run.
- Missing/stale DA data triggers a visible warning and logs fallback behavior.

### FR-7: Alerting Additions for Forecast Integrity

Requirements:
- New alert types: forecast divergence exceeds threshold, DA awards missing/stale near run time, elevated spill risk under scenario stress.
- Respect existing cooldown/channel settings.
- Deliver via SMS/voice once Twilio is live.

Acceptance criteria:
- Alert can be configured per user and appears in existing alert channels.

### FR-8: Real-Time Dispatch Monitoring and Alerting

The system must monitor real-time dispatch against Day Ahead awards and alert operators when significant deviations occur, indicating either revenue opportunities or curtailment risk.

**Background:**
PCWA bids all 210 MW of MDFKRL capacity into the RT market with a tiered bid curve. The portion up to the DA award is bid at a low price (e.g., -$100) to ensure execution. The remaining capacity is bid at a higher price (e.g., $60). If RT prices spike above the higher bid price, the full capacity is dispatched — a revenue opportunity. If RT prices drop below the must-run bid, the unit may be curtailed to 0 MW.

**Data sources (confirmed operational 2/17/2026):**
- DA Awards: `RetrieveMarketAwards_CMRIv4_AP` with `marketType=DAM`, `executionType=IFM`
- RT Awards (FMM): `RetrieveMarketAwards_CMRIv4_AP` with `marketType=RTM`, `executionType=RTUC`
- RT Prices (FMM/RTD): `RetrieveSchedulePrices_CMRIv3_DocAttach_AP`
- RT Bid Curves (future): SIBR `retrieveCurrentBidResults` endpoint (separate from CMRI)

Requirements:
- Periodic RT dispatch polling (every 15 minutes minimum, aligned with FMM clearing).
- Compare RT dispatch MW vs DA award MW per resource per interval.
- Alert triggers:
  - **Upward dispatch spike**: RT dispatch exceeds DA award by a configurable MW threshold (e.g., +20 MW). Indicates RT price exceeded bid curve and additional generation is being dispatched.
  - **Negative price curtailment**: RT dispatch drops to 0 MW when DA award was > 0. Indicates RT price fell below must-run bid.
  - **Price threshold breach**: RT LMP at resource PNode exceeds or drops below configurable price thresholds.
- Alert messages must include: resource name, DA award MW, RT dispatch MW, current RT LMP, and estimated revenue impact of the deviation.
- Store RT dispatch history for post-analysis and settlement verification.
- Dashboard panel showing DA vs RT dispatch side-by-side with RT LMP overlay.

Acceptance criteria:
- Operators receive dispatch deviation alerts within 15 minutes of FMM clearing.
- Alert contains sufficient context (MW delta, LMP, revenue impact) for operator to take action.
- Historical RT dispatch data is queryable for settlement analysis.
- Dashboard panel provides visual DA vs RT comparison at FMM granularity.

---

## 8. Technical Specifications

### 8.1 Tiered MFRA Forecast Strategy

#### Current State

| Component | File | Behavior |
|-----------|------|----------|
| DA awards fetch | `abay_opt/caiso_da.py` | Queries CAISO DAM for MFP1, aggregates hourly MW |
| DA awards lookup | `abay_opt/caiso_da.py` | Queries `CAISODAAwardSummary` for hours overlapping forecast |
| Persistence fallback | `abay_opt/build_inputs.py` | Last 7 days of `MFP_Total_Gen_GEN_MDFK_and_RA`, repeated if shorter than horizon |
| Blending | `abay_opt/build_inputs.py` | DA fills covered hours; persistence fills gaps |

**Problem:** DA awards typically cover only the next delivery day (~24 hours). For a 168-hour forecast, 144 hours (86%) use raw persistence.

#### Proposed: Three-Tier MFRA Forecast

```
Tier 1 (hours 1-24):   DA awards (high confidence)
Tier 2 (hours 25-48):  Blended DA-to-historical (medium confidence)
Tier 3 (hours 49+):    Historical hourly pattern (low confidence)
```

**Tier 1** — No change. DA awards from `CAISODAAwardSummary` already work.

**Tier 2** — Weighted blend between the last DA award hour's value and the historical mean for that hour-of-day / day-of-week:

```python
blend_weight = 1 - ((hour - 24) / 24)  # Linear decay from 1.0 at hour 25 to 0.0 at hour 48
mfra[t] = blend_weight * da_last_hour + (1 - blend_weight) * historical_pattern[t]
```

**Tier 3** — Historical hourly pattern derived from stored `CAISODAAward` records (past 30-90 days). Compute median MW by `(day_of_week, hour_of_day)` bucket. This captures weekly dispatch cycles (weekday vs weekend) that persistence misses entirely.

#### Implementation

New function in `abay_opt/caiso_da.py`:
```python
def get_historical_mfra_pattern(lookback_days: int = 60) -> pd.DataFrame:
    """
    Query CAISODAAwardSummary for the past `lookback_days` and return
    median total_mw by (day_of_week, hour_of_day_pt).
    Returns DataFrame with columns: [day_of_week, hour, median_mw, count]
    """
```

Modify `abay_opt/build_inputs.py` — replace the binary DA-or-persistence logic:
```python
def _build_tiered_mfra_forecast(
    idx_forecast: pd.DatetimeIndex,
    da_series: Optional[pd.Series],
    persist_raw: pd.Series,
    historical_pattern: pd.DataFrame,
    tier2_hours: int = 24,
) -> Tuple[pd.Series, pd.Series]:
    """
    Returns:
      mfra_forecast: pd.Series of MW values
      mfra_confidence: pd.Series of 'high'/'medium'/'low' labels (for UI)
    """
```

New constants in `abay_opt/constants.py`:
```python
MFRA_TIER2_BLEND_HOURS = 24
MFRA_HISTORICAL_LOOKBACK_DAYS = 60
```

**Testing:** Run optimizer with historical date where DA awards exist for day 1 only. Compare Tier 3 (historical pattern) vs persistence against actuals for days 2-3. Expect lower RMSE at 48h+ lead times.

### 8.2 Time-Decaying Bias Profile

#### Current State

| Component | File | Behavior |
|-----------|------|----------|
| Bias computation | `abay_opt/bias.py` | 24h mean of `(actual_net - expected_net)`, clipped +/-2000 CFS |
| Bias application | `abay_opt/build_inputs.py` | Single scalar applied to all forecast hours |

**Problem:** A bias caused by a passing storm front should decay as the event ends. The current approach never decays.

#### Proposed: Exponential Decay Profile

```python
bias_profile[t] = bias_24h * exp(-t * ln(2) / half_life_hours)
```

With `half_life_hours = 12` (default, configurable):
- Hour 1: 94% of bias retained
- Hour 12: 50% retained
- Hour 24: 25% retained
- Hour 48: 6% retained
- Hour 72+: ~0% (forecast trusts raw model)

#### Implementation

New function in `abay_opt/bias.py`:
```python
def compute_decaying_bias_profile(
    lookback_df: pd.DataFrame,
    horizon_hours: int,
    half_life_hours: float = 12.0,
) -> pd.Series:
    """
    Compute a time-decaying bias profile for the forecast horizon.
    Returns pd.Series indexed 0..horizon_hours-1 with decaying bias values (CFS).
    """
    base_bias = compute_bias_cfs_24h(lookback_df)
    hours = np.arange(horizon_hours)
    decay = np.exp(-hours * np.log(2) / half_life_hours)
    return pd.Series(base_bias * decay, index=hours, name='bias_cfs')
```

Modify `abay_opt/build_inputs.py`:
```python
# Before:
forecast['bias_cfs'] = float(bias_cfs)

# After:
from .bias import compute_decaying_bias_profile
bias_profile = compute_decaying_bias_profile(lookback, horizon_hours)
forecast['bias_cfs'] = bias_profile.values
```

New constant: `BIAS_DECAY_HALF_LIFE_HOURS = 12.0`

No changes to `optimizer.py` — it already reads `bias` per-row from `forecast_df['bias_cfs']`.

**Testing:** Compare elevation forecast accuracy (MAE at 24h, 48h, 72h) with static vs decaying bias using historical simulation mode. Expect improved accuracy at 48h+.

### 8.3 Elevation Confidence Bands (q10/q90)

#### Current State

The Upstream API already sends 7 quantile columns per site, but `data_fetcher.py` extracts only `discharge_mean` and discards all quantiles. Operators have zero visibility into forecast uncertainty.

#### Proposed: Propagate q10/q90 Through Water Balance

Run two additional deterministic forward simulations (not MILP re-solves) using q10 and q90 R4+R30 values as inputs while holding OXPH generation fixed at the optimized schedule. This produces a "likely range" for ABAY elevation at each hour.

```
Elevation band:
  - Upper bound: q90 inflows -> higher elevation trajectory
  - Central:     mean inflows -> optimizer's solution (existing)
  - Lower bound: q10 inflows -> lower elevation trajectory
```

#### Implementation

**Step 1** — Extract quantiles in `abay_opt/data_fetcher.py`:
```python
def forecasts_to_dataframe_with_quantiles(
    response_data, site_short_name, forecast_source
) -> pd.DataFrame:
    """Extracts ALL available quantile columns alongside discharge_mean."""
```

**Step 2** — Propagate quantiles in `abay_opt/build_inputs.py`:
```python
forecast['R4_q10_CFS'] = ...
forecast['R4_q90_CFS'] = ...
forecast['R30_q10_CFS'] = ...
forecast['R30_q90_CFS'] = ...
```

**Step 3** — Generate elevation bands in new module `abay_opt/confidence.py`:
```python
def compute_elevation_bands(
    forecast_df: pd.DataFrame,
    optimized_gen_mw: pd.Series,
    initial_elev_ft: float,
    initial_gen_mw: float,
) -> pd.DataFrame:
    """
    Forward simulation with q10 and q90 inflows, holding OXPH at optimized schedule.
    Reuses water balance logic from recalc.py. Returns ABAY_ft_q10, ABAY_ft_q90.
    """
```

**Step 4** — Store bands in `OptimizationResult` (or `raw_values` JSON field). Return from API.

**Step 5** — Display in `dashboard.js` as ECharts `areaStyle` shaded band between q10 and q90.

**MFRA Uncertainty:**
- Tier 1 (DA hours): No additional uncertainty (awards are firm).
- Tier 2-3: Add +/-1 standard deviation from historical pattern. Combine with R4/R30 quantiles in forward simulation.

**Testing:** Verify q10/q90 bands bracket observed actuals ~80% of the time. Check bands widen over horizon. Forward sim is lightweight (<100ms).

### 8.4 Forecast Tracking & Accuracy Dashboard

#### A. Forecast Snapshot Storage

Each optimization run's forecast is saved as a snapshot for later comparison against actuals.

```python
class ForecastSnapshot(models.Model):
    optimization_run = models.ForeignKey(OptimizationRun, on_delete=models.CASCADE, related_name='snapshots')
    timestamp_utc = models.DateTimeField()
    lead_time_hours = models.IntegerField()
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

Population: At the end of each optimization run in `tasks.py`, bulk-create `ForecastSnapshot` records from the result DataFrame.

#### B. Forecast Accuracy Metrics

A background task computes accuracy once actuals are available.

```python
class ForecastAccuracyLog(models.Model):
    optimization_run = models.OneToOneField(OptimizationRun, on_delete=models.CASCADE, related_name='accuracy')
    computed_at = models.DateTimeField(auto_now_add=True)
    mae_1h_ft = models.FloatField(null=True)
    mae_6h_ft = models.FloatField(null=True)
    mae_12h_ft = models.FloatField(null=True)
    mae_24h_ft = models.FloatField(null=True)
    mae_48h_ft = models.FloatField(null=True)
    r4_mae_24h_cfs = models.FloatField(null=True)
    r30_mae_24h_cfs = models.FloatField(null=True)
    mfra_mae_24h_mw = models.FloatField(null=True)
    mean_bias_cfs = models.FloatField(null=True)  # positive = model under-predicts inflow
```

Trigger: Schedule via Celery Beat (every hour, check for runs >24h old without accuracy records).

#### C. Bias Trend Chart

API: `GET /api/forecast-accuracy/bias-trend/?days=7` — returns hourly rolling 24h bias using `hourly_abay_error_diagnostics()` from `abay_opt/bias.py`.

Frontend: ECharts line chart showing rolling 24h bias CFS with +/-threshold bands, color-coded green/amber/red.

#### D. Forecast vs Actual Overlay ("Spaghetti Plot")

API: `GET /api/forecast-accuracy/history/?hours_back=72` — returns last N optimization runs' predicted elevation curves alongside actual observed elevation.

Frontend: Toggle-able overlay on elevation chart. Actual = solid bold, past forecasts = semi-transparent lines labeled by run time.

#### Implementation Priority
1. Snapshot storage (required by all other components)
2. Bias trend chart (leverages existing `hourly_abay_error_diagnostics()`)
3. Accuracy metrics (background task + new API endpoint)
4. Spaghetti plot (frontend-heavy, requires snapshot API)

### 8.5 Operator Adjustment & Alert Tools

#### A. Live Impact Preview

When the operator edits a cell in Handsontable, show the elevation impact immediately on the chart without requiring a "Save" button click. Debounce recalculation calls (500ms after last keystroke).

Implementation: Frontend-only change in `dashboard.js`. On `afterChange` event, debounce -> call `/api/recalculate/` -> update elevation chart with a "preview" dashed line.

#### B. MFRA Override Workflow

Operators sometimes receive advance notice of MDFK dispatch changes. They need a fast path to: select a time range, set new MFRA MW for those hours, see immediate elevation impact, optionally re-optimize.

Implementation:
- Add "MFRA Override" input mode to Handsontable (highlight overridden cells differently)
- Store overrides in `OptimizationResult.raw_values` JSON field
- Add "Re-optimize with overrides" button calling `POST /api/run-optimization/` with `customParameters.mfra_overrides`

#### C. Forecast Deviation Alerts

Auto-detect when actual ABAY trajectory diverges from forecast and alert the operator.

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

Alert message includes actionable suggestion: "ABAY is 1.2 ft below forecast. Consider applying +30 CFS bias or checking for unexpected MFRA changes."

#### D. Scenario Comparison

```python
class OperatorScenario(models.Model):
    name = models.CharField(max_length=100)
    base_run = models.ForeignKey(OptimizationRun, on_delete=models.CASCADE)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    overrides = models.JSONField()  # {timestamp: {mfra: X, oxph: Y, r4: Z, r30: W}}
    result_elevation_ft = models.JSONField()  # [ft values after recalc]
    notes = models.TextField(blank=True)
```

API: `POST /api/scenarios/`, `GET /api/scenarios/`, `GET /api/scenarios/<id>/`

---

## 9. UX Requirements

### 9.1 Dashboard (Completed)
- Neon control room dark theme with glassmorphism cards.
- Apache ECharts 5 with synced crosshairs, DataZoom, day dividers.
- KPI gauge strip (ABAY Elevation, OXPH Output, Spill Risk, Revenue Rate, Forecast Confidence).
- Animated SVG system schematic with particle flow animations.
- 7-day operations timeline with rafting window highlights.
- Command palette (Ctrl+K) with fuzzy search and keyboard shortcuts.
- Smart alert toasts with severity icons, audio chimes, stacking.
- MFRA source indicator badge (DA Awards / Persistence).
- Editable Handsontable data grid with physics-parity recalculation.
- Blinking dot on current data row.

### 9.2 Tracking Panel (Planned -- Phase B)
- Forecast age and confidence trend.
- Forecast vs actual ABAY line with divergence markers.
- Source provenance strip (DA/persistence/manual/actual).
- "What changed since last run" summary cards.

### 9.3 Scenario Workspace (Planned -- Phase B)
- Baseline run pinned.
- One-click branch to "Adjusted Scenario".
- Side-by-side chart/table compare for ABAY, OXPH, MFRA, risk metrics.

### 9.4 Operator Guidance (Planned -- Phase C)
- Next critical setpoint action time.
- Risk explanation (e.g., "High MDFK uncertainty 10:00-14:00 PT").
- Suggested mitigation options.

---

## 10. Technical Approach

### 10.1 Optimization Architecture
1. Deterministic MILP schedule (existing core).
2. Scenario stress evaluation against candidate schedule.
3. Optional re-solve with risk penalties/reserve targets if risk score exceeds threshold.
4. Persist full assumption and risk metadata with run.

### 10.2 Data/Model Additions
- `ForecastAssumptionHour`: per-hour input value + provenance + confidence.
- `RunTrackingPoint`: per-hour forecast-vs-actual tracking metrics.
- `RunChangeLog`: structured input/output deltas between related runs.
- `ForecastSnapshot`: per-hour forecast for later accuracy comparison.
- `ForecastAccuracyLog`: per-run accuracy metrics computed once actuals arrive.
- `OperatorScenario`: saved what-if scenarios from operator edits.

### 10.3 API Additions
- Recent runs by user.
- Run comparison.
- Tracking metrics for a run.
- Forecast provenance summary.
- Forecast accuracy and bias trend.
- Scenario CRUD.

All endpoints must return UTC timestamps with explicit PT rendering guidance for UI.

---

## 11. Operator Workflow Vision

After all phases are complete, an operator's workflow looks like:

1. **Morning check:** Open dashboard. See the elevation forecast with confidence bands. Immediately know: "Am I in a tight window or do I have margin?"

2. **Assess trust:** Glance at the bias trend chart. If the model has been consistently under-predicting by 40 CFS for the past 3 days, they know to mentally adjust (or apply a manual bias).

3. **React to dispatch changes:** Phone call says MDFK is ramping up 50 MW in 2 hours. Override MFRA in the table for those hours, see the elevation impact instantly. Save as a scenario. Re-optimize if needed.

4. **Track accuracy:** At end of shift, review the spaghetti plot. See how this morning's forecast compared to what actually happened. Note that R4 consistently over-forecasts during dry weather — useful tribal knowledge confirmed by data.

5. **Get alerted:** If ABAY deviates >1 ft from forecast for 2+ hours, receive an SMS notification suggesting a bias check or forecast refresh. No need to manually monitor the chart.

---

## 12. Success Metrics

Operational metrics:
- Bound compliance: ABAY min/float violations per month.
- Spill performance: total spill AF and near-spill hours.
- Forecast quality: MAE/RMSE at +1h, +6h, +24h.
- Adjustment effectiveness: post-adjustment error reduction.
- Alert responsiveness: time from threshold violation to SMS delivery.

Adoption metrics:
- Percent of runs with provenance visible.
- Percent of operators using run comparison/tracking weekly.
- Time-to-decision after forecast divergence alert.
- Percent of operators with SMS alerts enabled.

---

## 13. Phased Delivery Plan

### Phase 0: Dashboard & Data Table (COMPLETED -- Feb 2026)
- Full UI overhaul: ECharts migration, neon theme, gauges, schematic, timeline, command palette.
- Data table remediation: ABAY forecast visibility, physics-parity editing, timestamp semantics, R20 editing.
- Alerting backend: multi-channel engine with Twilio integration, cooldown logic, per-user preferences.
- CAISO DA Awards: fetch, aggregate, query, and blend into optimizer pipeline.

### Phase 0.5: SMS/Voice Alert Deployment (BLOCKED -- Twilio API Approval)
- Configure production Twilio credentials once API approval is granted.
- Verify end-to-end SMS/voice delivery.
- Operator onboarding: phone number entry, preference selection, test alerts.
- Deploy `monitor_alerts` on recurring schedule.

### Phase 1: Core Forecast Intelligence (Highest Impact)

**Goal:** Better inputs -> better optimization output, no UI changes required.

| Task | Files | Effort |
|------|-------|--------|
| Tiered MFRA forecast (Section 8.1) | `caiso_da.py`, `build_inputs.py`, `constants.py` | Medium |
| Time-decaying bias profile (Section 8.2) | `bias.py`, `build_inputs.py`, `constants.py` | Small |
| Unit tests for new functions | `tests/` (new) | Small |

### Phase 2: Confidence Bands

**Goal:** Operators see forecast uncertainty on the elevation chart.

| Task | Files | Effort |
|------|-------|--------|
| Extract quantile columns from Upstream API (Section 8.3) | `data_fetcher.py` | Small |
| Forward-sim with q10/q90 inputs | `confidence.py` (new), `build_inputs.py` | Medium |
| Store bands in OptimizationResult | `models.py`, `views.py`, `tasks.py` | Small |
| Display bands on elevation chart | `dashboard.js` | Medium |

### Phase 3: Forecast Tracking Dashboard

**Goal:** Operators can evaluate forecast performance over time.

| Task | Files | Effort |
|------|-------|--------|
| ForecastSnapshot model + population (Section 8.4A) | `models.py`, `tasks.py` | Medium |
| ForecastAccuracyLog model + background task (Section 8.4B) | `models.py`, `tasks.py` | Medium |
| Bias trend API + chart (Section 8.4C) | `views.py`, `dashboard.js` | Medium |
| Spaghetti plot API + chart (Section 8.4D) | `views.py`, `dashboard.js` | Medium |

### Phase 4: Enhanced Operator Tools

**Goal:** Operators can quickly adjust and compare scenarios.

| Task | Files | Effort |
|------|-------|--------|
| Live impact preview (Section 8.5A) | `dashboard.js` | Small |
| MFRA override workflow (Section 8.5B) | `dashboard.js`, `views.py` | Medium |
| Forecast deviation alerts (Section 8.5C) | `alerting.py`, `models.py` | Medium |
| Scenario save/compare (Section 8.5D) | `models.py`, `views.py`, `dashboard.js` | Large |

### Phase A/B/C/D: Instrumentation, Tracking UX, Robust Layer, Hardening

See `TASKS.md` for detailed backlog items and status tracking for these phases.

---

## 14. Files to Modify (Summary)

| File | Phase | Changes |
|------|-------|---------|
| `abay_opt/caiso_da.py` | 1 | Add `get_historical_mfra_pattern()` |
| `abay_opt/build_inputs.py` | 1, 2 | Tiered MFRA, decaying bias, quantile propagation |
| `abay_opt/bias.py` | 1 | Add `compute_decaying_bias_profile()` |
| `abay_opt/constants.py` | 1, 2 | New config constants (half-life, tier hours, lookback days) |
| `abay_opt/data_fetcher.py` | 2 | Extract quantile columns from Upstream API response |
| `abay_opt/confidence.py` (new) | 2 | Elevation band computation via forward simulation |
| `optimization_api/models.py` | 3, 4 | `ForecastSnapshot`, `ForecastAccuracyLog`, `OperatorScenario` |
| `optimization_api/views.py` | 3, 4 | New API endpoints for accuracy, scenarios |
| `optimization_api/tasks.py` | 3 | Snapshot population, accuracy background task |
| `optimization_api/alerting.py` | 4 | Forecast deviation alert type |
| `static/js/dashboard.js` | 2, 3, 4 | Confidence bands, bias trend, spaghetti plot, live preview |

---

## 15. Testing and Validation Strategy

Required test layers:
- **Unit tests**: Physics parity (optimizer vs recalc), provenance/confidence calculations, decaying bias math, tiered MFRA blending.
- **Integration tests**: End-to-end run -> persist -> reload -> compare, DA partial coverage and fallback, SMS/voice alert delivery (once Twilio live).
- **Historical replay/backtest**: Fixed benchmark periods with known dispatch shocks, baseline vs robust-layer comparisons, MAE comparison at 24h/48h/72h.
- **Operator acceptance tests**: Bias update workflow, manual override and scenario save/compare, alert receipt and acknowledgment.

---

## 16. Risks and Mitigations

- **Twilio API approval delayed** — Email and browser alerts are fully functional now. SMS/voice is additive.
- **Over-complicating optimization** — Keep deterministic MILP path as baseline; robust layer is additive and configurable.
- **Operator distrust** — Mandatory provenance + explainability cards per run.
- **DA feed gaps and timing variability** — Explicit freshness checks, fallback labeling, and alerting.
- **Drift between backend optimization and frontend recalc** — Shared physics helpers and parity test suite.

## 17. Open Questions

- What dispatch shock envelope should be the default for MFRA scenario stress tests?
- Should confidence scoring be rules-based only initially, or include statistical calibration?
- What minimum DA coverage should allow a run to be labeled "DA-driven" at run level?
- Do operators want one global bias control only, or component-level bias controls in the first release?

---

## Appendix A: Key Equations Reference

| Equation | Source | Used In |
|----------|--------|---------|
| `ABAY_AF = 0.6311303 * ft^2 - 1403.8 * ft + 780566` | `physics.py:9-11` | Stage-storage mapping |
| `OXPH_CFS = 163.73 * MW + 83` | `constants.py:98-99` | Water balance |
| `g_max = 0.0912 * H - 101.42` | `constants.py:114-115` | Head loss constraint |
| `MF12_MW = (MFRA - min(86, max(0, (R4-R5L)/10))) * 0.59` | `physics.py:80-81` | GEN mode reduction |
| `bias[t] = bias_24h * exp(-t * ln(2) / half_life)` | Section 8.2 | Decaying bias |

## Appendix B: Data Source Coverage

| Input | Source | Forecast Coverage | Confidence |
|-------|--------|-------------------|------------|
| R4 Flow | Upstream API (HydroForecast / CNRFC) | 7 days, with quantiles | High (days 1-2), Medium (days 3-7) |
| R30 Flow | Upstream API (HydroForecast / CNRFC) | 7 days, with quantiles | High (days 1-2), Medium (days 3-7) |
| MFRA MW | CAISO DA awards + tiered fallback | 1 day (DA), 2 days (blend), 4 days (pattern) | High -> Low |
| R20, R5L, R26 | Last observed (persistence) | Held constant | Low beyond 6h |
| Float setpoint | Operator-set PI tag | Held constant | N/A (operator decision) |
| Bias | 24h rolling average, decaying | Decays over horizon | High (hours 1-12), Low (hours 24+) |
