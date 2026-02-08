# Bias-Friendly UI & Alerting Plan

# Startup Familiarization Tasks

Use this checklist at the beginning of each session to stay aligned with the current project needs.

## Immediate Follow-Ups
- Bias recalculation remains incorrect: changing the bias value must properly adjust historical and forecast expected elevations based on the delta from the previously applied bias.
- Alerting experience is incomplete: enhance the dashboard alerting section so it is fully functional and backed by working server-side logic.
- Parameter persistence gap: updates made on the Parameters tab are not reaching the backend and therefore are not influencing subsequent optimization runs.

## Goals
- Enable operators to compare actual vs expected ABAY levels.
- Let users apply a constant bias to net inflow and see its effect immediately.
- Integrate the bias controls with existing optimization logic and alerting.

## Milestones
1. **Bias Adjustment Panel**
   - Numeric input or slider for constant bias (cfs).
   - “Apply bias” button recalculates ABAY path using `recalc_abay_path`.
   - Reflect the bias in the elevation chart (“Bias Corrected Expected” line).

2. **Actual vs Expected Diagnostic View**
   - 24‑hour lookback grid: actual vs expected inflow components.
   - Plot the difference (bias) alongside forecast (`elevationChart` legend already includes a slot for this line)​:codex-file-citation[codex-file-citation]{line_range_start=91 line_range_end=116 path=django_backend/templates/dashboard.html git_url="https://github.com/pcwa-smotley/Oxbow_Django_Optimization/blob/master/django_backend/templates/dashboard.html#L91-L116"}​.
   - Use `compute_bias_cfs_24h` to auto-suggest bias based on recent data​:codex-file-citation[codex-file-citation]{line_range_start=6 line_range_end=20 path=abay_opt/bias.py git_url="https://github.com/pcwa-smotley/Oxbow_Django_Optimization/blob/master/abay_opt/bias.py#L6-L20"}​.

3. **Editable Forecast Table**
   - Allow inline edits for river flows, MFRA, and OXPH.
   - On change, call `recalc_abay_path` with overrides (column timestamp edits)​:codex-file-citation[codex-file-citation]{line_range_start=1 line_range_end=53 path=abay_opt/recalc.py git_url="https://github.com/pcwa-smotley/Oxbow_Django_Optimization/blob/master/abay_opt/recalc.py#L1-L53"}​.
   - “Save as new optimization” persists the modified run.

4. **Alert Integration**
   - Add bias thresholds to alert settings.
   - If |bias| exceeds a user-defined limit, trigger an alert via existing alerting modules.

## Testing
- `python manage.py test` (full suite)
- Manual bias adjustments: verify chart updates and alerts fire when thresholds crossed.
