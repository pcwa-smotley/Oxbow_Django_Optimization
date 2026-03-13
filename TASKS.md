# TASKS: ABAY Optimization Planning Backlog

## Planning Scope (as of March 12, 2026)
This file tracks planning + implementation status for the current cycle.

Current priorities:
- RT dispatch monitoring — build DA vs RT comparison engine (RT-1) and integrate dispatch spike alerts (RT-2).
- Convert Phase A and Phase B from `PRD.md` into concrete backlog items.
- Continue regression testing for data table remediation (DT-5).

---

## Completed: UI Overhaul (February 2026)

All items below were completed during the Feb 2026 sprint and are in production on the `sandbox` branch.

### UI-1: Chart Library Migration (Chart.js -> Apache ECharts 5)
- Status: `completed`
- Scope:
  - Replaced all `<canvas>` elements with `<div>` containers.
  - Registered custom themes (`oxbow-light`, `oxbow-dark`) in `echart-theme.js`.
  - Synced Elevation + OXPH charts via `echarts.connect('dashboardSync')`.
  - Added DataZoom sliders, day dividers, smooth animations.
- Files: `dashboard.html`, `dashboard.js`, `echart-theme.js` (new), `dashboard.css`

### UI-2: Neon Control Room Theme
- Status: `completed`
- Scope:
  - Dark mode with glassmorphism cards, animated mesh gradient background.
  - Accent palette: cyan `#00d4ff`, magenta `#ff006e`, lime `#00ff88`, amber `#ffbe0b`.
  - Background: deep navy `#0a0e1a`.
- Files: `dashboard.css`, `dashboard.html`

### UI-3: KPI Gauge Strip
- Status: `completed`
- Scope: Five animated ECharts gauges (ABAY Elevation, OXPH Output, Spill Risk, Revenue Rate, Forecast Confidence).
- Files: `dashboard.js`

### UI-4: System Schematic
- Status: `completed`
- Scope: Animated SVG water flow diagram with particle animations showing real-time flow through MFRA, R30, R4, ABAY, OXPH, Spillway.
- Files: `system-schematic.js` (new), `dashboard.html`

### UI-5: Command Palette & Boot Sequence
- Status: `completed`
- Scope: Ctrl+K quick-action palette with fuzzy search, keyboard shortcuts (1-8 for tabs, D for dark mode, ? for help). Cinematic boot sequence on first visit.
- Files: `command-palette.js` (new), `dashboard.html`

### UI-6: 7-Day Operations Timeline
- Status: `completed`
- Scope: Bar chart overview of OXPH setpoints with rafting window highlights and day boundaries.
- Files: `dashboard.js`

### UI-7: Smart Alert Toasts
- Status: `completed`
- Scope: Slide-in notifications with severity icons, audio chimes for critical alerts, stacking with overflow badge.
- Files: `auth-alerts.js`

### UI-8: MFRA Source Indicator
- Status: `completed`
- Scope: Badge showing DA Awards (green) vs Persistence (amber) source, plus "Fetch DA Awards" button on power chart.
- Files: `dashboard.js`, `dashboard.html`

---

## Completed: Data Table Remediation (Operator-Critical)

### DT-1: Make ABAY Forecast Visible and Understandable in the Data Table
- Status: `completed`
- Operator can see ABAY forecast elevation directly while editing setpoint/MFRA/R4/R30/R20.
- Column is visible and readable on desktop and laptop layouts.

### DT-2: Enforce Setpoint -> OXPH Physics Parity (Ramp + Head Limit)
- Status: `completed`
- Changing setpoint updates OXPH according to ramp and head limit, not one-to-one equality.
- Table, chart, and saved run values remain consistent after edits.

### DT-3: Correct Setpoint Change Timestamp Semantics
- Status: `completed`
- Timestamp appears only at true setpoint command transitions; ramp-only hours do not generate timestamps.

### DT-4: Add R20 Forecast Editing Support
- Status: `completed`
- Operator can edit R20 in table and immediately see ABAY forecast impact.

### DT-5: Data Table Regression Test Plan
- Status: `in_progress`
- Planning tasks:
  - Add backend tests for recalc parity when setpoint is edited across multiple hours.
  - Add frontend test cases/manual scripts for column visibility and timestamp semantics.
  - Add scenario-based acceptance tests with known expected results.
- Acceptance criteria:
  - Test plan explicitly covers DT-1 through DT-4 before release.

### DT-6: Blinking Dot on Current Data Row
- Status: `completed`
- Visual indicator on the data table row corresponding to the current hour.

---

## Completed: SMS/Voice Alert Deployment via Twilio (March 2026)

### TWILIO-1: Obtain Twilio API Approval
- Status: `completed` (approved March 2026)
- Twilio credentials configured in `abay_opt/config/` and loaded via `settings.py`.
- SMS and voice delivery verified end-to-end.

### TWILIO-2: Production Alert Rollout
- Status: `completed` (March 2026)
- Delivered:
  - Dashboard **Alerts tab** with full CRUD for all threshold types: flows (R4, R11, R30), Afterbay elevation (high/low), OXPH deviation, rafting ramp, MF RT vs DA deviation, ABAY forecast deviation.
  - **Re-arm/hysteresis logic**: `is_armed` field on `AlertThreshold` — alerts fire once on threshold crossing, disarm, then re-arm only after value returns to safe zone.
  - **Test notification system** accessible from Alerts tab (SMS, email, voice, browser).
  - **Alert history** panel with severity and notification channel indicators.
  - `monitor_alerts` management command for polling PI data and checking thresholds (no Celery/Redis required).
- Acceptance criteria met:
  - Operators receive SMS alerts on threshold violation.
  - Alert logs are persisted and queryable in the dashboard.

### TWILIO-3: Forecast Deviation Alerts
- Status: `completed` (March 2026)
- Implemented:
  - `_check_abay_forecast_deviation_alert()` in `alerting.py` — compares actual PI elevation against latest `OptimizationResult` forecast.
  - `_check_mf_rt_vs_da_alert()` in `alerting.py` — compares live PI MFRA power against `CAISODAAwardSummary` for current hour.
  - Both alert types use re-arm/hysteresis logic and fire through all configured channels.
  - Configurable from the dashboard Alerts tab under "ABAY Forecast Deviation" and "MF RT vs DA Monitoring" sections.

---

## Priority 1: Real-Time Dispatch Monitoring & Alerting

### RT-1: DA vs RT Dispatch Comparison Engine
- Status: `planned`
- Context:
  - CAISO CMRI API confirmed working for both DAM and RTM awards (tested 2/17/2026).
  - Resources confirmed: `MDFKRL_2_PROJCT`, `OXBOW_6_DRUM`, `FMEADO_6_HELLHL`, `FMEADO_7_UNIT`.
  - RT awards (FMM, 15-min granularity) already accessible via `caiso_api.fetch_rt_awards()`.
  - On 2/17/2026: DA cleared 40 MW for MDFKRL, RT dispatched up to 105 MW — confirming RT pickup above DA does occur.
- Tasks:
  - Build a periodic RT award poller that compares current RT dispatch vs DA award for each hour.
  - Compute delta: `RT_dispatch - DA_award` per resource per interval.
  - Store RT dispatch snapshots for historical analysis.
- Acceptance criteria:
  - System can detect when RT dispatch exceeds DA award within 15 minutes of FMM clearing.

### RT-2: RT Dispatch Spike Alert
- Status: `planned`
- Context:
  - Example scenario: HE 2 has 50 MW DA award. RT bids are structured as -$100 for 0-50 MW (must-run) and $60 for 51-210 MW. If RT price spikes above $60, the full 210 MW is dispatched — operators should be alerted.
  - Conversely, if RT price drops below -$100 (negative price), the unit is dispatched to 0 MW — also worth alerting.
- Tasks:
  - Define alert triggers:
    - **Upward dispatch**: RT dispatch > DA award + configurable threshold (e.g., > 20 MW above DA).
    - **Curtailment**: RT dispatch = 0 MW when DA award > 0 (negative price curtailment).
    - **Price spike**: RT LMP exceeds configurable threshold at resource PNode.
  - Integrate with existing `AlertingService` in `alerting.py` (SMS/voice once Twilio live, browser/email now).
  - Include in alert message: resource name, DA award MW, RT dispatch MW, current RT LMP, estimated revenue impact.
- Acceptance criteria:
  - Operators receive alerts within minutes of RT dispatch deviating significantly from DA schedule.
  - Alert messages include actionable context (MW delta, price, revenue impact estimate).

### RT-3: RT Market Data Dashboard Panel
- Status: `planned`
- Tasks:
  - Add a dashboard panel showing DA award vs RT dispatch side-by-side per resource.
  - Overlay RT LMP on the chart to visualize price-dispatch correlation.
  - Color-code intervals where RT dispatch exceeds DA (green = extra revenue opportunity, red = negative price curtailment).
- Acceptance criteria:
  - Operators can visually identify RT dispatch deviations without leaving the dashboard.
  - Panel updates at FMM cadence (every 15 minutes).

### RT-4: SIBR Bid Curve Retrieval (Future)
- Status: `planned`
- Context:
  - CAISO uses SIBR (not CMRI) for bid submission/retrieval: `retrieveCurrentBidResults` and `retrieveCleanBidSet` endpoints.
  - Access to submitted bid curves (price/quantity segments) would enable predictive alerts: "RT price is approaching your $60 bid segment, dispatch increase likely."
  - Requires SIBR API access investigation via CAISO Developer Portal.
- Tasks:
  - Research SIBR API access and authentication requirements.
  - Build bid curve retrieval and storage.
  - Implement predictive dispatch alert based on real-time price vs bid curve segments.
- Acceptance criteria:
  - System can retrieve and display submitted bid curves alongside awards.
  - Predictive alerts fire before actual dispatch changes when possible.

---

## Phase A: Instrumentation and Provenance

### A-1: Persist Per-Hour Forecast Provenance
- Status: `pending`
- Tasks:
  - Define persistence model for per-hour assumption source and confidence.
  - Add provenance population in optimization pipeline.
  - Include MFRA source type at hour level (`da_awards`, `persistence`, `actual`, `manual_override`).
- Acceptance criteria:
  - Every forecast hour in a run includes source metadata.

### A-2: DA Awards Freshness and Coverage Signals
- Status: `pending`
- Tasks:
  - Define freshness/coverage rules and thresholds.
  - Expose freshness + coverage in API and run metadata.
  - Add dashboard indicator behavior for stale/missing/partial DA.
- Acceptance criteria:
  - Operators can tell whether DA input is fresh and complete for active run.

### A-3: Run Tracking Skeleton (Forecast vs Actual)
- Status: `pending`
- Tasks:
  - Define minimal tracking schema and API contract.
  - Add first-pass tracking view for ABAY forecast vs actual.
  - Include lead-time framing (+1h, +6h, +24h).
- Acceptance criteria:
  - Latest run includes baseline forecast tracking record and UI view.

### A-4: Phase A Test Plan
- Status: `pending`
- Tasks:
  - Unit tests for provenance and confidence calculations.
  - Integration tests for DA fallback + provenance labels.
- Acceptance criteria:
  - Automated tests validate source labeling and fallback behavior.

---

## Phase B: Tracking and Comparison UX

### B-1: Recent Runs and Compare API Contract
- Status: `pending`
- Tasks:
  - Define and implement supported endpoints for recent runs by user and run comparison.
  - Ensure response contracts are stable and documented.
- Acceptance criteria:
  - Run history modal can load users/runs and compare runs without client-side workarounds.

### B-2: Tracking Panel UX
- Status: `pending`
- Tasks:
  - Add forecast-age and divergence views.
  - Add per-hour provenance strip and summary cards.
- Acceptance criteria:
  - Operator can inspect tracking and divergence without leaving dashboard.

### B-3: Adjustment Audit Trail
- Status: `pending`
- Tasks:
  - Define structured audit log for manual adjustments (who, when, what changed, reason).
  - Persist linkage between adjusted run and source run.
- Acceptance criteria:
  - Every manual adjustment is auditable and queryable.

### B-4: Phase B Validation
- Status: `pending`
- Tasks:
  - End-to-end validation: run -> edit -> save -> reload -> compare.
  - Manual operator UAT script for compare workflow.
- Acceptance criteria:
  - Operators can reliably compare baseline and adjusted scenarios.

---

## Future: Forecast Intelligence Improvements (from PRD.md Section 8)

These items are defined in detail in `PRD.md` Section 8 (Technical Specifications) and will be scheduled after Phase A/B and Twilio deployment.

### FI-1: Tiered MFRA Forecast Strategy
- Status: `planned`
- Three-tier approach: DA awards (hours 1-24), blended DA-to-historical (25-48), historical hourly pattern (49+).
- See `PRD.md` Section 8.1 for full specification.

### FI-2: Time-Decaying Bias Profile
- Status: `planned`
- Exponential decay with configurable half-life (default 12h) replacing flat 24h bias.
- See `PRD.md` Section 8.2 for full specification.

### FI-3: Elevation Confidence Bands (q10/q90)
- Status: `planned`
- Propagate Upstream API quantiles through water balance for uncertainty visualization.
- See `PRD.md` Section 8.3 for full specification.

### FI-4: Forecast Tracking Dashboard
- Status: `planned`
- Snapshot storage, accuracy metrics, bias trend chart, spaghetti plot.
- See `PRD.md` Section 8.4 for full specification.

---

## Cross-Cutting Planning Items

### C-1: Physics Parity Contract (Optimizer vs Recalc vs Table)
- Status: `pending`
- Tasks:
  - Document shared assumptions and formulas for ramp/head constraints.
  - Identify all duplicate logic currently in frontend and backend.
  - Define a single authoritative computation path for operator edits.
- Acceptance criteria:
  - No contradictory OXPH/ABAY results between solver outputs and table recalc.

### C-2: Release Gating Criteria
- Status: `pending`
- Tasks:
  - Define launch gates for Data Table remediation and Phase A/B readiness.
  - Include rollback and feature-flag strategy.
- Acceptance criteria:
  - Release checklist exists and is used before deployment.

---

## Immediate Next Steps
1. Complete DT-5 regression test plan to validate data table remediation.
2. **RT dispatch monitoring** — build DA vs RT comparison engine (RT-1) and integrate dispatch spike alerts (RT-2) with existing alerting backend.
3. Begin Phase A-1 (forecast provenance) once table regression tests pass.
4. Finalize API contracts for B-1 before any frontend implementation.
