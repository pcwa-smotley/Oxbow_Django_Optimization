# PRD: ABAY Forecast Reliability and Operator Decision Support

## Document Control
- Version: 2.0
- Status: Draft for implementation planning
- Date: February 13, 2026
- Owner: Optimization + Operations (ABAY)
- Scope: `abay_opt/` optimization flow and Django operator workflow

## 1. Executive Summary
This PRD defines the next phase of ABAY optimization: keep the current MILP core, improve forecast robustness (especially around MDFK/MFRA uncertainty), and give operators clear tools to track forecast accuracy over time and adjust assumptions safely.

The key change from earlier phases is that day-ahead (DA) schedules are now available for MFRA. The system must use DA awards when available, fall back cleanly when coverage is partial, and make source/uncertainty visible to operators hour by hour.

## 2. Problem Statement
Current optimization logic produces useful schedules, but operators still need better confidence and control in three areas:
- Forecast volatility: unexpected MDFK real-time dispatch and river flow deviations can quickly invalidate a baseline schedule.
- Source transparency: MFRA may come from DA awards or persistence fallback, but operators need per-hour provenance and confidence, not a single run-level label.
- Tracking and adjustment loop: operators need to see how forecasts are aging versus actuals, what changed between runs, and how to apply bias/flow/dispatch overrides without losing auditability.

## 3. Current-State Assessment
### 3.1 What is working now
- `abay_opt/optimizer.py` solves a constrained schedule with:
  - ABAY storage/elevation physics via piecewise ft<->AF mapping.
  - Ramp limits and head limit constraints.
  - Rafting window setpoint/target handling.
  - Strong penalties for elevation bound violations.
- `abay_opt/build_inputs.py` now supports MFRA DA awards with persistence fallback.
- `abay_opt/bias.py` computes 24-hour signed bias and applies it to forecast net inflow.
- `abay_opt/recalc.py` supports forward recalculation from edited hours for operator interaction.
- Django persistence already stores runs and timeseries details (`OptimizationRun`, `OptimizationResult`).

### 3.2 Gaps to close
- Forecast confidence and source are not tracked per hour as first-class data.
- No explicit risk-reserve logic for unexpected MDFK dispatch shocks.
- Recalc/operator-simulation behavior must stay physically aligned with optimization behavior (ramp/head/limits parity).
- Forecast-vs-actual tracking across successive runs is not formalized as an operator workflow.
- Run-comparison UX/API needs a complete, supported contract.

## 4. Product Vision
Create an operator-first optimization system where each run is:
- Explainable: operators can see exactly which assumptions and data sources drove each hour.
- Trackable: operators can see how the run performed as actuals arrived.
- Adjustable: operators can safely apply bias, flow, or dispatch overrides and immediately see impact.
- Risk-aware: schedules include explicit protection against likely uncertainty events.

## 5. Goals and Non-Goals
### 5.1 Goals
- Improve ABAY forecast reliability under uncertain inflow and MDFK dispatch conditions.
- Reduce spill risk caused by late schedule response to dispatch/flow shocks.
- Give operators a full forecast lifecycle view: planned -> tracking -> adjusted -> saved scenario.
- Preserve current production workflow and avoid destabilizing the existing optimization engine.

### 5.2 Non-Goals
- Replacing the MILP solver with a completely different optimizer in Phase 1.
- Building fully autonomous dispatch without operator review.
- Introducing a new database platform (SQLite remains acceptable for current user scale).

## 6. Primary Users and Use Cases
### 6.1 Reservoir Operators
- Run forecast optimization for next 72 hours.
- See per-hour assumption provenance (DA vs persistence vs actual).
- Detect forecast drift and apply corrective bias/override adjustments.
- Save and compare scenarios.

### 6.2 Optimization Engineers
- Validate solver behavior versus recalc behavior.
- Analyze errors by source component.
- Tune risk settings (dispatch shock margin, bias behavior, smoothing priorities).

### 6.3 Operations Leadership
- Review reliability metrics (bound compliance, spill avoidance, forecast error).
- Audit why a run changed and who adjusted assumptions.

## 7. Functional Requirements

### FR-1: Forecast Source and Confidence Layer
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

### FR-2: Robust Optimization Enhancements (Keep MILP Core)
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

### FR-3: Forecast Tracking Over Time
Operators need an explicit "tracking" experience for each run.

Requirements:
- For each saved run, track forecast-versus-actual error as actuals arrive.
- Show tracking views at minimum horizons: +1h, +6h, +24h.
- Provide error decomposition views:
  - Bias component.
  - River forecast miss (R4/R30).
  - MDFK/MFRA dispatch miss.
  - Mode change impacts (GEN/SPILL transitions).
- Show "what changed" between two runs (inputs, bias, setpoints, resulting ABAY path).

Acceptance criteria:
- Operator can select two runs and view delta in ABAY, OXPH, MFRA assumptions, and spill risk.
- Tracking metrics persist and are queryable per run.

### FR-4: Adjustment Workflow (Bias + Overrides + Scenarios)
Adjustments must be fast, traceable, and physically consistent.

Requirements:
- Support:
  - Global bias updates (existing behavior).
  - Component-level bias overrides (MFRA-only, river-only, or custom).
  - Hourly overrides for MFRA, R4, R30, OXPH.
- Recalc from earliest edited hour forward with physics parity to optimization assumptions.
- Every adjustment save must include:
  - User, timestamp, changed fields, reason/note, parent run.

Acceptance criteria:
- Operator can apply an adjustment and see updated ABAY trajectory within the current session.
- Saved adjusted runs are auditable and reloadable.

### FR-5: DA Awards Operationalization
DA awards must move from optional fetch to dependable operational input.

Requirements:
- Add scheduled DA fetch job and status health indicator.
- Surface publish/fetch timestamps and coverage completeness.
- If DA unavailable or stale, degrade gracefully and alert operator.

Acceptance criteria:
- Operators can see whether DA awards are fresh enough for the active run.
- Missing/stale DA data triggers a visible warning and logs fallback behavior.

### FR-6: Alerting Additions for Forecast Integrity
Alerting must include forecast-quality and risk controls, not only threshold values.

Requirements:
- New alert types:
  - Forecast divergence exceeds threshold (e.g., ABAY actual vs forecast).
  - DA awards missing/stale near run time.
  - Elevated spill risk under scenario stress.
- Respect existing cooldown/channel settings.

Acceptance criteria:
- Alert can be configured per user and appears in existing alert channels.

## 8. UX Requirements

### 8.1 Tracking Panel
Add a dedicated operator panel (tab or dashboard section) that includes:
- Forecast age and confidence trend.
- Forecast vs actual ABAY line with divergence markers.
- Source provenance strip (DA/persistence/manual/actual).
- "What changed since last run" summary cards.

### 8.2 Scenario Workspace
Add a lightweight scenario workflow:
- Baseline run pinned.
- One-click branch to "Adjusted Scenario".
- Side-by-side chart/table compare for ABAY, OXPH, MFRA, risk metrics.

### 8.3 Operator Guidance
For each run, expose:
- Next critical setpoint action time.
- Risk explanation (e.g., "High MDFK uncertainty 10:00-14:00 PT").
- Suggested mitigation options (increase pre-ramp, apply temporary bias, override specific hours).

## 9. Technical Approach

### 9.1 Optimization Architecture
Use a staged method:
1. Deterministic MILP schedule (existing core).
2. Scenario stress evaluation against candidate schedule.
3. Optional re-solve with risk penalties/reserve targets if risk score exceeds threshold.
4. Persist full assumption and risk metadata with run.

### 9.2 Data/Model Additions
Add new persisted entities (names tentative):
- `ForecastAssumptionHour`: per-hour input value + provenance + confidence.
- `RunTrackingPoint`: per-hour forecast-vs-actual tracking metrics over elapsed time.
- `RunChangeLog`: structured input/output deltas between related runs.

### 9.3 API Additions/Normalization
Define and support stable endpoints for:
- Recent runs by user.
- Run comparison.
- Tracking metrics for a run.
- Forecast provenance summary for active run.

All endpoints must return UTC timestamps with explicit PT rendering guidance for UI.

## 10. Success Metrics

Operational metrics:
- Bound compliance: ABAY min/float violations per month.
- Spill performance: total spill AF and near-spill hours.
- Forecast quality: MAE/RMSE at +1h, +6h, +24h.
- Adjustment effectiveness: post-adjustment error reduction.

Adoption metrics:
- Percent of runs with provenance visible.
- Percent of operators using run comparison/tracking weekly.
- Time-to-decision after forecast divergence alert.

## 11. Phased Delivery Plan

### Phase A: Instrumentation and Provenance (Low Risk)
- Persist hourly source provenance/confidence.
- Add DA freshness/coverage indicators.
- Deliver run tracking skeleton (forecast vs actual trend).

Exit criteria:
- Every run records per-hour MFRA source and confidence.
- Dashboard shows DA coverage and freshness.

### Phase B: Tracking and Comparison UX
- Add tracking panel and run-vs-run diff views.
- Add missing/standardized recent-run and compare APIs.
- Add structured adjustment audit logging.

Exit criteria:
- Operators can compare two runs without manual export.
- Tracking metrics available for at least the latest 30 days of runs.

### Phase C: Robust Optimization Layer
- Implement dispatch/flow stress scenarios.
- Add reserve/risk penalty tuning in configuration.
- Add spill-risk score and mitigation hints.

Exit criteria:
- Historical replay shows measurable spill-risk reduction.
- Operators can inspect why risk-driven adjustments were recommended.

### Phase D: Hardening and Alert Integration
- Add forecast-integrity alert types.
- Backtest at scale and tune thresholds.
- Finalize operator playbook and runbook.

Exit criteria:
- Forecast divergence and DA-staleness alerts live with cooldown behavior.
- Production-ready monitoring + regression tests in place.

## 12. Testing and Validation Strategy

Required test layers:
- Unit tests:
  - Physics parity between optimizer and recalc.
  - Provenance/confidence calculations.
- Integration tests:
  - End-to-end run -> persist -> reload -> compare.
  - DA partial coverage and fallback behavior.
- Historical replay/backtest:
  - Fixed benchmark periods with known dispatch shocks.
  - Baseline vs robust-layer comparisons.
- Operator acceptance tests:
  - Bias update workflow.
  - Manual override and scenario save/compare workflow.

## 13. Risks and Mitigations
- Risk: Over-complicating optimization and harming reliability.
  - Mitigation: Keep deterministic MILP path as baseline; make robust layer additive and configurable.
- Risk: Operator distrust due to opaque adjustments.
  - Mitigation: Mandatory provenance + explainability cards per run.
- Risk: DA feed gaps and timing variability.
  - Mitigation: Explicit freshness checks, fallback labeling, and alerting.
- Risk: Drift between backend optimization and frontend recalc behavior.
  - Mitigation: Shared physics helpers and parity test suite.

## 14. Open Questions
- What dispatch shock envelope should be the default for MDFK scenario stress tests?
- Should confidence scoring be rules-based only in Phase A, or include statistical calibration immediately?
- What minimum DA coverage should allow a run to be labeled "DA-driven" at run level?
- Do operators want one global bias control only, or component-level bias controls in the first release?

## 15. Implementation Notes (Initial Recommendation)
- Recommendation: Do not replace the existing optimizer now. Build a robust layer around the current `build_inputs -> build_and_solve -> recalc` pipeline.
- Reason: Current solver already encodes key physical/operational constraints; the larger gap is forecast uncertainty management and operator decision support.

