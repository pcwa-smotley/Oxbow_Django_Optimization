# TASKS: ABAY Optimization Planning Backlog

## Planning Scope (as of February 13, 2026)
This file tracks planning + implementation status for the current cycle.

Priorities in this planning cycle:
- Convert Phase A and Phase B from `PRD.md` into concrete backlog items.
- Define and prioritize Data Table fixes needed for operator trust.

---

## Priority 0: Data Table Remediation (Operator-Critical)

### DT-1: Make ABAY Forecast Visible and Understandable in the Data Table
- Status: `completed` (pending operator UAT)
- Problem:
  - Operators cannot reliably see ABAY forecast in the table workflow.
  - `elevation` exists in table rows but visibility/layout is not operator-friendly.
- Planning tasks:
  - Define required columns and order so forecast ABAY elevation is always visible without horizontal hunting.
  - Decide whether to pin columns (`Date/Time`, `Setpoint`, `OXPH`, `ABAY Forecast`) on the left.
  - Add explicit column labels for `ABAY Forecast (ft)` and optional `ABAY Actual (ft)`.
  - Confirm behavior in full horizon scroll and on standard operator screen sizes.
- References:
  - `django_backend/static/js/dashboard.js:40`
  - `django_backend/static/js/dashboard.js:73`
  - `django_backend/static/js/dashboard.js:2338`
- Acceptance criteria:
  - Operator can see ABAY forecast elevation directly while editing setpoint/MFRA/R4/R30/R20.
  - Column is visible and readable on both desktop and laptop layouts.

### DT-2: Enforce Setpoint -> OXPH Physics Parity (Ramp + Head Limit)
- Status: `completed` (pending operator UAT)
- Problem:
  - Current table edits can set `OXPH (MW)` equal to setpoint directly.
  - This bypasses ramp-rate and head-pressure behavior operators expect.
- Planning tasks:
  - Remove direct assignment behavior from frontend edit path.
  - Define single source of truth for setpoint-to-generation translation:
    - Ramp rate from constants.
    - Head-limited cap based on ABAY elevation.
  - Require recalculation path to compute `OXPH_generation_MW` from setpoint changes using shared backend physics (`recalc_abay_path` and related helpers), not ad-hoc frontend approximations.
  - Ensure modal setpoint workflow uses same physics (replace hardcoded ramp assumptions).
- References:
  - `django_backend/static/js/dashboard.js:2538`
  - `django_backend/static/js/dashboard.js:3311`
  - `django_backend/static/js/dashboard.js:3325`
  - `abay_opt/recalc.py`
  - `abay_opt/constants.py`
- Acceptance criteria:
  - Changing setpoint updates OXPH according to ramp and head limit, not one-to-one equality.
  - Table, chart, and saved run values remain consistent after edits.

### DT-3: Correct Setpoint Change Timestamp Semantics
- Status: `completed` (pending operator UAT)
- Problem:
  - Setpoint-change time is being stamped too broadly (including ramp continuation hours).
  - Operators only want timestamp when setpoint value actually changes.
- Planning tasks:
  - Define rule: show timestamp only on row(s) where setpoint command changes.
  - Ensure ramp-only generation changes do not create new setpoint-change timestamps.
  - Align table behavior with run output semantics used elsewhere in the pipeline.
- References:
  - `django_backend/static/js/dashboard.js:3335`
  - `django_backend/static/js/dashboard.js:2680`
  - `abay_opt/cli.py`
- Acceptance criteria:
  - If setpoint is changed at 07:44 and only ramp continues through 08:00, 08:00 row has no setpoint-change timestamp.
  - Timestamp appears only at true setpoint command transitions.

### DT-4: Add R20 Forecast Editing Support
- Status: `completed` (pending operator UAT)
- Problem:
  - Operator requirement includes R20 forecast editing, but current editable fields omit R20.
- Planning tasks:
  - Add `r20` to editable table schema and validation config.
  - Ensure recalculation and persistence paths include updated R20 values.
  - Confirm edited R20 values propagate to chart and save-edited run payload.
- References:
  - `django_backend/static/js/dashboard.js:86`
  - `django_backend/static/js/dashboard.js:1144`
  - `django_backend/static/js/dashboard.js:3085`
- Acceptance criteria:
  - Operator can edit R20 in table and immediately see ABAY forecast impact.

### DT-5: Data Table Regression Test Plan
- Status: `in_progress`
- Planning tasks:
  - Add backend tests for recalc parity when setpoint is edited across multiple hours.
  - Add frontend test cases/manual scripts for column visibility and timestamp semantics.
  - Add scenario-based acceptance tests with known expected results.
- Acceptance criteria:
  - Test plan explicitly covers DT-1 through DT-4 before release.

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
- Problem:
  - UI expects recent-run endpoints that are not fully aligned/implemented.
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

## Immediate Next Planning Session (Proposed)
1. Confirm DT-1 through DT-4 acceptance criteria with operators.
2. Finalize API contracts for B-1 before any frontend implementation.
3. Decide whether table recalculation should always call backend or support a validated local fallback mode.

