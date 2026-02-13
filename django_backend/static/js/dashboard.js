// django_backend/static/js/dashboard.js

// Global variables
let elevationChart, oxphChart, historicalChart;
let powerChartMode = "oxph";
let latestChartData = null;
let forecastData = [];
let originalData = [];
let currentOptimizationData = null;

let currentRunId = null;
let currentRunDetails = null;
let forecastDirty = false;
let priceChart;
let currentPriceData = null;
let editingRowIndex = null;
let lastFocusedElement = null;
let runHistoryUsers = [];
let recentRunLookup = {};
let selectedRunId = null;
let runUsersLoaded = false;
let pendingSetpointChange = null;
let currentRaftingData = null;
let currentBiasValue = null;
let actualsApplied = false;
let forecastHot = null;
let suppressForecastTableChange = false;
let forecastTableActualCount = 0;

function markForecastDirty(forceValue) {
  if (typeof forceValue === "boolean") {
    forecastDirty = forceValue;
  } else {
    forecastDirty = detectForecastChanges();
  }
  updateSaveButtons();
}

const FORECAST_TABLE_HEADERS = [
    'Date/Time', 'Setpoint', 'OXPH (MW)', 'OXPH Actual', 'Setpoint Change',
    'MFRA Forecast', 'MFRA Actual',
    'R4 Forecast', 'R4 Actual', 'R30 Forecast', 'R30 Actual', 
    'R20 Forecast', 'R5L Forecast', 'R26 Forecast', 
    'Abay Elevation'
];

const FORECAST_TABLE_COLUMNS = [
  {
    data: "datetime",
    type: "text",
    readOnly: true,
    width: 170,
    renderer: forecastDateTimeRenderer,
  },
  { data: "setpoint", type: "numeric", numericFormat: { pattern: "0.0" } },
  { data: "oxph", type: "numeric", numericFormat: { pattern: "0.0" }},
  { data: "oxphActual", type: "numeric", numericFormat: { pattern: "0.0" }, readOnly: true },
  { 
    data: "setpointChange", 
    type: "text", 
    readOnly: true,
    renderer: forecastTableSetpointChangeRenderer
  },
  { data: "mfra", type: "numeric", numericFormat: { pattern: "0,0" } },
{ data: "mfraActual", type: "numeric", numericFormat: { pattern: "0,0" }, readOnly: true },
{ data: "r4", type: "numeric", numericFormat: { pattern: "0,0" } },
{ data: "r4Actual", type: "numeric", numericFormat: { pattern: "0,0" }, readOnly: true },
{ data: "r30", type: "numeric", numericFormat: { pattern: "0,0" } },
{ data: "r30Actual", type: "numeric", numericFormat: { pattern: "0,0" }, readOnly: true },
{ data: "r20", type: "numeric", numericFormat: { pattern: "0,0" } },
{ data: "r5l", type: "numeric", numericFormat: { pattern: "0,0" } },
{ data: "r26", type: "numeric", numericFormat: { pattern: "0,0" } },
  { data: "elevation", type: "numeric", numericFormat: { pattern: "0,0.0" }, readOnly: true },
];

const PACIFIC_TIMEZONE = "America/Los_Angeles";
const RUN_HISTORY_LIMIT = 5;

const EDITABLE_FIELD_CONFIG = Object.freeze({
  setpoint: { decimals: 1, step: "0.1", min: 0, max: 6 },
  mfra: { decimals: 0, step: "1", min: 0 },
  r4: { decimals: 0, step: "10", min: 0 },
  r30: { decimals: 0, step: "10", min: 0 },
});

const FORECAST_TABLE_EDITABLE_FIELDS = new Set(['setpoint', 'mfra', 'r4', 'r30']);

const EDITABLE_FIELD_LABELS = Object.freeze({
  setpoint: "OXPH Setpoint",
  mfra: "MFRA Forecast",
  r4: "R4 Forecast",
  r30: "R30 Forecast"
});

const TABLE_DATE_TIME_FORMATTER = new Intl.DateTimeFormat("en-US", {
  timeZone: PACIFIC_TIMEZONE,
  month: "short",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  hour12: true,
});

const TABLE_DAY_FORMATTER = new Intl.DateTimeFormat("en-US", {
  timeZone: PACIFIC_TIMEZONE,
  weekday: "short",
});

const TABLE_MONTH_DAY_FORMATTER = new Intl.DateTimeFormat("en-US", {
  timeZone: PACIFIC_TIMEZONE,
  month: "short",
  day: "numeric",
});

const TABLE_TIME_FORMATTER = new Intl.DateTimeFormat("en-US", {
  timeZone: PACIFIC_TIMEZONE,
  hour: "2-digit",
  minute: "2-digit",
  hour12: true,
});

// ECharts helper - day divider markLines
function buildDayDividers(labels) {
  if (!Array.isArray(labels)) return [];
  const lines = [];
  labels.forEach(function (label, index) {
    var parts = (label || '').split(', ');
    if (parts[1] && parts[1].startsWith('00')) {
      lines.push({ xAxis: index, lineStyle: { color: 'rgba(128,128,128,0.25)', width: 2 } });
    }
  });
  return lines;
}

// ECharts helper - destroy chart safely
function destroyEChart(chartInstance) {
  if (chartInstance && typeof chartInstance.dispose === 'function') {
    chartInstance.dispose();
  }
  return null;
}

const ABAY_MATH = Object.freeze({
  A_COEF: 0.6311303,
  B_COEF: -1403.8,
  C_COEF: 780566.0,
  AF_PER_CFS_HOUR: 3600.0 / 43560.0,
  OXPH_MW_TO_CFS_FACTOR: 163.73,
  OXPH_MW_TO_CFS_OFFSET: 83.0,
  MFRA_MW2_TO_CFS_FACTOR: 0.00943,
  MFRA_MW_TO_CFS_FACTOR: 5.6653,
  MFRA_MW_TO_CFS_OFFSET: 18.54,
});

function toFiniteNumber(value) {
  if (value === null || value === undefined) return null;
  const num = Number(value);
  return Number.isFinite(num) ? num : null;
}

function toRoundedInteger(value) {
  const num = toFiniteNumber(value);
  return num === null ? null : Math.round(num);
}

function abayFeetToAf(ft) {
  const numeric = toFiniteNumber(ft);
  if (numeric === null) return null;
  const { A_COEF, B_COEF, C_COEF } = ABAY_MATH;
  return A_COEF * numeric * numeric + B_COEF * numeric + C_COEF;
}

function abayAfToFeet(af) {
  const numeric = toFiniteNumber(af);
  if (numeric === null) return null;
  const { A_COEF, B_COEF, C_COEF } = ABAY_MATH;
  const a = A_COEF;
  const b = B_COEF;
  const c = C_COEF - numeric;
  const disc = Math.max(0, b * b - 4 * a * c);
  return (-b + Math.sqrt(disc)) / (2 * a);
}

function oxphCfsFromMw(mw) {
  const numeric = toFiniteNumber(mw) ?? 0;
  return (
    ABAY_MATH.OXPH_MW_TO_CFS_FACTOR * numeric + ABAY_MATH.OXPH_MW_TO_CFS_OFFSET
  );
}

function normalizeModeValue(mode) {
  if (mode === null || mode === undefined) return null;
  if (typeof mode === "number") {
    return mode >= 0.5 ? "SPILL" : "GEN";
  }
  const str = String(mode).trim().toUpperCase();
  if (str === "SPILL" || str === "GEN") return str;
  if (str === "1") return "SPILL";
  if (str === "0") return "GEN";
  const parsed = Number(str);
  if (Number.isFinite(parsed)) {
    return parsed >= 0.5 ? "SPILL" : "GEN";
  }
  return null;
}

function mf12MwFromMfra(mfraMw, r4Cfs, r5lCfs, mode) {
  const mfra = toFiniteNumber(mfraMw) ?? 0;
  const r4 = toFiniteNumber(r4Cfs) ?? 0;
  const r5l = toFiniteNumber(r5lCfs) ?? 0;
  const normalizedMode = normalizeModeValue(mode) || "GEN";
  const reduction = Math.min(86.0, Math.max(0.0, (r4 - r5l) / 10.0));
  const base = (mfra - reduction) * 0.59;
  const spill = mfra * 0.59;
  return normalizedMode === "SPILL" ? Math.max(0, spill) : Math.max(0, base);
}

function mf12CfsFromMw(mw) {
  const numeric = Math.max(0, toFiniteNumber(mw) ?? 0);
  return (
    ABAY_MATH.MFRA_MW2_TO_CFS_FACTOR * numeric * numeric +
    ABAY_MATH.MFRA_MW_TO_CFS_FACTOR * numeric +
    ABAY_MATH.MFRA_MW_TO_CFS_OFFSET
  );
}

function regulatedComponentCfs(mf12Cfs, r4Cfs, r5lCfs) {
  const mf = toFiniteNumber(mf12Cfs) ?? 0;
  const r4 = toFiniteNumber(r4Cfs) ?? 0;
  const r5l = toFiniteNumber(r5lCfs) ?? 0;
  const term1 = Math.min(886.0, mf + r4 - r5l);
  const term2 = Math.max(0.0, r4 - r5l);
  return Math.max(term1, term2);
}

function computeNetAbayCfs(inputs) {
  const {
    r30 = 0,
    r4 = 0,
    r20 = 0,
    r5l = 0,
    r26 = 0,
    oxph = 0,
    mfra = 0,
    mode = null,
  } = inputs || {};

  const normalizedMode = normalizeModeValue(mode) || "GEN";
  const mf12Mw = mf12MwFromMfra(mfra, r4, r5l, normalizedMode);
  const mf12Cfs = mf12CfsFromMw(mf12Mw);
  const oxphCfs = oxphCfsFromMw(oxph);

  const base =
    (toFiniteNumber(r30) ?? 0) +
    (toFiniteNumber(r4) ?? 0) +
    ((toFiniteNumber(r20) ?? 0) - (toFiniteNumber(r5l) ?? 0)) -
    (toFiniteNumber(r26) ?? 0);

  if (normalizedMode === "SPILL") {
    return base + mf12Cfs - oxphCfs;
  }

  const regulated = regulatedComponentCfs(mf12Cfs, r4, r5l);
  return base + regulated - oxphCfs;
}

function resolveRowMode(row) {
  if (!row || typeof row !== "object") return "GEN";
  const actual = normalizeModeValue(row.modeActual ?? row.mode_actual);
  if (actual) return actual;
  const forecast = normalizeModeValue(row.mode);
  if (forecast) return forecast;
  return "GEN";
}

function chooseFlowValue(row, actualKey, forecastKey) {
  if (!row || typeof row !== "object") return 0;
  const actual = actualKey ? toFiniteNumber(row[actualKey]) : null;
  if (actual !== null) return actual;
  const forecast = forecastKey ? toFiniteNumber(row[forecastKey]) : null;
  return forecast !== null ? forecast : 0;
}

function getBiasForRow(row) {
  if (!row || typeof row !== "object") {
    return Number.isFinite(currentBiasValue) ? currentBiasValue : null;
  }
  const direct = toFiniteNumber(
    row.biasCfs ?? row.bias_cfs ?? row.additionalBias ?? row.additional_bias
  );
  if (direct !== null) return direct;
  return Number.isFinite(currentBiasValue) ? currentBiasValue : null;
}

function deriveBiasFromChartData(chartData, summaryBias = null) {
  if (!chartData || typeof chartData !== "object") {
    const fallback = toFiniteNumber(summaryBias);
    return fallback !== null ? fallback : null;
  }

  const forecastRows = Array.isArray(chartData.forecast_data)
    ? chartData.forecast_data
    : [];
  const actualMask = Array.isArray(chartData.actual_mask)
    ? chartData.actual_mask
    : [];

  const isActualRow = (index) => {
    if (!actualMask.length || index >= actualMask.length) {
      return false;
    }
    const value = actualMask[index];
    if (value === true || value === false) {
      return value;
    }
    if (typeof value === "number") {
      return value !== 0;
    }
    if (typeof value === "string") {
      const normalized = value.trim().toLowerCase();
      return normalized === "true" || normalized === "1";
    }
    return Boolean(value);
  };

  const extractBiasFromIndices = (indices) => {
    for (const idx of indices) {
      if (idx < 0 || idx >= forecastRows.length) continue;
      const row = forecastRows[idx] || {};
      const candidate = toFiniteNumber(
        row.bias_cfs ?? row.additional_bias ?? row.biasCfs ?? row.additionalBias
      );
      if (candidate !== null) {
        return candidate;
      }
    }
    return null;
  };

  if (forecastRows.length) {
    const forecastIndices = [];
    for (let i = 0; i < forecastRows.length; i++) {
      if (!isActualRow(i)) {
        forecastIndices.push(i);
      }
    }

    const forecastBias = extractBiasFromIndices(forecastIndices);
    if (forecastBias !== null) {
      return forecastBias;
    }

    const anyBias = extractBiasFromIndices(forecastRows.map((_, idx) => idx));
    if (anyBias !== null) {
      return anyBias;
    }
  }

  const fallback = toFiniteNumber(summaryBias);
  return fallback !== null ? fallback : null;
}

// Initialize the application
document.addEventListener("DOMContentLoaded", function () {
  // Safety check for formatters (in case of loading issues)
  if (typeof TABLE_TIME_FORMATTER === 'undefined') {
      console.warn("TABLE_TIME_FORMATTER missing, defining fallback");
      window.TABLE_TIME_FORMATTER = new Intl.DateTimeFormat("en-US", {
          timeZone: "America/Los_Angeles",
          hour: "2-digit",
          minute: "2-digit",
          hour12: true,
      });
  }
  if (typeof TABLE_DAY_FORMATTER === 'undefined') {
      window.TABLE_DAY_FORMATTER = new Intl.DateTimeFormat("en-US", {
          timeZone: "America/Los_Angeles",
          weekday: "short",
      });
  }
  if (typeof TABLE_MONTH_DAY_FORMATTER === 'undefined') {
      window.TABLE_MONTH_DAY_FORMATTER = new Intl.DateTimeFormat("en-US", {
          timeZone: "America/Los_Angeles",
          month: "short",
          day: "numeric",
      });
  }
  if (typeof TABLE_DATE_TIME_FORMATTER === 'undefined') {
      window.TABLE_DATE_TIME_FORMATTER = new Intl.DateTimeFormat("en-US", {
          timeZone: "America/Los_Angeles",
          month: "short",
          day: "2-digit",
          hour: "2-digit",
          minute: "2-digit",
          hour12: true,
      });
  }

  initializeCharts();
  initializePriceChart();
  setupLegends();
  initializeForecastTable();
  loadLatestResults();
  setDefaultDates();
  initializeRunHistoryModal();
  updateSaveButtons();
  updateActiveRunInfo();
  
  // Sidebar Toggle
  const sidebarToggle = document.getElementById('sidebarToggle');
  if (sidebarToggle) {
      sidebarToggle.addEventListener('click', toggleSidebar);
  }

  // Mobile Menu
  const mobileMenuBtn = document.getElementById('mobileMenuBtn');
  if (mobileMenuBtn) {
      mobileMenuBtn.addEventListener('click', () => {
          document.querySelector('.sidebar').classList.toggle('mobile-open');
      });
  }

  if (typeof refreshRaftingTimes === "function") {
    setTimeout(() => refreshRaftingTimes(), 500);
  }
  showNotification("Dashboard initialized successfully", "success");
});

function toggleSidebar() {
    const sidebar = document.querySelector('.sidebar');
    sidebar.classList.toggle('collapsed');
    
    // Trigger resize events for charts and tables after transition
    setTimeout(() => {
        if (elevationChart) elevationChart.resize();
        if (oxphChart) oxphChart.resize();
        if (priceChart) priceChart.resize();
        if (timelineChart) timelineChart.resize();
        if (forecastHot) forecastHot.render();
    }, 300);
}

// Run history modal and loading previous optimizations
function initializeRunHistoryModal() {
  const userSelect = document.getElementById("runHistoryUserSelect");
  if (userSelect) {
    userSelect.addEventListener("change", async (event) => {
      const userId = event.target.value;
      if (userId) {
        await loadRunsForUser(userId, { autoSelectLatest: true });
      } else {
        renderRunHistoryOptions([]);
      }
    });
  }

  const confirmRaftingButton = document.getElementById(
    "confirmRaftingChangeBtn"
  );
  if (confirmRaftingButton) {
    confirmRaftingButton.addEventListener("click", confirmRaftingWarning);
  }
}

async function openRunHistoryModal() {
  try {
    lastFocusedElement = document.activeElement;

    if (!runUsersLoaded) {
      await fetchRunHistoryUsers();
    }

    const modal = document.getElementById("runHistoryModal");
    const backdrop = document.getElementById("runHistoryBackdrop");
    if (!modal || !backdrop) return;

    const userSelect = document.getElementById("runHistoryUserSelect");
    if (userSelect && userSelect.value) {
      await loadRunsForUser(userSelect.value, { autoSelectLatest: true });
    }

    modal.classList.remove("hidden");
    backdrop.classList.remove("hidden");
    modal.classList.add("active");
    backdrop.classList.add("active");
    trapFocus(modal);
  } catch (error) {
    console.error("Failed to open run history modal:", error);
    showNotification(
      "Unable to load optimization history: " + error.message,
      "error"
    );
  }
}

function closeRunHistoryModal() {
  const modal = document.getElementById("runHistoryModal");
  const backdrop = document.getElementById("runHistoryBackdrop");
  if (!modal || !backdrop) return;

  modal.classList.add("hidden");
  backdrop.classList.add("hidden");
  modal.classList.remove("active");
  backdrop.classList.remove("active");
  releaseFocus("runHistoryModal");
  if (lastFocusedElement) {
    lastFocusedElement.focus();
    lastFocusedElement = null;
  }
}

async function fetchRunHistoryUsers() {
  const info = document.getElementById("runHistoryInfo");
  if (info) {
    info.textContent = "Loading available users...";
  }
  try {
    const response = await apiCall("/api/optimization-runs/users-with-runs/");
    runHistoryUsers = response.users || [];
    runUsersLoaded = true;
    populateRunHistoryUserSelect(response.current_user_id);
  } catch (error) {
    console.error("Failed to fetch run users:", error);
    showNotification("Unable to load available optimization users", "error");
    populateRunHistoryUserSelect(null);
  }
}

function populateRunHistoryUserSelect(preferredUserId) {
  const select = document.getElementById("runHistoryUserSelect");
  const info = document.getElementById("runHistoryInfo");
  if (!select || !info) return;

  select.innerHTML = "";

  if (!runHistoryUsers.length) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "No users with completed runs";
    select.appendChild(option);
    select.disabled = true;
    info.textContent = "No completed optimization runs are available yet.";
    renderRunHistoryOptions([]);
    return;
  }

  select.disabled = false;
  runHistoryUsers.forEach((user) => {
    const option = document.createElement("option");
    option.value = user.id;
    option.textContent = user.display_name || user.username;
    if (preferredUserId && String(user.id) === String(preferredUserId)) {
      option.selected = true;
    }
    select.appendChild(option);
  });

  const activeUserId =
    select.value || (runHistoryUsers[0] && runHistoryUsers[0].id);
  if (activeUserId) {
    loadRunsForUser(activeUserId, { autoSelectLatest: true });
  }
}

async function loadRunsForUser(userId, options = {}) {
  const info = document.getElementById("runHistoryInfo");
  const list = document.getElementById("runHistoryList");
  if (!list || !userId) return;

  info.textContent = "Loading recent runs...";
  list.innerHTML = "";

  try {
    const response = await apiCall(
      `/api/optimization-runs/recent/?user_id=${userId}&limit=${RUN_HISTORY_LIMIT}`
    );
    const runs = response.runs || [];
    if (response.user_display_name && info) {
      info.textContent = `Recent runs for ${response.user_display_name}`;
    }
    renderRunHistoryOptions(runs, options);
  } catch (error) {
    console.error("Failed to load runs:", error);
    info.textContent = "Unable to load optimization runs.";
    showNotification(
      "Failed to load optimization runs: " + error.message,
      "error"
    );
    renderRunHistoryOptions([]);
  }
}

function renderRunHistoryOptions(runs, options = {}) {
  const list = document.getElementById("runHistoryList");
  const info = document.getElementById("runHistoryInfo");
  if (!list || !info) return;

  list.innerHTML = "";
  if (!runs.length) {
    info.textContent = "No completed optimization runs found for this user.";
    selectedRunId = null;
    updateLoadRunButton();
    return;
  }

  const { autoSelectLatest = false } = options;

  runs.forEach((run, index) => {
    recentRunLookup[run.id] = run;
    const label = document.createElement("label");
    label.className = "run-option";

    const input = document.createElement("input");
    input.type = "radio";
    input.name = "runHistorySelection";
    input.value = run.id;

    if (
      (autoSelectLatest && index === 0) ||
      String(run.id) === String(selectedRunId)
    ) {
      input.checked = true;
      selectedRunId = run.id;
    }

    input.addEventListener("change", () => selectRunOption(run.id));

    const details = document.createElement("div");
    details.className = "run-option-details";

    const title = document.createElement("div");
    title.className = "run-option-title";
    title.textContent = `Run #${run.id}`;

    const meta = document.createElement("div");
    meta.className = "run-option-meta";
    meta.textContent = formatRunOptionMeta(run);

    details.appendChild(title);
    details.appendChild(meta);

    label.appendChild(input);
    label.appendChild(details);
    list.appendChild(label);

    label.addEventListener("click", () => {
      if (!input.checked) {
        input.checked = true;
        selectRunOption(run.id);
      }
    });
  });

  updateLoadRunButton();
}

function formatRunOptionMeta(run) {
  const createdAt = run.created_at
    ? formatRunTimestamp(run.created_at)
    : "Unknown time";
  const createdBy = run.created_by_username || "Unknown user";
  const mode = run.run_mode_display || run.run_mode || "Forecast";
  return `${createdBy} • ${createdAt} • ${mode}`;
}

function formatRunTimestamp(timestamp) {
  try {
    const date = new Date(timestamp);
    return date.toLocaleString("en-US", {
      timeZone: PACIFIC_TIMEZONE,
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
  } catch (error) {
    return "Unknown time";
  }
}

function selectRunOption(runId) {
  selectedRunId = runId;
  updateLoadRunButton();
}

function updateLoadRunButton() {
  const button = document.getElementById("confirmLoadRunBtn");
  if (button) {
    button.disabled = !selectedRunId;
  }
}

async function loadSelectedRun() {
  if (!selectedRunId) return;
  const runMeta = recentRunLookup[selectedRunId] || null;
  closeRunHistoryModal();
  await loadOptimizationResults(selectedRunId, runMeta);
}

function setCurrentRunDetails(runInfo) {
  if (runInfo) {
    currentRunDetails = {
      ...runInfo,
      created_by_name:
        runInfo.created_by_name ||
        runInfo.created_by_display ||
        runInfo.created_by_username,
    };
  } else {
    currentRunDetails = null;
  }
  updateActiveRunInfo();
  // Update MFRA source indicator from run metadata
  if (currentRunDetails && currentRunDetails.mfra_source) {
    updateMfraSourceIndicator(currentRunDetails.mfra_source);
  }
}

function updateActiveRunInfo() {
  const userElement = document.getElementById("activeRunUser");
  const timeElement = document.getElementById("activeRunTimestamp");
  const descriptionElement = document.getElementById("activeRunDescription");

  if (!userElement || !timeElement) {
    return;
  }

  if (!currentRunDetails) {
    userElement.textContent = "No optimization run loaded";
    timeElement.textContent = "";
    if (descriptionElement) {
      descriptionElement.textContent =
        "Review recent optimization performance and reload prior schedules.";
    }
    return;
  }

  const ownerName =
    currentRunDetails.created_by_name ||
    currentRunDetails.created_by_username ||
    currentRunDetails.created_by ||
    "Unknown user";
  const timestamp =
    currentRunDetails.completed_at || currentRunDetails.created_at || null;
  const mode =
    currentRunDetails.run_mode_display ||
    currentRunDetails.run_mode ||
    "Forecast";
  const source = currentRunDetails.forecast_source || "Configured";

  userElement.textContent = `Run Owner: ${ownerName}`;
  timeElement.textContent = timestamp
    ? `Generated: ${formatRunTimestamp(timestamp)}`
    : "Generated: Unknown";

  if (descriptionElement) {
    descriptionElement.textContent = `${mode} optimization loaded using ${source} forecast data.`;
  }
}

function detectForecastChanges() {
  if (
    !Array.isArray(forecastData) ||
    !Array.isArray(originalData) ||
    !originalData.length
  ) {
    return false;
  }

  if (forecastData.length !== originalData.length) {
    return true;
  }

  const fieldsToCheck = ["setpoint", "mfra", "r4", "r30"];

  for (let i = 0; i < forecastData.length; i++) {
    const current = forecastData[i];
    const baseline = originalData[i];
    if (!current || !baseline) {
      return true;
    }

    for (const field of fieldsToCheck) {
      if (!numbersAreClose(current[field], baseline[field])) {
        return true;
      }
    }
  }
  return false;
}

function numbersAreClose(a, b, tolerance = 0.0001) {
  const first = typeof a === "number" ? a : parseFloat(a) || 0;
  const second = typeof b === "number" ? b : parseFloat(b) || 0;
  return Math.abs(first - second) <= tolerance;
}

function updateSaveButtons() {
  const dashboardButton = document.getElementById("saveNewOptimizationBtn");
  const tableButton = document.getElementById("saveTableChangesBtn");

  if (dashboardButton) {
    if (forecastDirty) {
      dashboardButton.classList.remove("hidden");
      dashboardButton.disabled = false;
    } else {
      dashboardButton.classList.add("hidden");
      dashboardButton.disabled = true;
    }
  }

  if (tableButton) {
    tableButton.disabled = !forecastDirty;
  }
}

function getBiasEndpoint() {
  const meta = document.querySelector('meta[name="apply-bias-endpoint"]');
  const endpoint = meta?.content?.trim();
  return endpoint || "/api/optimization-runs/apply-bias/";
}

function formatBiasForDisplay(value) {
  const num = Number.parseFloat(value);
  if (!Number.isFinite(num)) {
    return "";
  }

  const abs = Math.abs(num);
  let decimals = 2;
  if (abs >= 100) {
    decimals = 0;
  } else if (abs >= 10) {
    decimals = 1;
  }

  const formatted = num.toFixed(decimals);
  const sign = num >= 0 ? "+" : "";
  return `${sign}${formatted} cfs`;
}

function formatBiasForInput(value) {
  const num = Number.parseFloat(value);
  if (!Number.isFinite(num)) {
    return "";
  }

  const abs = Math.abs(num);
  let decimals = 2;
  if (abs >= 100) {
    decimals = 0;
  } else if (abs >= 10) {
    decimals = 1;
  }

  return num.toFixed(decimals);
}

function updateBiasLegendLabel(biasValue) {
  const legendLabel = document.querySelector(
    '.legend-item[data-chart="elevation"][data-dataset="1"] span'
  );
  const displayText = formatBiasForDisplay(biasValue);
  const labelText = displayText
    ? `Bias Corrected Expected (${displayText})`
    : "Bias Corrected Expected";

  if (legendLabel) {
    legendLabel.textContent = labelText;
  }

  if (elevationChart && elevationChart.getOption) {
    try {
      const opt = elevationChart.getOption();
      if (opt.series && opt.series[1]) {
        elevationChart.setOption({ series: [{ /* idx 0 unchanged */ }, { name: labelText }] });
      }
    } catch(e) { /* chart may not be ready */ }
  }
}

function setAppliedBiasValue(value, options = {}) {
  const { updateInput = true } = options;
  const parsed = Number.parseFloat(value);
  currentBiasValue = Number.isFinite(parsed) ? parsed : null;

  updateBiasLegendLabel(currentBiasValue);

  // Update the display span
  const displayEl = document.getElementById("currentBiasDisplay");
  if (displayEl) {
    const displayVal = currentBiasValue !== null ? formatBiasForDisplay(currentBiasValue) : "0 CFS";
    displayEl.textContent = `Bias: ${displayVal}`;
  }

  if (updateInput) {
    const biasInput = document.getElementById("biasValueInput");
    if (biasInput) {
      // Clear input so user can enter new value easily, or set to current if desired.
      // The prompt implies user enters a NEW value. Let's keep it empty or show current?
      // "if the calculated bias was 100 cfs, and a user enters 105 cfs"
      // It might be better to leave it empty for "New Bias" or pre-fill it.
      // Given the "Clean up" request, maybe they expect it to be a "block" edit.
      // But let's be safe and just edit the point.
      biasInput.value =
        currentBiasValue === null ? "" : formatBiasForInput(currentBiasValue);
    }
  }
}

function buildBiasRequestPayload(biasValue) {
  const payload = {
    bias_cfs: biasValue,
  };

  const runIdFromData =
    currentRunId ||
    currentOptimizationData?.run_id ||
    currentOptimizationData?.run?.id;
  if (runIdFromData) {
    payload.run_id = runIdFromData;
  }

  const forecastSource =
    currentOptimizationData?.chart_data?.forecast_data ||
    currentOptimizationData?.forecast_data ||
    latestChartData?.forecast_data;

  if (Array.isArray(forecastSource) && forecastSource.length) {
    payload.forecast_data = forecastSource;
  } else if (Array.isArray(forecastData) && forecastData.length) {
    payload.forecast_data = forecastData.map((row) => ({
      datetime:
        row.datetime instanceof Date
          ? row.datetime.toISOString()
          : row.datetime,
      oxph: row.oxph ?? null,
      mfra: row.mfra ?? null,
      r4: row.r4 ?? null,
      r30: row.r30 ?? null,
      r20: row.r20 ?? null,
      r5l: row.r5l ?? null,
      r26: row.r26 ?? null,
      float_level: row.floatLevel ?? row.float_level ?? null,
      elevation: row.elevation ?? null,
      oxph_actual: row.oxphActual ?? row.oxph_actual ?? null,
      mfra_actual: row.mfraActual ?? row.mfra_actual ?? null,
      r4_actual: row.r4Actual ?? row.r4_actual ?? null,
      r30_actual: row.r30Actual ?? row.r30_actual ?? null,
      r20_actual: row.r20Actual ?? row.r20_actual ?? null,
      r5l_actual: row.r5lActual ?? row.r5l_actual ?? null,
      r26_actual: row.r26Actual ?? row.r26_actual ?? null,
      mode: row.mode ?? null,
      mode_actual: row.modeActual ?? null,
      abay_elevation: row.abayElevation ?? row.abay_elevation ?? null,
      expected_abay: row.elevation ?? row.expected_abay ?? null,
      bias_cfs: row.biasCfs ?? row.additionalBias ?? null,
    }));
  }

  return payload;
}

function extractAppliedBiasFromResponse(response, fallbackValue) {
  if (!response || typeof response !== "object") {
    return fallbackValue;
  }

  const summaryBias = response.summary?.r_bias_cfs;
  if (summaryBias !== undefined && summaryBias !== null) {
    const parsed = Number.parseFloat(summaryBias);
    if (Number.isFinite(parsed)) {
      return parsed;
    }
  }

  const directBiasKeys = [
    "applied_bias_cfs",
    "bias_cfs",
    "appliedBias",
    "bias",
  ];
  for (const key of directBiasKeys) {
    if (response[key] !== undefined && response[key] !== null) {
      const parsed = Number.parseFloat(response[key]);
      if (Number.isFinite(parsed)) {
        return parsed;
      }
    }
  }

  return fallbackValue;
}

async function applyBiasCorrection(button) {
  const adjustmentInput = document.getElementById("biasValueInput");
  if (!adjustmentInput) {
    showNotification("Bias input not found", "error");
    return;
  }

  const rawValue = adjustmentInput.value.trim();
  if (!rawValue.length) {
    showNotification("Enter a bias value.", "warning");
    adjustmentInput.focus();
    return;
  }

  const newBiasValue = Number.parseFloat(rawValue);
  if (!Number.isFinite(newBiasValue)) {
    showNotification("Bias must be a valid number.", "error");
    adjustmentInput.focus();
    return;
  }

  // The user enters the TOTAL desired bias.
  // Example: Current is 100. User enters 105. Result is 105.
  const totalBias = newBiasValue;
  const currentBias = Number.isFinite(currentBiasValue) ? currentBiasValue : 0;
  const diff = totalBias - currentBias;

  const payload = buildBiasRequestPayload(totalBias);
  const shouldReapplyActuals = actualsApplied;

  if (
    !payload.run_id &&
    (!payload.forecast_data || !payload.forecast_data.length)
  ) {
    showNotification(
      "Load optimization data before applying a bias adjustment.",
      "warning"
    );
    return;
  }

  if (button) {
    button.disabled = true;
    button.dataset.originalText =
      button.dataset.originalText || button.textContent;
    button.textContent = "Applying...";
  }

  try {
    const sign = diff >= 0 ? "+" : "";
    showNotification(
      `Setting bias to ${totalBias} CFS (${sign}${diff.toFixed(1)} change)`,
      "info"
    );

    const response = await apiCall(getBiasEndpoint(), {
      method: "POST",
      body: JSON.stringify(payload),
    });

    if (response.error) {
      throw new Error(response.error);
    }

    const chartData =
      response.chart_data ||
      response.updated_chart_data ||
      response.data?.chart_data;
    if (chartData) {
      updateChartsWithOptimizationData(chartData);
      if (chartData.forecast_data) {
        updateForecastTableWithData(chartData.forecast_data);
      }
      currentOptimizationData = currentOptimizationData || {};
      currentOptimizationData.chart_data = chartData;
    } else if (response.forecast_data) {
      updateForecastTableWithData(response.forecast_data);
    }

    if (response.run) {
      setCurrentRunDetails(response.run);
    }
    if (response.run_id !== undefined && response.run_id !== null) {
      currentRunId = response.run_id;
    }

    if (response.summary) {
      currentOptimizationData = currentOptimizationData || {};
      currentOptimizationData.summary = {
        ...(currentOptimizationData.summary || {}),
        ...response.summary,
      };
    }

    const fallbackBias = extractAppliedBiasFromResponse(response, totalBias);
    setAppliedBiasValue(fallbackBias, { updateInput: true });

    if (shouldReapplyActuals) {
      applyActuals({ silent: true });
    }

    let derivedBias = null;
    if (chartData) {
      derivedBias = deriveBiasFromChartData(chartData, fallbackBias);
    } else if (response.forecast_data) {
      derivedBias = deriveBiasFromChartData(
        { forecast_data: response.forecast_data },
        fallbackBias
      );
    }

    const effectiveBias = derivedBias !== null ? derivedBias : fallbackBias;
    setAppliedBiasValue(effectiveBias);

    if (currentOptimizationData) {
      currentOptimizationData.summary = {
        ...(currentOptimizationData.summary || {}),
        r_bias_cfs: effectiveBias,
      };
    }

    showNotification("Bias applied successfully", "success");
  } catch (error) {
    console.error("Error applying bias correction:", error);
    showNotification("Failed to apply bias: " + error.message, "error");
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = button.dataset.originalText || "Set Bias";
    }
  }
}

function applyBiasCorrectionLegacy(button, biasInput) {
  const rawValue = biasInput.value.trim();
  if (!rawValue.length) return;
  const biasValue = Number.parseFloat(rawValue);
  // Legacy logic placeholder
}

function destroyChartInstance(chart) {
  if (chart && typeof chart.dispose === 'function') {
    chart.dispose();
  } else if (chart && typeof chart.destroy === 'function') {
    chart.destroy();
  }
}

// Shared ECharts base options
function getBaseChartOption(labels, yAxisName, yMin) {
  return {
    animation: true,
    animationDuration: 600,
    grid: { left: 60, right: 30, top: 40, bottom: 80 },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' }
    },
    legend: { show: false },
    xAxis: {
      type: 'category',
      data: labels || [],
      axisLabel: {
        rotate: 45,
        interval: function (index) { return index % 6 === 0; },
        fontSize: 11
      },
      name: 'Date/Time',
      nameLocation: 'center',
      nameGap: 50
    },
    yAxis: {
      type: 'value',
      name: yAxisName || '',
      min: yMin != null ? yMin : undefined,
      nameTextStyle: { fontSize: 12 },
      splitLine: { show: true }
    },
    dataZoom: [
      { type: 'slider', xAxisIndex: 0, start: 0, end: 100, height: 25, bottom: 5 },
      { type: 'inside', xAxisIndex: 0 }
    ],
    series: []
  };
}

// Connect charts for synced tooltip
let chartsConnected = false;

function initializeCharts() {
  elevationChart = destroyEChart(elevationChart);
  oxphChart = destroyEChart(oxphChart);
  historicalChart = destroyEChart(historicalChart);

  // ABAY Elevation Chart (ECharts)
  elevationChart = initEChart('elevationChart');
  if (elevationChart) {
    elevationChart.setOption(getBaseChartOption([], 'Elevation (ft)', 1166));
    elevationChart.group = 'dashboardSync';
  }

  // Power Output Chart (ECharts)
  oxphChart = initEChart('oxphChart');
  if (oxphChart) {
    var oxphOpt = getBaseChartOption([], 'Power Output (MW)', 0);
    oxphOpt.yAxis.min = 0;
    oxphChart.setOption(oxphOpt);
    oxphChart.group = 'dashboardSync';
  }

  // Connect elevation and OXPH charts for synced tooltips
  if (elevationChart && oxphChart && !chartsConnected) {
    echarts.connect('dashboardSync');
    chartsConnected = true;
  }

  // Historical Analysis Chart (ECharts)
  historicalChart = initEChart('historicalChart');
  if (historicalChart) {
    var histOpt = getBaseChartOption([], 'Value');
    histOpt.legend = { show: true, textStyle: { fontSize: 12 } };
    historicalChart.setOption(histOpt);
  }

  window.elevationChart = elevationChart;
  window.oxphChart = oxphChart;
  window.historicalChart = historicalChart;
  window.priceChart = priceChart;

  // Register for theme reinit
  if (typeof registerChartReinit === 'function' && !window._mainChartsRegistered) {
    registerChartReinit(function () {
      chartsConnected = false;
      // Dispose drill-down chart if open during theme switch
      if (schematicDrillDownChart) {
        schematicDrillDownChart.dispose();
        schematicDrillDownChart = null;
      }
      initializeCharts();
      if (latestChartData) {
        applyElevationChartData(latestChartData);
        refreshPowerChart();
      }
      if (currentPriceData) {
        initializePriceChart();
        updatePriceChart(currentPriceData);
      }
    });
    window._mainChartsRegistered = true;
  }

  // Initialize gauge widgets
  initGaugeWidgets();

  // Initialize timeline
  initTimeline();

  updateBiasLegendLabel(currentBiasValue);
}

// ============================================
// KPI GAUGE WIDGETS (ECharts)
// ============================================
let gaugeElevation, gaugeOXPH, gaugeSpillRisk, gaugeRevenue, gaugeConfidence;

function initGaugeWidgets() {
  gaugeElevation = destroyEChart(gaugeElevation);
  gaugeOXPH = destroyEChart(gaugeOXPH);
  gaugeSpillRisk = destroyEChart(gaugeSpillRisk);
  gaugeRevenue = destroyEChart(gaugeRevenue);
  gaugeConfidence = destroyEChart(gaugeConfidence);

  gaugeElevation = initEChart('gaugeElevation');
  gaugeOXPH = initEChart('gaugeOXPH');
  gaugeSpillRisk = initEChart('gaugeSpillRisk');
  gaugeRevenue = initEChart('gaugeRevenue');
  gaugeConfidence = initEChart('gaugeConfidence');

  var isDark = document.documentElement.getAttribute('data-theme') === 'dark';
  var trackColor = isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.06)';
  var detailColor = isDark ? '#e2e8f0' : '#1e293b';

  // Helper: pick arc color based on normalized value and color stops
  function arcColorForValue(pct, colorStops) {
    for (var i = 0; i < colorStops.length; i++) {
      if (pct <= colorStops[i][0]) return colorStops[i][1];
    }
    return colorStops[colorStops.length - 1][1];
  }

  // Modern radial arc gauge — no pointer, no ticks, clean progress ring
  function makeGaugeOption(min, max, value, unit, colorStops, fmtFn) {
    var pct = max > min ? (value - min) / (max - min) : 0;
    var activeColor = arcColorForValue(pct, colorStops);
    return {
      series: [
        // Background track ring
        {
          type: 'gauge',
          center: ['50%', '58%'],
          radius: '90%',
          startAngle: 220,
          endAngle: -40,
          min: min, max: max,
          pointer: { show: false },
          progress: { show: false },
          axisLine: { lineStyle: { width: 14, color: [[1, trackColor]], roundCap: true } },
          axisTick: { show: false },
          splitLine: { show: false },
          axisLabel: { show: false },
          title: { show: false },
          detail: { show: false },
          data: [{ value: value }]
        },
        // Active progress arc
        {
          type: 'gauge',
          center: ['50%', '58%'],
          radius: '90%',
          startAngle: 220,
          endAngle: -40,
          min: min, max: max,
          pointer: { show: false },
          progress: {
            show: true,
            width: 14,
            roundCap: true,
            itemStyle: { color: activeColor }
          },
          axisLine: { show: false },
          axisTick: { show: false },
          splitLine: { show: false },
          axisLabel: { show: false },
          title: { show: false },
          detail: {
            valueAnimation: true,
            fontSize: 20,
            fontWeight: 700,
            fontFamily: "'Inter', 'SF Pro Display', system-ui, sans-serif",
            color: detailColor,
            offsetCenter: [0, '8%'],
            formatter: fmtFn || function (v) { return v.toFixed(1) + ' ' + unit; }
          },
          data: [{ value: value }],
          // Store metadata for dynamic color updates
          _colorStops: colorStops,
          _min: min,
          _max: max
        }
      ]
    };
  }

  // Color stops: [normalizedPosition, color]
  // Elevation gauge uses a custom rich-text formatter for trend arrow
  if (gaugeElevation) {
    var elevOpt = makeGaugeOption(1166, 1175, 1170, 'ft', [
      [0.22, '#ef4444'], [0.33, '#f59e0b'], [0.78, '#10b981'], [0.89, '#f59e0b'], [1, '#ef4444']
    ]);
    // Override detail with rich text support for trend indicator
    elevOpt.series[1].detail = {
      valueAnimation: true,
      fontSize: 20,
      fontWeight: 700,
      fontFamily: "'Inter', 'SF Pro Display', system-ui, sans-serif",
      offsetCenter: [0, '2%'],
      rich: {
        val: { fontSize: 20, fontWeight: 700, color: detailColor },
        unit: { fontSize: 13, fontWeight: 400, color: isDark ? '#94a3b8' : '#64748b', padding: [0, 0, 0, 2] },
        up: { fontSize: 12, fontWeight: 600, color: '#10b981', padding: [4, 0, 0, 0] },
        down: { fontSize: 12, fontWeight: 600, color: '#ef4444', padding: [4, 0, 0, 0] },
        flat: { fontSize: 12, fontWeight: 600, color: isDark ? '#64748b' : '#94a3b8', padding: [4, 0, 0, 0] }
      },
      formatter: function (v) {
        return '{val|' + v.toFixed(1) + '}{unit| ft}\n{flat|―  0.0 ft/hr}';
      }
    };
    gaugeElevation.setOption(elevOpt);
  }

  if (gaugeOXPH) {
    gaugeOXPH.setOption(makeGaugeOption(0, 6, 0, 'MW', [
      [0.15, '#f59e0b'], [0.85, '#10b981'], [1, '#ef4444']
    ]));
  }

  if (gaugeSpillRisk) {
    gaugeSpillRisk.setOption(makeGaugeOption(0, 100, 0, '%', [
      [0.5, '#10b981'], [0.8, '#f59e0b'], [1, '#ef4444']
    ]));
  }

  if (gaugeRevenue) {
    gaugeRevenue.setOption(makeGaugeOption(0, 500, 0, '$/hr', [
      [0.3, '#f59e0b'], [1, '#10b981']
    ], function (v) { return '$' + Math.round(v); }));
  }

  if (gaugeConfidence) {
    gaugeConfidence.setOption(makeGaugeOption(0, 100, 85, '%', [
      [0.4, '#ef4444'], [0.7, '#f59e0b'], [1, '#10b981']
    ]));
  }
}

function _updateGauge(chart, value) {
  if (!chart) return;
  var opt = chart.getOption();
  // series[1] is the active progress arc
  var meta = opt.series[1] || {};
  var stops = meta._colorStops;
  var gMin = meta._min != null ? meta._min : (meta.min || 0);
  var gMax = meta._max != null ? meta._max : (meta.max || 100);
  var pct = gMax > gMin ? (value - gMin) / (gMax - gMin) : 0;
  pct = Math.max(0, Math.min(1, pct));

  var color = undefined;
  if (stops && stops.length) {
    for (var i = 0; i < stops.length; i++) {
      if (pct <= stops[i][0]) { color = stops[i][1]; break; }
    }
    if (!color) color = stops[stops.length - 1][1];
  }

  var update = {
    series: [
      { data: [{ value: value }] },
      { data: [{ value: value }] }
    ]
  };
  if (color) {
    update.series[1].progress = { itemStyle: { color: color } };
  }
  chart.setOption(update);
}

function updateGaugeWidgets(data) {
  if (!data) return;
  if (gaugeElevation && data.elevation != null) {
    var elVal = parseFloat(data.elevation);
    var delta = data.elevDelta;
    // Update arc color + value via generic helper
    _updateGauge(gaugeElevation, elVal);
    // Update the rich-text detail with trend arrow
    var trendTag, trendText;
    if (delta != null && Math.abs(delta) >= 0.01) {
      if (delta > 0) {
        trendTag = 'up';
        trendText = '\u25B2  +' + delta.toFixed(1) + ' ft/hr';
      } else {
        trendTag = 'down';
        trendText = '\u25BC  ' + delta.toFixed(1) + ' ft/hr';
      }
    } else {
      trendTag = 'flat';
      trendText = '\u2014  0.0 ft/hr';
    }
    gaugeElevation.setOption({
      series: [{}, {
        detail: {
          formatter: function (v) {
            return '{val|' + v.toFixed(1) + '}{unit| ft}\n{' + trendTag + '|' + trendText + '}';
          }
        }
      }]
    });
  }
  if (gaugeOXPH && data.oxph != null) {
    _updateGauge(gaugeOXPH, parseFloat(data.oxph));
  }
  if (gaugeSpillRisk && data.elevation != null) {
    var elev = parseFloat(data.elevation);
    var risk = Math.max(0, Math.min(100, ((elev - 1172) / 3) * 100));
    _updateGauge(gaugeSpillRisk, Math.round(risk));
  }
  if (gaugeRevenue && data.oxph != null && data.price != null) {
    var rev = parseFloat(data.oxph) * parseFloat(data.price);
    _updateGauge(gaugeRevenue, rev);
  }
  if (gaugeConfidence && data.biasConfidence != null) {
    _updateGauge(gaugeConfidence, parseFloat(data.biasConfidence));
  }
}

// ============================================
// 7-DAY SCHEDULE TIMELINE (ECharts)
// ============================================
let timelineChart = null;

function initTimeline() {
  timelineChart = destroyEChart(timelineChart);
  const dom = document.getElementById('timelineChart');
  if (!dom) return;
  timelineChart = initEChart('timelineChart');
  if (!timelineChart) return;

  const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
  timelineChart.setOption({
    tooltip: {
      trigger: 'axis',
      backgroundColor: isDark ? 'rgba(15,23,42,0.9)' : 'rgba(255,255,255,0.95)',
      borderColor: isDark ? 'rgba(0,212,255,0.3)' : '#ccc',
      textStyle: { color: isDark ? '#e2e8f0' : '#333', fontSize: 11 }
    },
    grid: { left: 55, right: 20, top: 30, bottom: 50 },
    xAxis: {
      type: 'category',
      data: [],
      axisLabel: { rotate: 30, fontSize: 10, color: isDark ? '#94a3b8' : '#666', interval: 5 },
      axisLine: { lineStyle: { color: isDark ? 'rgba(255,255,255,0.1)' : '#ccc' } }
    },
    yAxis: {
      type: 'value',
      name: 'MW',
      nameTextStyle: { color: isDark ? '#94a3b8' : '#666', fontSize: 11 },
      axisLabel: { color: isDark ? '#94a3b8' : '#666', fontSize: 10 },
      splitLine: { lineStyle: { color: isDark ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.06)' } }
    },
    dataZoom: [
      { type: 'slider', bottom: 5, height: 18 },
      { type: 'inside' }
    ],
    series: []
  });
}

function updateTimeline(chartData) {
  if (!timelineChart || !chartData) return;

  const labels = chartData.labels || [];
  const oxphOpt = chartData.oxph?.optimized || [];
  const floatArr = chartData.elevation?.float || [];
  const isDark = document.documentElement.getAttribute('data-theme') === 'dark';

  // Detect rafting windows (hours where float level is notably different / high-flow periods)
  const raftingMarkAreas = [];
  let raftStart = null;
  for (let i = 0; i < labels.length; i++) {
    const isRafting = floatArr[i] != null && floatArr[i] >= 1173.5;
    if (isRafting && raftStart === null) {
      raftStart = i;
    } else if (!isRafting && raftStart !== null) {
      raftingMarkAreas.push([
        { xAxis: labels[raftStart], itemStyle: { color: isDark ? 'rgba(0,255,136,0.06)' : 'rgba(39,174,96,0.08)' } },
        { xAxis: labels[i - 1] }
      ]);
      raftStart = null;
    }
  }
  if (raftStart !== null) {
    raftingMarkAreas.push([
      { xAxis: labels[raftStart], itemStyle: { color: isDark ? 'rgba(0,255,136,0.06)' : 'rgba(39,174,96,0.08)' } },
      { xAxis: labels[labels.length - 1] }
    ]);
  }

  // Day divider markLines
  const dayLines = buildDayDividers(labels);

  timelineChart.setOption({
    xAxis: { data: labels },
    series: [
      {
        name: 'OXPH Setpoint',
        type: 'bar',
        data: oxphOpt.map(v => v != null ? parseFloat(v) : null),
        barMaxWidth: 8,
        itemStyle: {
          color: function (params) {
            const v = params.value;
            if (v == null) return 'transparent';
            if (v >= 5.0) return isDark ? '#ff006e' : '#e74c3c';
            if (v >= 3.5) return isDark ? '#00d4ff' : '#3498db';
            return isDark ? '#00ff88' : '#27ae60';
          }
        },
        markArea: { silent: true, data: raftingMarkAreas },
        markLine: {
          silent: true,
          symbol: 'none',
          lineStyle: { color: isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.08)', type: 'dashed', width: 1 },
          data: dayLines
        }
      }
    ]
  });
}

window.timelineZoom = function (direction) {
  if (!timelineChart) return;
  const opt = timelineChart.getOption();
  if (!opt.dataZoom || !opt.dataZoom[0]) return;
  let start = opt.dataZoom[0].start || 0;
  let end = opt.dataZoom[0].end || 100;
  const range = end - start;

  if (direction === 'in') {
    const mid = (start + end) / 2;
    const newRange = Math.max(10, range * 0.6);
    start = Math.max(0, mid - newRange / 2);
    end = Math.min(100, mid + newRange / 2);
  } else if (direction === 'out') {
    const mid = (start + end) / 2;
    const newRange = Math.min(100, range * 1.6);
    start = Math.max(0, mid - newRange / 2);
    end = Math.min(100, mid + newRange / 2);
  } else {
    start = 0;
    end = 100;
  }
  timelineChart.dispatchAction({ type: 'dataZoom', start: start, end: end });
};

function ensureArrayLength(arr, length, fillValue = null) {
  if (!Array.isArray(arr)) {
    return new Array(length).fill(fillValue);
  }
  if (arr.length === length) {
    return arr.slice();
  }
  if (arr.length > length) {
    return arr.slice(0, length);
  }
  return arr.concat(new Array(length - arr.length).fill(fillValue));
}

function alignSeriesToLabels(series, targetLength) {
  return ensureArrayLength(series, targetLength, null);
}

function hasChartValues(data) {
  return (
    Array.isArray(data) &&
    data.some(
      (value) => value !== null && value !== undefined && !Number.isNaN(value)
    )
  );
}

function normalizeChartData(chartData) {
  const labels = Array.isArray(chartData?.labels)
    ? chartData.labels.slice()
    : [];
  const length = labels.length;

  const elevation = chartData?.elevation || {};
  const oxph = chartData?.oxph || {};
  const mfra = chartData?.mfra || {};
  const river = chartData?.river || {};
  const floatSource =
    elevation.float ??
    (chartData?.float_level !== undefined
      ? new Array(length).fill(chartData.float_level)
      : null);

  return {
    labels,
    elevation: {
      optimized: alignSeriesToLabels(elevation.optimized, length),
      actual: alignSeriesToLabels(elevation.actual, length),
      bias_corrected: alignSeriesToLabels(elevation.bias_corrected, length),
      float: alignSeriesToLabels(floatSource, length),
    },
    oxph: {
      optimized: alignSeriesToLabels(oxph.optimized, length),
      historical: alignSeriesToLabels(oxph.historical, length),
    },
    mfra: {
      forecast: alignSeriesToLabels(mfra.forecast, length),
      historical: alignSeriesToLabels(mfra.historical, length),
    },
    river: {
      selected_source: river.selected_source || null,
      selected_source_label: river.selected_source_label || "",
      source_labels: {
        hydro: river.source_labels?.hydro || "HydroForecast",
        cnrfc: river.source_labels?.cnrfc || "CNRFC Forecast",
      },
      r4: {
        actual: alignSeriesToLabels(river.r4?.actual, length),
        hydro: alignSeriesToLabels(river.r4?.hydro, length),
        cnrfc: alignSeriesToLabels(river.r4?.cnrfc, length),
      },
      r30: {
        actual: alignSeriesToLabels(river.r30?.actual, length),
        hydro: alignSeriesToLabels(river.r30?.hydro, length),
        cnrfc: alignSeriesToLabels(river.r30?.cnrfc, length),
      },
    },
    actual_mask: ensureArrayLength(chartData?.actual_mask, length, false),
    forecast_data: Array.isArray(chartData?.forecast_data)
      ? chartData.forecast_data
      : [],
  };
}

function applyElevationChartData(chartData, animationMode = "default") {
  if (!chartData || !elevationChart) return;

  const labels = chartData.labels || [];
  const labelCount = labels.length;
  const actual = alignSeriesToLabels(chartData.elevation.actual, labelCount);
  const biasCorrected = alignSeriesToLabels(chartData.elevation.bias_corrected, labelCount);
  const optimized = alignSeriesToLabels(chartData.elevation.optimized, labelCount);
  const floatLevel = alignSeriesToLabels(chartData.elevation.float, labelCount);

  // Calculate Y-axis bounds
  var allVals = [].concat(actual, biasCorrected, optimized, floatLevel).filter(function (v) { return v != null && Number.isFinite(v); });
  var yMin = 1166;
  var yMax = allVals.length ? Math.ceil(Math.max.apply(null, allVals) + 1) : 1176;

  // Build day divider markLines
  var dividers = buildDayDividers(labels);

  var biasLabel = 'Bias Corrected Expected';
  if (currentBiasValue != null && Number.isFinite(currentBiasValue)) {
    biasLabel = 'Expected (Bias: ' + currentBiasValue + ' CFS)';
  }

  elevationChart.setOption({
    xAxis: { data: labels },
    yAxis: { min: yMin, max: yMax },
    legend: {
      show: true,
      bottom: 35,
      textStyle: { fontSize: 11 },
      data: ['Actual Elevation', biasLabel, 'Optimized Forecast', 'Float Level']
    },
    series: [
      {
        name: 'Actual Elevation',
        type: 'line',
        data: actual,
        itemStyle: { color: '#e74c3c' },
        lineStyle: { width: 2 },
        symbol: 'none',
        smooth: false,
        connectNulls: false
      },
      {
        name: biasLabel,
        type: 'line',
        data: biasCorrected,
        itemStyle: { color: '#f39c12' },
        lineStyle: { width: 2, type: 'dashed' },
        symbol: 'none',
        smooth: false,
        connectNulls: false
      },
      {
        name: 'Optimized Forecast',
        type: 'line',
        data: optimized,
        itemStyle: { color: '#3498db' },
        lineStyle: { width: 3 },
        symbol: 'none',
        smooth: false,
        connectNulls: false,
        areaStyle: { color: 'rgba(52, 152, 219, 0.06)' },
        markLine: {
          silent: true,
          symbol: 'none',
          label: { show: false },
          data: dividers
        }
      },
      {
        name: 'Float Level',
        type: 'line',
        data: floatLevel,
        itemStyle: { color: '#dc3545' },
        lineStyle: { width: 2, type: [10, 5] },
        symbol: 'none',
        smooth: false,
        connectNulls: true
      }
    ]
  }, { notMerge: false, lazyUpdate: animationMode === 'none' });

  updateBiasLegendLabel(currentBiasValue);

  // Update status bar and gauges with latest values
  var lastActualElev = null, prevActualElev = null;
  if (actual.length) {
    // Find last two non-null actual elevations for delta computation
    var found = 0;
    for (var i = actual.length - 1; i >= 0 && found < 2; i--) {
      if (actual[i] != null) {
        if (found === 0) lastActualElev = actual[i];
        else prevActualElev = actual[i];
        found++;
      }
    }
  }
  var elevDelta = (lastActualElev != null && prevActualElev != null)
    ? lastActualElev - prevActualElev : null;
  if (typeof updateStatusBar === 'function') {
    updateStatusBar({ elevation: lastActualElev });
  }
  if (typeof updateSchematicData === 'function') {
    updateSchematicData({ elevation: lastActualElev });
  }
  updateGaugeWidgets({ elevation: lastActualElev, elevDelta: elevDelta });

  // Update 7-day timeline
  updateTimeline(chartData);
}

function renderPowerChartLegend(seriesList) {
  // ECharts handles legends natively, but we update the external legend container
  const legendContainer = document.getElementById("powerChartLegend");
  if (!legendContainer) return;
  legendContainer.innerHTML = "";

  seriesList.forEach(function (s) {
    var legendItem = document.createElement("div");
    legendItem.className = "legend-item";
    legendItem.dataset.chart = "oxph";
    legendItem.dataset.seriesName = s.name;

    var colorSwatch = document.createElement("div");
    colorSwatch.className = "legend-color";
    if (s.lineStyle && s.lineStyle.type && s.lineStyle.type !== 'solid') {
      colorSwatch.style.borderBottom = '3px dashed ' + (s.itemStyle ? s.itemStyle.color : '#999');
      colorSwatch.style.background = 'none';
    } else {
      colorSwatch.style.background = s.itemStyle ? s.itemStyle.color : '#999';
    }
    legendItem.appendChild(colorSwatch);

    var labelSpan = document.createElement("span");
    labelSpan.textContent = s.name;
    legendItem.appendChild(labelSpan);

    legendItem.addEventListener('click', function () {
      if (!oxphChart) return;
      oxphChart.dispatchAction({ type: 'legendToggleSelect', name: s.name });
      legendItem.classList.toggle('inactive');
    });

    legendContainer.appendChild(legendItem);
  });
}

function changePowerChartMode(mode) {
  if (!mode || powerChartMode === mode) return;
  powerChartMode = mode;
  const select = document.getElementById("powerChartModeSelect");
  if (select && select.value !== mode) {
    select.value = mode;
  }
  refreshPowerChart();
}

function refreshPowerChart(animationMode = "default") {
  if (!oxphChart) return;

  const labels = latestChartData?.labels || [];
  const chartTitleEl = document.getElementById("powerChartTitle");

  if (!labels.length) {
    oxphChart.setOption({ tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } }, xAxis: { data: [] }, series: [] }, { notMerge: true });
    renderPowerChartLegend([]);
    if (chartTitleEl) chartTitleEl.textContent = "Power Output";
    return;
  }

  const labelCount = labels.length;
  const seriesList = [];
  let yLabel = "Power Output (MW)";

  function makeSeries(name, data, color, opts) {
    var s = {
      name: name,
      type: 'line',
      data: alignSeriesToLabels(data, labelCount),
      itemStyle: { color: color },
      lineStyle: { width: opts.width || 2, type: opts.dash || 'solid' },
      symbol: 'none',
      smooth: false,
      connectNulls: true
    };
    if (opts.step) s.step = 'end';
    return s;
  }

  if (powerChartMode === "mfra") {
    seriesList.push(makeSeries("Historical MFRA", latestChartData?.mfra?.historical, "#2980b9", { width: 2 }));
    seriesList.push(makeSeries("Forecast MFRA", latestChartData?.mfra?.forecast, "#e67e22", { width: 2, dash: 'dashed' }));
    if (chartTitleEl) chartTitleEl.textContent = "MFRA MW Output (Observed vs Forecast)";
  } else if (powerChartMode === "river") {
    var riverData = latestChartData?.river || {};
    var r4 = riverData.r4 || {};
    var r30 = riverData.r30 || {};
    var hydroLabel = riverData.source_labels?.hydro || "HydroForecast";
    var cnrfcLabel = riverData.source_labels?.cnrfc || "CNRFC Forecast";

    seriesList.push(makeSeries("R4 Observed", r4.actual, "#1abc9c", { width: 2 }));
    seriesList.push(makeSeries("R4 " + hydroLabel, r4.hydro, "#16a085", { width: 2, dash: 'dashed' }));
    seriesList.push(makeSeries("R4 " + cnrfcLabel, r4.cnrfc, "#48c9b0", { width: 2, dash: [4, 4] }));
    seriesList.push(makeSeries("R30 Observed", r30.actual, "#e67e22", { width: 2 }));
    seriesList.push(makeSeries("R30 " + hydroLabel, r30.hydro, "#d35400", { width: 2, dash: 'dashed' }));
    seriesList.push(makeSeries("R30 " + cnrfcLabel, r30.cnrfc, "#f1c40f", { width: 2, dash: [4, 4] }));
    yLabel = "River Flow (CFS)";
    if (chartTitleEl) chartTitleEl.textContent = "R30 & R4 River Flows";
  } else {
    seriesList.push(makeSeries("Historical OXPH", latestChartData?.oxph?.historical, "#27ae60", { width: 2 }));
    seriesList.push(makeSeries("Optimized Schedule", latestChartData?.oxph?.optimized, "#9b59b6", { width: 3, step: true }));
    if (chartTitleEl) chartTitleEl.textContent = "OXPH Output (24h + 4 Day Forecast)";

    // Update OXPH status and schematic with latest actual (not first forecast)
    var oxphHist = latestChartData?.oxph?.historical;
    var oxphOpt = latestChartData?.oxph?.optimized;
    var lastOxphVal = null;
    // Prefer last actual reading
    if (Array.isArray(oxphHist)) {
      for (var i = oxphHist.length - 1; i >= 0; i--) {
        if (oxphHist[i] != null) { lastOxphVal = oxphHist[i]; break; }
      }
    }
    // Fall back to first optimized value if no actuals
    if (lastOxphVal == null && Array.isArray(oxphOpt)) {
      for (var i = 0; i < oxphOpt.length; i++) {
        if (oxphOpt[i] != null) { lastOxphVal = oxphOpt[i]; break; }
      }
    }
    if (lastOxphVal != null) {
      if (typeof updateStatusBar === 'function') updateStatusBar({ oxph: lastOxphVal });
      if (typeof updateSchematicData === 'function') updateSchematicData({ oxph: lastOxphVal });
      updateGaugeWidgets({ oxph: lastOxphVal });
    }
  }

  // Filter out empty series
  var filtered = seriesList.filter(function (s) { return hasChartValues(s.data); });

  // Calculate Y bounds
  var allVals = [];
  filtered.forEach(function (s) {
    s.data.forEach(function (v) { if (v != null && Number.isFinite(v)) allVals.push(v); });
  });
  var yMin = allVals.length ? Math.min(0, Math.min.apply(null, allVals) * 0.95) : 0;
  var yMax = allVals.length ? Math.ceil(Math.max.apply(null, allVals) * 1.1 * 10) / 10 : undefined;

  // Rounding helpers per view mode
  var isRiver = powerChartMode === "river";
  var isMfra = powerChartMode === "mfra";
  // OXPH: 1 decimal, MFRA: integer MW, River: integer CFS
  var unitLabel = isRiver ? ' CFS' : ' MW';
  function fmtVal(v) {
    if (v == null || !Number.isFinite(v)) return '–';
    if (isRiver || isMfra) return Math.round(v) + unitLabel;
    return v.toFixed(1) + unitLabel;
  }

  // Add day dividers to first series
  var dividers = buildDayDividers(labels);
  if (filtered.length && dividers.length) {
    filtered[0].markLine = { silent: true, symbol: 'none', label: { show: false }, data: dividers };
  }

  oxphChart.setOption({
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
      formatter: function (params) {
        if (!params || !params.length) return '';
        var header = params[0].axisValueLabel || '';
        var lines = [header];
        params.forEach(function (p) {
          if (p.value != null) {
            lines.push(p.marker + ' ' + p.seriesName + ': <b>' + fmtVal(p.value) + '</b>');
          }
        });
        return lines.join('<br/>');
      }
    },
    xAxis: { data: labels },
    yAxis: {
      name: yLabel, min: yMin, max: yMax,
      axisLabel: { formatter: function (v) { return isRiver || isMfra ? Math.round(v) : v.toFixed(1); } }
    },
    legend: { show: false },
    series: filtered
  }, { notMerge: true, lazyUpdate: animationMode === 'none' });

  renderPowerChartLegend(filtered);
}

// Add this to your initializeCharts() function after the existing charts
function initializePriceChart() {
  const dom = document.getElementById("priceChart");
  if (!dom) return;
  if (priceChart) { try { priceChart.dispose(); } catch(e) {} }
  priceChart = initEChart('priceChart');
  if (!priceChart) return;

  const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
  priceChart.setOption({
    tooltip: {
      trigger: 'axis',
      backgroundColor: isDark ? 'rgba(15, 23, 42, 0.9)' : 'rgba(255,255,255,0.95)',
      borderColor: isDark ? 'rgba(0, 212, 255, 0.3)' : '#ccc',
      textStyle: { color: isDark ? '#e2e8f0' : '#333' }
    },
    legend: {
      top: 5,
      textStyle: { color: isDark ? '#94a3b8' : '#666' }
    },
    grid: { left: 60, right: 30, top: 45, bottom: 70 },
    xAxis: {
      type: 'category',
      data: [],
      axisLabel: {
        rotate: 45,
        interval: 3,
        color: isDark ? '#94a3b8' : '#666',
        fontSize: 10
      },
      axisLine: { lineStyle: { color: isDark ? 'rgba(255,255,255,0.1)' : '#ccc' } }
    },
    yAxis: {
      type: 'value',
      name: 'Price ($/MWh)',
      nameTextStyle: { color: isDark ? '#94a3b8' : '#666' },
      axisLabel: { color: isDark ? '#94a3b8' : '#666' },
      splitLine: { lineStyle: { color: isDark ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.06)' } }
    },
    dataZoom: [
      { type: 'slider', bottom: 5, height: 20 },
      { type: 'inside' }
    ],
    series: [
      {
        name: 'Day-Ahead Price',
        type: 'line',
        data: [],
        smooth: true,
        lineStyle: { width: 2 },
        symbol: 'none'
      },
      {
        name: 'Real-Time Price',
        type: 'line',
        data: [],
        smooth: true,
        lineStyle: { width: 2 },
        symbol: 'none'
      },
      {
        name: '15-Min Price',
        type: 'line',
        data: [],
        smooth: true,
        lineStyle: { width: 1, type: 'dashed' },
        symbol: 'none'
      }
    ]
  });
}

// setupLegends() - removed: ECharts handles legends natively
function setupLegends() { /* no-op: ECharts built-in legends */ }

// updateElevationScale() - removed: handled inline in applyElevationChartData
function updateElevationScale() { /* no-op: ECharts handles axis scaling via setOption */ }

// Generate sample data for demonstration
function generateSampleData() {
  const now = new Date();

  const startTime = new Date(
    now.getFullYear(),
    now.getMonth(),
    now.getDate(),
    now.getHours(),
    0,
    0,
    0
  );
  const hourMs = 60 * 60 * 1000;

  const labels = [];

  const elevationActual = [];
  const elevationBias = [];
  const elevationOptimized = [];
  const floatLevels = [];
  const oxphHistorical = [];
  const oxphOptimized = [];
  const mfraHistorical = [];
  const mfraForecast = [];
  const r4Actual = [];
  const r4Hydro = [];
  const r4Cnrfc = [];
  const r30Actual = [];
  const r30Hydro = [];
  const r30Cnrfc = [];
  const actualMask = [];
  const forecastRows = [];

  const currentFloatLevel = 1173.0;

  for (let i = -24; i < 0; i++) {
    const date = new Date(startTime.getTime() + i * hourMs);
    const label = formatChartDateTime(date);
    labels.push(label);

    const elevation = 1170 + Math.sin(i / 12) * 2 + Math.random() * 0.5;
    const optimizedElevation = elevation + 0.25 + Math.random() * 0.15;
    const biasValue = elevation + 0.35 + Math.random() * 0.15;

    const oxphActual = Math.max(
      0,
      2.2 + Math.sin(i / 6) * 1.4 + Math.random() * 0.4
    );
    const oxphSchedule = Math.max(0, oxphActual * (0.95 + Math.random() * 0.1));

    const mfraActual = Math.round(150 + Math.random() * 20);
    const mfraPlanned = Math.round(mfraActual * (0.95 + Math.random() * 0.05));

    const r4Observed = Math.round(780 + Math.random() * 80);
    const r4HydroForecast = Math.round(
      r4Observed * (0.95 + Math.random() * 0.1)
    );
    const r4CnrfcForecast = Math.round(
      r4Observed * (0.9 + Math.random() * 0.15)
    );

    const r30Observed = Math.round(1180 + Math.random() * 120);
    const r30HydroForecast = Math.round(
      r30Observed * (0.95 + Math.random() * 0.08)
    );
    const r30CnrfcForecast = Math.round(
      r30Observed * (0.92 + Math.random() * 0.12)
    );

    const r20Observed = 620 + Math.random() * 70;
    const r5lObserved = 190 + Math.random() * 40;
    const r26Observed = 140 + Math.random() * 25;
    const modeActual = Math.abs(i) % 12 === 0 ? "SPILL" : "GEN";

    elevationActual.push(elevation);
    elevationBias.push(biasValue);
    elevationOptimized.push(optimizedElevation);
    floatLevels.push(currentFloatLevel);

    oxphHistorical.push(oxphActual);
    oxphOptimized.push(oxphSchedule);

    mfraHistorical.push(mfraActual);
    mfraForecast.push(mfraPlanned);

    r4Actual.push(r4Observed);
    r4Hydro.push(r4HydroForecast);
    r4Cnrfc.push(r4CnrfcForecast);

    r30Actual.push(r30Observed);
    r30Hydro.push(r30HydroForecast);
    r30Cnrfc.push(r30CnrfcForecast);

    actualMask.push(true);

    const setpointChange = Math.abs(i) % 6 === 0 ? date.toISOString() : null;
    forecastRows.push({
      datetime: date.toISOString(),
      setpoint: oxphSchedule,
      oxph: oxphSchedule,
      oxph_actual: oxphActual,
      setpoint_change: setpointChange,
      r4_forecast: r4HydroForecast,
      r30_forecast: r30HydroForecast,
      r4_actual: r4Observed,
      r30_actual: r30Observed,
      r4_hydro_forecast: r4HydroForecast,
      r4_cnrfc_forecast: r4CnrfcForecast,
      r30_hydro_forecast: r30HydroForecast,
      r30_cnrfc_forecast: r30CnrfcForecast,
      r20_forecast: r20Observed,
      r20_actual: r20Observed,
      r5l_forecast: r5lObserved,
      r5l_actual: r5lObserved,
      r26_forecast: r26Observed,
      r26_actual: r26Observed,
      mode_forecast: modeActual,
      mode_actual: modeActual,
      bias_cfs: 0,
      additional_bias: 0,
      abay_elevation: elevation,
      expected_abay: optimizedElevation,
      float_level: currentFloatLevel,
      mfra_forecast: mfraPlanned,
      mfra_actual: mfraActual,
    });
  }

  // Generate 4 days of forecast data
  for (let i = 0; i < 96; i++) {
    const date = new Date(startTime.getTime() + i * hourMs);
    labels.push(formatChartDateTime(date));

    const forecastElevation =
      1170 + Math.sin(i / 10) * 1.6 + Math.random() * 0.25;
    const oxphSchedule = (() => {
      const hour = date.getHours();
      if (hour >= 8 && hour <= 12) return 5.4 + Math.random() * 0.3;
      if (hour >= 6 && hour < 8)
        return 1.6 + (hour - 6) * 1.9 + Math.random() * 0.2;
      if (hour > 12 && hour <= 14)
        return 5.6 - (hour - 12) * 1.4 + Math.random() * 0.2;
      return 1.0 + Math.random() * 0.4;
    })();
    const mfraPlan = Math.round(150 + Math.random() * 40);
    const r4HydroForecast = Math.round(790 + Math.random() * 180);
    const r4CnrfcForecast = Math.round(
      r4HydroForecast * (0.95 + Math.random() * 0.1)
    );
    const r30HydroForecast = Math.round(1180 + Math.random() * 260);
    const r30CnrfcForecast = Math.round(
      r30HydroForecast * (0.94 + Math.random() * 0.1)
    );
    const r20Forecast = 640 + Math.random() * 110;
    const r5lForecast = 200 + Math.random() * 55;
    const r26Forecast = 150 + Math.random() * 35;
    const modeForecast = i % 18 === 0 ? "SPILL" : "GEN";

    elevationActual.push(null);
    elevationBias.push(null);
    elevationOptimized.push(forecastElevation);
    floatLevels.push(currentFloatLevel);

    oxphHistorical.push(null);
    oxphOptimized.push(oxphSchedule);

    mfraHistorical.push(null);
    mfraForecast.push(mfraPlan);

    r4Actual.push(null);
    r4Hydro.push(r4HydroForecast);
    r4Cnrfc.push(r4CnrfcForecast);

    r30Actual.push(null);
    r30Hydro.push(r30HydroForecast);
    r30Cnrfc.push(r30CnrfcForecast);

    actualMask.push(false);

    const setpointChange = i % 6 === 0 ? date.toISOString() : null;
    forecastRows.push({
      datetime: date.toISOString(),
      setpoint: oxphSchedule,
      oxph: oxphSchedule,
      oxph_actual: null,
      setpoint_change: setpointChange,
      r4_forecast: r4HydroForecast,
      r30_forecast: r30HydroForecast,
      r4_actual: null,
      r30_actual: null,
      r4_hydro_forecast: r4HydroForecast,
      r4_cnrfc_forecast: r4CnrfcForecast,
      r30_hydro_forecast: r30HydroForecast,
      r30_cnrfc_forecast: r30CnrfcForecast,
      r20_forecast: r20Forecast,
      r20_actual: null,
      r5l_forecast: r5lForecast,
      r5l_actual: null,
      r26_forecast: r26Forecast,
      r26_actual: null,
      mode_forecast: modeForecast,
      mode_actual: null,
      bias_cfs: 0,
      additional_bias: 0,
      abay_elevation: null,
      expected_abay: forecastElevation,
      float_level: currentFloatLevel,
      mfra_forecast: mfraPlan,
      mfra_actual: null,
    });
  }

  const chartData = {
    labels,
    elevation: {
      optimized: elevationOptimized,
      actual: elevationActual,
      bias_corrected: elevationBias,
      float: floatLevels,
    },
    oxph: {
      optimized: oxphOptimized,
      historical: oxphHistorical,
    },
    mfra: {
      forecast: mfraForecast,
      historical: mfraHistorical,
    },
    river: {
      selected_source: "hydroforecast-short-term",
      selected_source_label: "HydroForecast",
      source_labels: {
        hydro: "HydroForecast",
        cnrfc: "CNRFC Forecast",
      },
      r4: {
        actual: r4Actual,
        hydro: r4Hydro,
        cnrfc: r4Cnrfc,
      },
      r30: {
        actual: r30Actual,
        hydro: r30Hydro,
        cnrfc: r30Cnrfc,
      },
    },
    actual_mask: actualMask,
    forecast_data: forecastRows,
  };

  updateChartsWithOptimizationData(chartData);
  updateForecastTableWithData(chartData.forecast_data);
  originalData = JSON.parse(JSON.stringify(forecastData));
  currentRunId = null;
  setCurrentRunDetails(null);
  markForecastDirty(false);
  setAppliedBiasValue(null);
  actualsApplied = false;
}

// Update forecast table
function initializeForecastTable() {
  const container = document.getElementById("forecastTable");
  if (!container) {
    return;
  }

  if (!window.Handsontable) {
    console.warn(
      "Handsontable library is not available. Forecast table will not be interactive."
    );
    return;
  }

  if (forecastHot) {
    return;
  }

  const height = computeForecastTableHeight();
  forecastHot = new Handsontable(container, {
    data: [],
    colHeaders: FORECAST_TABLE_HEADERS.slice(),
    columns: FORECAST_TABLE_COLUMNS.map((column) => ({ ...column })),
    rowHeaders: false,
    stretchH: "all",
    autoColumnSize: false,
    manualColumnResize: true,
    height,
    width: "100%",
    className: "forecast-handsontable",
    fillHandle: { direction: "vertical", autoInsertRow: false },
    enterMoves: { row: 1, col: 0 },
    enterBeginsEditing: true,
    licenseKey: "non-commercial-and-evaluation",
    allowInsertRow: false,
    allowInsertColumn: false,
    multiColumnSorting: false,
    cells: forecastTableCellProperties,
    afterChange: handleForecastTableAfterChange,
  });

  window.addEventListener("resize", handleForecastTableResize);
}

function computeForecastTableHeight() {
  const container = document.getElementById("forecastTable");
  const parentHeight = container?.parentElement?.clientHeight || 0;
  if (parentHeight > 240) {
    return parentHeight - 24;
  }
  const viewport = window.innerHeight || 800;
  const desired = Math.round(viewport * 0.8);
  return Math.max(320, desired);
}

function handleForecastTableResize() {
  if (!forecastHot) {
    return;
  }
  const height = computeForecastTableHeight();
  forecastHot.updateSettings({ height });
  forecastHot.render();
}

let displayForecastData = [];
let displayToForecastIndex = [];

function forecastTableCellProperties(row, col) {
  const props = {};
  // Use displayForecastData instead of forecastData
  if (!Array.isArray(displayForecastData) || row < 0 || row >= displayForecastData.length) {
    return props;
  }

  const classes = [];

  if (forecastTableActualCount > 0) {
    if (row < forecastTableActualCount) {
      classes.push("actual-row-cell");
    } else if (row === forecastTableActualCount) {
      classes.push("forecast-divider-cell");
    }
  }

  const rowData = displayForecastData[row];
  if (isDayBoundaryRow(rowData)) {
    classes.push("day-boundary-cell");
  }

  if (classes.length) {
    props.className = classes.join(" ");
  }

  return props;
}

function updateForecastTable() {
  if (!Array.isArray(forecastData)) {
    forecastData = [];
  }

  if (!forecastHot) {
    initializeForecastTable();
  }

  if (!forecastHot) {
    return;
  }

  // Show all rows to allow scroll and editing across the full horizon
  displayForecastData = forecastData.slice();
  displayToForecastIndex = forecastData.map((_, idx) => idx);

  forecastTableActualCount = computeActualRowCutoff(displayForecastData);

  suppressForecastTableChange = true;
  forecastHot.loadData(displayForecastData);
  suppressForecastTableChange = false;
  forecastHot.render();
}

function handleForecastTableAfterChange(changes, source) {
  if (
    !changes ||
    !changes.length ||
    source === "loadData" ||
    suppressForecastTableChange
  ) {
    return;
  }

  let earliestRow = null;
  const affectedFields = new Set();

  for (const change of changes) {
    const [viewRowIndex, prop, oldValue, newValue] = change;
    
    // Map view index to real index
       const realRowIndex = displayToForecastIndex[viewRowIndex];
    if (realRowIndex === undefined) continue;

    if (!FORECAST_TABLE_EDITABLE_FIELDS.has(prop)) {
      continue;
    }
    
    const applied = applyForecastTableValue(realRowIndex, prop, newValue, oldValue);
    if (!applied) {
      continue;
    }
    
    // If setpoint changed, we might need to propagate it to hidden rows?
    // For now, let's just update the single row. 
    // If the user wants to propagate, they should probably use a "Fill Down" or we implement smart logic.
    // Given the "Clean up" request, maybe they expect it to be a "block" edit.
    // But let's be safe and just edit the point.
    
    earliestRow =
      earliestRow === null ? realRowIndex : Math.min(earliestRow, realRowIndex);
    affectedFields.add(prop);
  }

  if (earliestRow === null) {
    return;
  }

  recalculateElevation(earliestRow);
  updateCharts();
  markForecastDirty();
  
  // Re-render table to show updates (and potentially re-filter if we want dynamic updates, 
  // but re-filtering might be jarring during edit. Let's just render.)
  if (forecastHot) {
    forecastHot.render();
  }

  if (affectedFields.size) {
    const labels = Array.from(affectedFields).map(
      (field) => EDITABLE_FIELD_LABELS[field] || field
    );
    const messageLabel = labels.length === 1 ? labels[0] : "Forecast values";
    showNotification(`Updated ${messageLabel}`, "success");
  }
}

function applyForecastTableValue(rowIndex, field, rawValue, previousValue) {
  if (!Array.isArray(forecastData) || !forecastData[rowIndex]) {
    return false;
  }

  const numericValue = toFiniteNumber(rawValue);
  if (numericValue === null) {
   
    return false;
  }

  const config = EDITABLE_FIELD_CONFIG[field] || {};
  let value = numericValue;

  if (typeof config.min === "number") {
    value = Math.max(config.min, value);
  }
  if (typeof config.max === "number") {
    value = Math.min(config.max, value);
  }
  if (typeof config.decimals === "number") {
    const factor = Math.pow(10, config.decimals);
    value = Math.round(value * factor) / factor;
  }

  const row = forecastData[rowIndex];
  const previousNumeric = toFiniteNumber(previousValue);
  const noMeaningfulChange =
    previousNumeric !== null && numbersAreClose(previousNumeric, value);

  if (field === "setpoint") {
    const oxphBefore = toFiniteNumber(row.oxph);
    row.setpoint = value;
    row.oxph = value;
    if (!noMeaningfulChange) {
      return true;
    }
    return !numbersAreClose(oxphBefore, value);
  }

  if (field === "mfra") {
    row.mfra = value;
  } else if (field === "r4") {
    row.r4 = value;
  } else if (field === "r30") {
    row.r30 = value;
  } else {
    row[field] = value;
  }

  if (!noMeaningfulChange) {
    return true;
  }

  return false;
}

function computeActualRowCutoff(rows) {
  if (!Array.isArray(rows) || !rows.length) {
    return 0;
  }

  let count = 0;
  for (const row of rows) {
    if (isActualDataRow(row)) {
      count += 1;
    } else {
      break;
       }
  }
  return count;
}

function isActualDataRow(row) {
  if (!row) {
    return false;
  }
  return (
    toFiniteNumber(row.oxphActual) !== null ||
    toFiniteNumber(row.mfraActual) !== null ||
    toFiniteNumber(row.r4Actual) !== null ||
    toFiniteNumber(row.r30Actual) !== null ||
    toFiniteNumber(row.abayElevation) !== null
  );
}

function isDayBoundaryRow(rowData) {
  if (!rowData) {
    return false;
  }
  const date = toValidDate(rowData.datetime);
  if (!date) {
    return false;
  }
  return formatTableTime(date) === "12:00 AM";
}

function forecastTableDayRenderer(
  instance,
  td,
  row,
  col,
  prop,
  value,
  cellProperties
) {
  Handsontable.renderers.TextRenderer.call(
    this,
    instance,
    td,
    row,
    col,
    prop,
    value,
    cellProperties
  );
  const rowData = displayForecastData?.[row];
  const date = toValidDate(rowData?.datetime);
  td.textContent = date ? formatTableDayOfWeek(date) : "";
  td.title = date ? formatTableDateTime(date) : "";
}

function forecastTableMonthDayRenderer(
  instance,
  td,
  row,
  col,
  prop,
  value,
  cellProperties
) {
  Handsontable.renderers.TextRenderer.call(
    this,
    instance,
    td,
    row,
    col,
    prop,
    value,
    cellProperties
  );
  const rowData = displayForecastData?.[row];
  const date = toValidDate(rowData?.datetime);
  td.textContent = date ? formatTableMonthDay(date) : "";
  td.title = date ? formatTableDateTime(date) : "";
}

function forecastTableTimeRenderer(
  instance,
  td,
  row,
  col,
  prop,
  value,
  cellProperties
) {
  Handsontable.renderers.TextRenderer.call(
    this,
    instance,
    td,
    row,
    col,
    prop,
    value,
    cellProperties
  );
  const rowData = displayForecastData?.[row];
  const date = toValidDate(rowData?.datetime);
  td.textContent = date ? formatTableTime(date) : "";
  td.title = date ? formatTableDateTime(date) : "";
}

function forecastTableSetpointChangeRenderer(
  instance,
  td,
  row,
  col,
  prop,
  value,
  cellProperties
) {
  Handsontable.renderers.TextRenderer.call(
    this,
    instance,
    td,
    row,
    col,
    prop,
    value,
    cellProperties
  );
  const rawDate = displayForecastData?.[row]?.setpointChange;
  const date = toValidDate(rawDate);
  td.textContent = date ? formatTableTime(date) : "";
  td.title = date ? formatTableDateTime(date) : "";
}

function forecastDateTimeRenderer(
  instance,
  td,
  row,
  col,
  prop,
  value,
  cellProperties
) {
  Handsontable.renderers.TextRenderer.call(
    this,
    instance,
    td,
    row,
    col,
    prop,
    value,
    cellProperties
  );
  const raw = displayForecastData?.[row]?.datetime ?? value;
  const date = toValidDate(raw);
  td.textContent = date ? formatForecastDateTime(date) : "";
  td.title = date ? formatTableDateTime(date) : "";
}

// Recalculate elevation based on MFRA/OXPH changes
function recalculateElevation(startIndex = 0) {
  if (!Array.isArray(forecastData) || !forecastData.length) {
    return;
  }

  const length = forecastData.length;
  const parsedIndex = Number.parseInt(startIndex, 10);
  const normalizedStart = Math.min(
    Math.max(Number.isFinite(parsedIndex) ? parsedIndex : 0, 0),
    length - 1
  );

  let seedRowIndex = Math.max(0, normalizedStart - 1);
  let seedElevation = null;

  for (let idx = seedRowIndex; idx >= 0; idx--) {
    const row = forecastData[idx];
    const expectedValue = toFiniteNumber(row?.elevation);
    if (expectedValue !== null) {
      seedElevation = expectedValue;
      seedRowIndex = idx;
      break;
    }
    const actualValue = toFiniteNumber(row?.abayElevation);
    if (actualValue !== null) {
      seedElevation = actualValue;
      seedRowIndex = idx;
      break;
    }
  }

  if (seedElevation === null) {
    const firstRow = forecastData[0] || {};
    const fallbackExpected = toFiniteNumber(firstRow.elevation);
    const fallbackActual = toFiniteNumber(firstRow.abayElevation);
    seedElevation = fallbackExpected ?? fallbackActual ?? 1170;
    seedRowIndex = 0;
  }

  let currentAf = abayFeetToAf(seedElevation);
  if (!Number.isFinite(currentAf)) {
    const fallbackAf = abayFeetToAf(1170);
    currentAf = Number.isFinite(fallbackAf) ? fallbackAf : 0;
    const fallbackFt = abayAfToFeet(currentAf);
    seedElevation = Number.isFinite(fallbackFt) ? fallbackFt : 1170;
  }

  const expectedSeries = new Array(length);

  for (let i = 0; i <= seedRowIndex && i < length; i++) {
    const row = forecastData[i];
    const expectedValue = toFiniteNumber(row?.elevation);
    const actualValue = toFiniteNumber(row?.abayElevation);
    const value = expectedValue ?? actualValue ?? seedElevation;
    row.elevation = value;
    expectedSeries[i] = value;
  }

  for (let i = seedRowIndex + 1; i < length; i++) {
    const row = forecastData[i];
    const biasValue = getBiasForRow(row);
    const biasCfs = Number.isFinite(biasValue) ? biasValue : 0;
    const netInputs = {
      r30: chooseFlowValue(row, "r30Actual", "r30"),
      r4: chooseFlowValue(row, "r4Actual", "r4"),
      r20: chooseFlowValue(row, "r20Actual", "r20"),
      r5l: chooseFlowValue(row, "r5lActual", "r5l"),
      r26: chooseFlowValue(row, "r26Actual", "r26"),
      oxph: chooseFlowValue(row, "oxphActual", "oxph"),
      mfra: chooseFlowValue(row, "mfraActual", "mfra"),
      mode: resolveRowMode(row),
    };

    const netCfs = computeNetAbayCfs(netInputs);
    currentAf += (netCfs + biasCfs) * ABAY_MATH.AF_PER_CFS_HOUR;
    const expectedFt = abayAfToFeet(currentAf);
    if (Number.isFinite(expectedFt)) {
      row.elevation = expectedFt;
      expectedSeries[i] = expectedFt;
    } else {
      const preserved = toFiniteNumber(row.elevation);
      expectedSeries[i] = preserved !== null ? preserved : null;
    }
  }

  syncChartDataWithExpectedSeries(expectedSeries);
}

// Update charts after data changes
function updateCharts() {
  if (!latestChartData || !forecastData || !forecastData.length) {
    return;
  }
  const labelCount = latestChartData.labels.length;

  if (forecastData.length === labelCount) {
    latestChartData.elevation.optimized = forecastData.map(
      (row) => row.elevation ?? null
    );
    latestChartData.elevation.float = forecastData.map(
      (row) => row.floatLevel ?? latestChartData.elevation.float?.[0] ?? null
    );
    latestChartData.oxph.optimized = forecastData.map(
      (row) => row.oxph ?? null
    );
    latestChartData.oxph.historical = forecastData.map(
      (row) => row.oxphActual ?? null
    );
    latestChartData.mfra.forecast = forecastData.map((row) => row.mfra ?? null);
    latestChartData.mfra.historical = forecastData.map(
      (row) => row.mfraActual ?? null
    );
    latestChartData.river.r4.actual = forecastData.map(
      (row) => row.r4Actual ?? null
    );
    latestChartData.river.r30.actual = forecastData.map(
      (row) => row.r30Actual ?? null
    );
    latestChartData.river.r4.hydro = forecastData.map((row) => row.r4 ?? null);
    latestChartData.river.r30.hydro = forecastData.map(
      (row) => row.r30 ?? null
    );
    latestChartData.actual_mask = forecastData.map(
      (row) =>
        row.oxphActual !== null ||
        row.mfraActual !== null ||
        row.r4Actual !== null ||
        row.r30Actual !== null ||
        row.abayElevation !== null
    );
  }

  applyElevationChartData(latestChartData, "none");
  refreshPowerChart("none");
}

// Apply actual values to forecast columns for past hours
function applyActuals(options = {}) {
  const { silent = false } = options;
  if (!Array.isArray(forecastData) || !forecastData.length) {
    if (!silent) {
      showNotification(
        "No forecast data available to apply actuals.",
        "warning"
      );
    }
    return;
  }

  forecastData.forEach((row) => {
    const mfraActual = toRoundedInteger(row.mfraActual);
    if (mfraActual !== null) {
      row.mfraActual = mfraActual;
      row.mfra = mfraActual;
    }

    const oxphActual = toFiniteNumber(row.oxphActual);
    if (oxphActual !== null) row.oxph = oxphActual;

    const r4Actual = toRoundedInteger(row.r4Actual);
    if (r4Actual !== null) {
      row.r4Actual = r4Actual;
      row.r4 = r4Actual;
    }

    const r30Actual = toRoundedInteger(row.r30Actual);
    if (r30Actual !== null) {
      row.r30Actual = r30Actual;
      row.r30 = r30Actual;
    }

    const r20Actual = toFiniteNumber(row.r20Actual);
    if (r20Actual !== null) row.r20 = r20Actual;

    const r5lActual = toFiniteNumber(row.r5lActual);
    if (r5lActual !== null) row.r5l = r5lActual;

    const r26Actual = toFiniteNumber(row.r26Actual);
    if (r26Actual !== null) row.r26 = r26Actual;

    const modeActual = normalizeModeValue(row.modeActual);
    if (modeActual) row.mode = modeActual;
  });

  let startIndex = forecastData.findIndex(
    (row) => toFiniteNumber(row.abayElevation) !== null
  );
  if (startIndex === -1) {
    startIndex = 0;
  }

  const seedRow = forecastData[startIndex] || forecastData[0];
  let seedElevation = toFiniteNumber(seedRow?.abayElevation);
  if (seedElevation === null) {
    seedElevation = toFiniteNumber(seedRow?.elevation);
  }
  if (seedElevation === null) {
    seedElevation = 1170;
  }

  let currentAf = abayFeetToAf(seedElevation);
  if (!Number.isFinite(currentAf)) {
    currentAf = abayFeetToAf(1170) ?? 0;
  }

  const expectedSeries = new Array(forecastData.length).fill(seedElevation);

  for (let i = 0; i < forecastData.length; i++) {
    const row = forecastData[i];
    const biasRaw = getBiasForRow(row);
    const biasCfsValue = Number.isFinite(biasRaw) ? biasRaw : 0;
    row.biasCfs = biasRaw;
    row.additionalBias = biasRaw;

    if (i < startIndex) {
      const preserved = toFiniteNumber(row.elevation) ?? seedElevation;
      row.elevation = preserved;
      expectedSeries[i] = preserved;
      continue;
    }

    if (i === startIndex) {
      row.elevation = seedElevation;
      expectedSeries[i] = seedElevation;
      continue;
    }

    const netInputs = {
      r30: chooseFlowValue(row, "r30Actual", "r30"),
      r4: chooseFlowValue(row, "r4Actual", "r4"),
      r20: chooseFlowValue(row, "r20Actual", "r20"),
      r5l: chooseFlowValue(row, "r5lActual", "r5l"),
      r26: chooseFlowValue(row, "r26Actual", "r26"),
      oxph: chooseFlowValue(row, "oxphActual", "oxph"),
      mfra: chooseFlowValue(row, "mfraActual", "mfra"),
      mode: resolveRowMode(row),
    };

    const netCfs = computeNetAbayCfs(netInputs);
    currentAf += (netCfs + biasCfsValue) * ABAY_MATH.AF_PER_CFS_HOUR;
    const expectedFt = abayAfToFeet(currentAf);
    row.elevation = Number.isFinite(expectedFt) ? expectedFt : row.elevation;
    expectedSeries[i] = row.elevation;
  }

  syncChartDataWithExpectedSeries(expectedSeries);
  updateForecastTable();
  updateCharts();
  markForecastDirty();
  actualsApplied = true;
  if (!silent) {
    showNotification("Applied actual values to forecast", "success");
  }
}

function syncChartDataWithExpectedSeries(expectedSeries) {
  if (!Array.isArray(expectedSeries) || !expectedSeries.length) {
    return;
  }
  if (!latestChartData) {
    return;
  }

  const normalizedSeries = expectedSeries.map((value) => toFiniteNumber(value));
  const length = normalizedSeries.length;

  const chartLength = Array.isArray(latestChartData.labels)
    ? latestChartData.labels.length
    : length;
  if (chartLength !== length) {
    return;
  }

  if (!latestChartData.elevation) {
    latestChartData.elevation = {};
  }

  latestChartData.elevation.bias_corrected = normalizedSeries.slice();
  if (
    !Array.isArray(latestChartData.elevation.optimized) ||
    latestChartData.elevation.optimized.length !== length
  ) {
    latestChartData.elevation.optimized = normalizedSeries.slice();
  }

  if (
    Array.isArray(latestChartData.forecast_data) &&
    latestChartData.forecast_data.length === length
  ) {
    latestChartData.forecast_data = latestChartData.forecast_data.map(
      (entry, idx) => {
        const expectedValue = normalizedSeries[idx];
        const biasValue = toFiniteNumber(
          forecastData[idx]?.additionalBias ?? forecastData[idx]?.biasCfs
        );
        return {
          ...entry,
          expected_abay:
            expectedValue !== null
              ? expectedValue
              : entry.expected_abay ?? null,
          additional_bias:
            biasValue !== null ? biasValue : entry.additional_bias ?? null,
          bias_cfs: biasValue !== null ? biasValue : entry.bias_cfs ?? null,
        };
      }
    );
  }
}

function resetForecast() {
  const baselineChartData = currentOptimizationData?.chart_data;
  const summaryBias = currentOptimizationData?.summary?.r_bias_cfs;

  if (baselineChartData && baselineChartData.forecast_data) {
    updateChartsWithOptimizationData(baselineChartData);
    updateForecastTableWithData(baselineChartData.forecast_data);

    const baselineBias = deriveBiasFromChartData(
      baselineChartData,
      summaryBias
    );
    if (baselineBias !== null) {
      setAppliedBiasValue(baselineBias);
    } else if (summaryBias !== undefined) {
      setAppliedBiasValue(summaryBias);
    }
  } else if (Array.isArray(originalData) && originalData.length) {
    forecastData = JSON.parse(JSON.stringify(originalData));
    updateForecastTable();
    updateCharts();
  } else {
    updateForecastTable();
    updateCharts();
  }

  actualsApplied = false;
  markForecastDirty(false);
  showNotification("Forecast reset to loaded values", "info");
}

// Save edited forecast as new optimization run
async function saveForecastChanges() {
  await saveEditedOptimization();
}

async function saveEditedOptimization() {
  if (!forecastDirty && currentRunId !== null) {
    showNotification("No changes detected to save.", "info");
    return;
  }
  try {
    const payload = {
      source_run_id: currentRunId,
      forecast_data: forecastData.map((entry) => ({
        datetime:
          entry.datetime instanceof Date
            ? entry.datetime.toISOString()
            : entry.datetime,
        setpoint: entry.setpoint,
        oxph: entry.oxph,
        r4: entry.r4,
        r30: entry.r30,
        mfra: entry.mfra,
        abay_elevation: entry.abayElevation,
        expected_abay: entry.elevation,
        float_level: entry.floatLevel,
        r4_actual: entry.r4Actual,
        r30_actual: entry.r30Actual,
        mfra_actual: entry.mfraActual,
        oxph_actual: entry.oxphActual,
      })),
    };

    showNotification("Saving manual optimization run...", "info");
    const response = await apiCall("/api/optimization-runs/save-edited/", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCsrfToken(),
      },
      body: JSON.stringify(payload),
    });
    showNotification("Manual optimization run saved successfully.", "success");

    if (response.run_id) {
      currentRunId = response.run_id;
      setCurrentRunDetails(response.run || null);
      if (response.chart_data && response.chart_data.labels) {
        currentOptimizationData = response;
        updateChartsWithOptimizationData(response.chart_data);
        updateForecastTableWithData(response.chart_data.forecast_data);
      } else {
        await loadOptimizationResults(response.run_id);
      }
    }

    originalData = JSON.parse(JSON.stringify(forecastData));
    markForecastDirty(false);
  } catch (error) {
    console.error("Failed to save edited optimization:", error);
    showNotification("Failed to save optimization: " + error.message, "error");
  }
}

// Ensure setpoint modal structure exists (for pages missing the template markup)
function ensureSetpointModal() {
  if (!document.getElementById("modalBackdrop")) {
    const backdrop = document.createElement("div");
    backdrop.id = "modalBackdrop";
    backdrop.className = "modal-backdrop hidden";
    document.body.appendChild(backdrop);
  }
  if (!document.getElementById("setpointModal")) {
    const modal = document.createElement("div");
    modal.id = "setpointModal";
    modal.className = "modal hidden";
    modal.setAttribute("role", "dialog");
    modal.setAttribute("aria-modal", "true");
    modal.setAttribute("aria-labelledby", "setpointModalTitle");
    modal.innerHTML = `
            <div class="modal-header">
                <h3 id="setpointModalTitle">Update OXPH Setpoint</h3>
                <button class="close-btn" onclick="closeSetpointModal()" aria-label="Close">&times;</button>
            </div>
            <div class="progress"><div class="progress-bar" id="setpointProgress"></div></div>
            <form id="setpointForm">
                <div class="step active" data-step="1">
                    <div class="form-group-floating">
                        <input type="number" id="setpointInput" placeholder=" " aria-label="New setpoint" required>
                        <label for="setpointInput">New Setpoint (MW)</label>
                        <div class="error-msg" id="setpointError"></div>
                    </div>
                    <div class="actions">
                        <button type="button" class="btn btn-secondary" onclick="closeSetpointModal()">Cancel</button>
                        <button type="button" class="btn" onclick="nextSetpointStep()">Next</button>
                    </div>
                </div>
                <div class="step" data-step="2">
                    <div class="form-group-floating">
                        <input type="datetime-local" id="setpointStart" placeholder=" " aria-label="Start time" required>
                        <label for="setpointStart">Start Time</label>
                        <div class="error-msg" id="startError"></div>
                    </div>
                    <div class="form-group-floating">
                        <input type="datetime-local" id="setpointEnd" placeholder=" " aria-label="End time" required>
                        <label for="setpointEnd">End Time</label>
                        <div class="error-msg" id="endError"></div>
                    </div>
                    <div class="actions">
                        <button type="button" class="btn btn-secondary" onclick="prevSetpointStep()">Back</button>
                        <button type="button" class="btn" onclick="submitSetpointForm()">Save</button>
                    </div>
                </div>
            </form>
        `;
    document.body.appendChild(modal);
  }
}

// Accessible modal to modify OXPH setpoint and adjust generation
function formatDateTimeLocal(date) {
  if (!(date instanceof Date)) {
    date = new Date(date);
  }
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  const tzOffset = date.getTimezoneOffset() * 60000;
  const local = new Date(date.getTime() - tzOffset);
  return local.toISOString().slice(0, 16);
}

function openSetpointModal(rowIndex) {
  editingRowIndex = rowIndex;
  const row = forecastData[rowIndex];
  lastFocusedElement = document.activeElement;

  ensureSetpointModal();

  const modal = document.getElementById("setpointModal");
  const backdrop = document.getElementById("modalBackdrop");
  const setpointInput = document.getElementById("setpointInput");
  const startInput = document.getElementById("setpointStart");
  const endInput = document.getElementById("setpointEnd");

  if (!modal || !backdrop || !setpointInput || !startInput || !endInput) {
    console.warn("Setpoint modal elements missing");
    return;
  }

  const baseDate =
    row.datetime instanceof Date ? row.datetime : new Date(row.datetime);
  const validBaseDate = Number.isNaN(baseDate.getTime())
    ? new Date()
    : baseDate;
  const defaultEnd = new Date(validBaseDate.getTime() + 4 * 3600000);

  setpointInput.value = (row.setpoint ?? row.oxph).toFixed(1);
  startInput.value = formatDateTimeLocal(validBaseDate);
  endInput.value = formatDateTimeLocal(defaultEnd);

  showSetpointStep(1);

  modal.classList.remove("hidden");
  backdrop.classList.remove("hidden");
  modal.classList.add("active");
  backdrop.classList.add("active");
  trapFocus(modal);
}

function closeSetpointModal() {
  const modal = document.getElementById("setpointModal");
  const backdrop = document.getElementById("modalBackdrop");
  modal.classList.add("hidden");
  backdrop.classList.add("hidden");
  modal.classList.remove("active");
  backdrop.classList.remove("active");
  releaseFocus("setpointModal");
  if (lastFocusedElement) lastFocusedElement.focus();
  pendingSetpointChange = null;
}

let setpointStep = 1;
function showSetpointStep(step) {
  setpointStep = step;
  const steps = document.querySelectorAll("#setpointForm .step");
  steps.forEach((s, i) => s.classList.toggle("active", i === step - 1));
  document.getElementById("setpointProgress").style.width =
    step === 1 ? "50%" : "100%";
}

function nextSetpointStep() {
  const input = document.getElementById("setpointInput");
  const error = document.getElementById("setpointError");
  const val = parseFloat(input.value);
  if (isNaN(val)) {
    error.textContent = "Enter a numeric setpoint";
    return;
  }
  error.textContent = "";
  showSetpointStep(2);
}

function prevSetpointStep() {
  showSetpointStep(1);
}

async function submitSetpointForm() {
  const setpointVal = parseFloat(
    document.getElementById("setpointInput").value
  );
  const startVal = document.getElementById("setpointStart").value;
  const endVal = document.getElementById("setpointEnd").value;
  const startError = document.getElementById("startError");
  const endError = document.getElementById("endError");

  let valid = true;
  if (!startVal) {
    startError.textContent = "Required";
    valid = false;
  } else startError.textContent = "";
  if (!endVal) {
    endError.textContent = "Required";
    valid = false;
  } else endError.textContent = "";

  const start = new Date(startVal);
  const end = new Date(endVal);
  if (start >= end) {
    endError.textContent = "End must be after start";
    valid = false;
  }
  if (isNaN(setpointVal)) {
    document.getElementById("setpointError").textContent =
      "Enter a numeric setpoint";
    valid = false;
  }
  if (!valid) return;

  let currentMW = forecastData[editingRowIndex].oxph;
  const ramp = 1.5; // MW per hour
  const changeRequest = { setpointVal, start, end };
  const raftingConflict = await checkRaftingConflict(changeRequest);

  if (raftingConflict && raftingConflict.conflict) {
    pendingSetpointChange = changeRequest;
    showRaftingWarning(raftingConflict);
    return;
  }

  applySetpointChange(changeRequest);
}

function applySetpointChange({ setpointVal, start, end }) {
  let currentMW = forecastData[editingRowIndex].oxph;
  const ramp = 1.5; // MW per hour
  forecastData.forEach((r) => {
    if (r.datetime >= start && r.datetime <= end) {
      const diff = setpointVal - currentMW;
      const step = Math.sign(diff) * Math.min(Math.abs(diff), ramp);
      currentMW += step;
      r.setpoint = setpointVal;
      r.oxph = Math.max(0, Math.min(5.8, currentMW));
      r.setpointChange = start;
    }
  });

  recalculateElevation(editingRowIndex);
  updateForecastTable();
  updateCharts();
  markForecastDirty();
  closeSetpointModal();
  showNotification("Setpoint updated", "success");
}

async function ensureRaftingData() {
  if (currentRaftingData) {
    return currentRaftingData;
  }
  try {
    currentRaftingData = await apiCall("/api/rafting-times/");
  } catch (error) {
    console.warn("Unable to fetch rafting schedule:", error);
    currentRaftingData = null;
  }
  return currentRaftingData;
}

async function checkRaftingConflict({ setpointVal, start, end }) {
  const raftingData = await ensureRaftingData();
  if (!raftingData) {
    return null;
  }

  const targetMw = raftingData?.ramp_settings?.target_mw ?? 5.8;
  if (setpointVal >= targetMw - 0.05) {
    return null;
  }

  const startDetails = getRaftingDayDetails(start, raftingData);
  if (
    !startDetails ||
    !startDetails.dayInfo ||
    !startDetails.dayInfo.has_rafting
  ) {
    return null;
  }

  const { dayInfo, dayLabel } = startDetails;
  if (!dayInfo.start_time || !dayInfo.end_time) {
    return null;
  }

  const startPt = convertToPacific(start);
  const endPt = convertToPacific(end);

  const startMinutes = getMinutesFromDate(startPt);
  const endMinutes = getMinutesFromDate(endPt);
  const raftingStart = timeStringToMinutes(dayInfo.start_time);
  const raftingEnd = timeStringToMinutes(dayInfo.end_time);

  const overlaps = startMinutes <= raftingEnd && endMinutes >= raftingStart;

  if (!overlaps) {
    return null;
  }

  return {
    conflict: true,
    dayInfo,
    dayLabel,
    targetMw,
  };
}

function getRaftingDayDetails(date, raftingData) {
  const pacificDate = convertToPacific(date);
  const dateKey = formatDateToYMD(pacificDate);

  if (raftingData.today && raftingData.today.date === dateKey) {
    return { dayInfo: raftingData.today, dayLabel: "today" };
  }

  if (raftingData.tomorrow && raftingData.tomorrow.date === dateKey) {
    return { dayInfo: raftingData.tomorrow, dayLabel: "tomorrow" };
  }

  return null;
}

function convertToPacific(date) {
  return new Date(date.toLocaleString("en-US", { timeZone: PACIFIC_TIMEZONE }));
}

function formatDateToYMD(date) {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: PACIFIC_TIMEZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(date);
}

function getMinutesFromDate(date) {
  return date.getHours() * 60 + date.getMinutes();
}

function timeStringToMinutes(value) {
  if (!value) return 0;
  const [hours, minutes] = value.split(":").map(Number);
  return (hours || 0) * 60 + (minutes || 0);
}

function showRaftingWarning(conflictDetails) {
  const modal = document.getElementById("raftingWarningModal");
  const backdrop = document.getElementById("raftingWarningBackdrop");
  if (!modal || !backdrop) return;

  const messageElement = document.getElementById("raftingWarningMessage");
  if (messageElement && conflictDetails) {
    const { dayInfo, dayLabel, targetMw } = conflictDetails;
    const label = dayLabel
      ? `${dayLabel.charAt(0).toUpperCase()}${dayLabel.slice(1)}`
      : "the selected day";
    const windowLabel =
      dayInfo.start_time && dayInfo.end_time
        ? `${dayInfo.start_time} - ${dayInfo.end_time} PT`
        : "the scheduled rafting window";
    messageElement.textContent = `The requested setpoint is below the rafting target of ${targetMw.toFixed(
      1
    )} MW during ${label}'s rafting window (${windowLabel}). Do you want to continue?`;
  }

  modal.classList.remove("hidden");
  backdrop.classList.remove("hidden");
  modal.classList.add("active");
  backdrop.classList.add("active");
  trapFocus(modal);
}

function cancelRaftingWarning(keepPending = false) {
  const modal = document.getElementById("raftingWarningModal");
  const backdrop = document.getElementById("raftingWarningBackdrop");
  if (!modal || !backdrop) return;

  modal.classList.add("hidden");
  backdrop.classList.add("hidden");
  modal.classList.remove("active");
  backdrop.classList.remove("active");
  releaseFocus("raftingWarningModal");
  if (!keepPending) {
    pendingSetpointChange = null;
  }
}

function confirmRaftingWarning() {
  const change = pendingSetpointChange;
  cancelRaftingWarning(true);
  if (change) {
    pendingSetpointChange = null;
    applySetpointChange(change);
  }
}

function trapFocus(modal) {
  const focusable = modal.querySelectorAll(
    'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
  );
  if (!focusable.length) return;
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  function handle(e) {
    if (e.key !== "Tab") return;
    if (e.shiftKey) {
      if (document.activeElement === first) {
        e.preventDefault();
        last.focus();
      }
    } else {
      if (document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }
  }
  modal._trapHandler = handle;
  modal.addEventListener("keydown", handle);
  first.focus();
}

function releaseFocus(modalId = "setpointModal") {
  const modal = document.getElementById(modalId);
  if (modal && modal._trapHandler) {
    modal.removeEventListener("keydown", modal._trapHandler);
    modal._trapHandler = null;
  }
}

document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape") return;

  const setpointModal = document.getElementById("setpointModal");
  const runModal = document.getElementById("runHistoryModal");
  const raftingModal = document.getElementById("raftingWarningModal");

  if (setpointModal && !setpointModal.classList.contains("hidden")) {
    closeSetpointModal();
  } else if (runModal && !runModal.classList.contains("hidden")) {
    closeRunHistoryModal();
  } else if (raftingModal && !raftingModal.classList.contains("hidden")) {
    cancelRaftingWarning();
    closeSetpointModal();
  }
});

function formatTableDayOfWeek(date) {
  const valid = toValidDate(date);
  return valid ? TABLE_DAY_FORMATTER.format(valid) : "";
}

function formatTableMonthDay(date) {
  const valid = toValidDate(date);
  return valid ? TABLE_MONTH_DAY_FORMATTER.format(valid) : "";
}

function formatTableTime(date) {
  const valid = toValidDate(date);
  return valid ? TABLE_TIME_FORMATTER.format(valid) : "";
}

function formatTableSetpointChange(date) {
  const valid = toValidDate(date);
  return valid ? TABLE_DATE_TIME_FORMATTER.format(valid) : "";
}

function formatTableDate(date) {
  return formatTableDateTime(date);
}

function formatTableDateTime(date) {
  const valid = toValidDate(date);
  return valid ? TABLE_DATE_TIME_FORMATTER.format(valid) : "";
}

function formatForecastDateTime(date) {
  const valid = toValidDate(date);
  if (!valid) return "";

  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: PACIFIC_TIMEZONE,
    weekday: "short",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).formatToParts(valid);

  const lookup = (type) => parts.find((p) => p.type === type)?.value || "";
  const weekday = lookup("weekday");
  const month = lookup("month");
  const day = lookup("day");
  const hour = lookup("hour");
  const minute = lookup("minute");

  return `${weekday} ${month} ${day} ${hour}:${minute}`;
}

function toValidDate(value) {
  if (value instanceof Date && !Number.isNaN(value.getTime())) {
    return value;
  }
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

// Toggle historical date input
function toggleHistoricalDate() {
  const runMode = document.getElementById("runMode");
  const historicalGroup = document.getElementById("historicalDateGroup");

  if (!runMode || !historicalGroup) return;

  if (runMode.value === "historical") {
    historicalGroup.classList.remove("hidden");
  } else {
    historicalGroup.classList.add("hidden");
  }
}

// Set default dates
function setDefaultDates() {
  const today = new Date();
  const yesterday = new Date(today);
  yesterday.setDate(yesterday.getDate() - 1);

  const weekAgo = new Date(today);
  weekAgo.setDate(weekAgo.getDate() - 7);

  const historicalDateInput = document.getElementById("historicalDate");
  const historyStartInput = document.getElementById("historyStartDate");
  const historyEndInput = document.getElementById("historyEndDate");

  if (historicalDateInput) {
    historicalDateInput.value = yesterday.toISOString().split("T")[0];
  }
  if (historyStartInput) {
    historyStartInput.value = weekAgo.toISOString().split("T")[0];
  }
  if (historyEndInput) {
    historyEndInput.value = today.toISOString().split("T")[0];
  }
}

const OPTIMIZATION_PROGRESS_STEPS = [
  {
    id: "fetch-data",
    threshold: 5,
    keywords: ["fetching pi data", "fetch pi data"],
  },
  {
    id: "load-forecast",
    threshold: 20,
    keywords: ["loading forecast data", "load forecast data"],
  },
  {
    id: "setup-optimization",
    threshold: 40,
    keywords: ["setting up optimization", "set up optimization"],
  },
  {
    id: "solve-optimization",
    threshold: 60,
    keywords: ["solving optimization", "solve optimization"],
  },
  {
    id: "recalculate-state",
    threshold: 80,
    keywords: ["recalculating state", "recalculate state"],
  },
  {
    id: "finalize-results",
    threshold: 95,
    keywords: [
      "finalizing results",
      "finalize results",
      "completed successfully",
    ],
  },
];

function getOptimizationProgressElements() {
  const stepsContainer = document.getElementById("optimizationProgressSteps");
  const progressSteps = stepsContainer
    ? Array.from(stepsContainer.querySelectorAll(".progress-step"))
    : [];
  const progressLine = document.getElementById("optimizationProgressLine");
  return { steps: progressSteps, line: progressLine };
}

function updateOptimizationProgressStatus(message) {
  const srStatus = document.getElementById("optimizationProgressStatus");
  if (!srStatus) {
    return;
  }

  if (typeof message === "string" && message.trim()) {
    srStatus.textContent = message;
  }
}

function resetOptimizationProgress() {
  const { steps, line } = getOptimizationProgressElements();
  steps.forEach((step, index) => {
    step.classList.remove("completed", "failed", "active");
    if (index === 0) {
      step.classList.add("active");
    }
  });

  if (line) {
    line.classList.remove("failed");
    line.style.width = "0%";
  }

  updateOptimizationProgressStatus("Starting optimization...");
}

function getStepIndexFromMessage(message) {
  if (!message) {
    return -1;
  }

  const normalized = message.toLowerCase();
  return OPTIMIZATION_PROGRESS_STEPS.findIndex((step) =>
    step.keywords.some((keyword) => normalized.includes(keyword))
  );
}

function updateOptimizationProgress(progressPercentage, message) {
  const { steps, line } = getOptimizationProgressElements();

  if (!steps.length) {
    updateOptimizationProgressStatus(message);
    return;
  }

  const hasNumericProgress =
    typeof progressPercentage === "number" && !Number.isNaN(progressPercentage);
  const normalizedProgress = hasNumericProgress
    ? Math.max(0, Math.min(progressPercentage, 100))
    : null;

  let targetIndex = 0;

  if (normalizedProgress !== null) {
    OPTIMIZATION_PROGRESS_STEPS.forEach((step, index) => {
      if (normalizedProgress >= step.threshold) {
        targetIndex = index;
      }
    });

    if (normalizedProgress >= 100) {
      targetIndex = steps.length - 1;
    }
  }

  const messageIndex = getStepIndexFromMessage(message || "");
  if (messageIndex !== -1) {
    targetIndex = Math.max(targetIndex, messageIndex);
  }

  steps.forEach((stepEl, index) => {
    stepEl.classList.toggle("completed", index < targetIndex);
    stepEl.classList.toggle("active", index === targetIndex);

    if (index > targetIndex) {
      stepEl.classList.remove("active");
    }

    stepEl.classList.remove("failed");
  });

  if (line && steps.length > 1) {
    line.classList.remove("failed");

    let width = (targetIndex / (steps.length - 1)) * 100;

    if (normalizedProgress !== null) {
      width = Math.max(width, normalizedProgress);
    }

    if (message && message.toLowerCase().includes("completed")) {
      width = 100;
    }

    line.style.width = `${Math.min(100, Math.max(0, width))}%`;
  }

  if (message) {
    updateOptimizationProgressStatus(message);
  }
}

function setOptimizationProgressComplete(message) {
  const { steps, line } = getOptimizationProgressElements();

  steps.forEach((step) => {
    step.classList.remove("failed", "active");
    step.classList.add("completed");
  });

  if (line) {
    line.classList.remove("failed");
    line.style.width = "100%";
  }

  if (message) {
    updateOptimizationProgressStatus(message);
  }
}

function markOptimizationFailed(message) {
  const { steps, line } = getOptimizationProgressElements();

  const activeIndex = steps.findIndex((step) =>
    step.classList.contains("active")
  );
  const failureIndex = activeIndex !== -1 ? activeIndex : steps.length - 1;

  if (failureIndex >= 0 && failureIndex < steps.length) {
    steps[failureIndex].classList.add("failed");
  }

  if (line) {
    line.classList.add("failed");
  }

  if (message) {
    updateOptimizationProgressStatus(message);
  }
}

// Run optimization with proper API integration
// Replace the entire runOptimization function with this:

async function runOptimization() {
  const btn = document.getElementById("optimizeBtn");
  const btnText = document.getElementById("optimizeText");
  const loadingOverlay = document.getElementById("loadingOverlay");
  const loadingMessage = document.getElementById("loadingMessage");

  // Close modal if open
  closeRunOptimizationModal();

  if (!btn || !btnText || !loadingOverlay || !loadingMessage) {
    console.error("Required elements not found for optimization");
    return;
  }

  // Disable button and show loading
  btn.disabled = true;
  btnText.textContent = "Running...";
  resetOptimizationProgress();
  loadingOverlay.classList.remove("hidden");

  try {
    // Read form values from MODAL with safe fallbacks
    const runMode = document.getElementById("modal_runMode")?.value || "forecast";
    const forecastSource =
      document.getElementById("modal_forecastSource")?.value ||
      "hydroforecast-short-term";
    const historicalDate =
      document.getElementById("modal_historicalDate")?.value || "";

    // Advanced parameters from modal
    const abayMinElevation = parseFloat(document.getElementById("modal_abayMinElevation")?.value || "1168.0");
    const abayMaxElevationBuffer = parseFloat(document.getElementById("modal_abayMaxElevationBuffer")?.value || "0.3");
    const oxphMinMW = parseFloat(document.getElementById("modal_oxphMinMW")?.value || "0.8");

    // Keep existing parameters from the other tab if they still exist, or use defaults
    const enableSmoothing =
      document.getElementById("enableSmoothing")?.checked ?? true;
    const avoidSpill =
      document.getElementById("avoidSpillToggle")?.checked ?? true;
    const smoothOperation = parseInt(
      document.getElementById("prioritySmoothOperation")?.value || "3",
      10
    );
    const midpointElevation = parseInt(
      document.getElementById("priorityMidpointElevation")?.value || "4",
      10
    );
    const enableMidpoint =
      document.getElementById("enableMidpoint")?.checked ?? true;
    const smoothingWeight = enableSmoothing
      ? parseFloat(document.getElementById("smoothingWeight")?.value || "100")
      : 0;

    // Collect form data
    const optimizationParams = {
      runMode,
      forecastSource,
      historicalDate,

      // Add optimization settings
      optimizationSettings: {
        avoidSpill,
        smoothOperation,
        midpointElevation,
        enableSmoothing,
        enableMidpoint,
        smoothingWeight,
        
        // New advanced params
        abayMinElevation,
        abayMaxElevationBuffer,
        oxphMinMW
      },
    };

    loadingMessage.textContent = "Starting optimization...";
    updateOptimizationProgress(0, "Starting optimization...");

    // Start optimization via API
    const response = await fetch("/api/run-optimization/", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCsrfToken(),
      },
      body: JSON.stringify(optimizationParams),
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const result = await response.json();

    if (result.error) {
      throw new Error(result.error);
    }

    // Poll for progress updates
    const taskId = result.task_id;
    await pollOptimizationProgress(taskId, loadingMessage);

    // DON'T generate sample data - the real data should already be loaded
    // by pollOptimizationProgress -> loadOptimizationResults

    showNotification("Optimization completed successfully!", "success");

    // Switch to dashboard tab to show results
    switchTab("dashboard", null);
    const dashboardBtn = document.querySelector('[onclick*="dashboard"]');
    if (dashboardBtn) {
      dashboardBtn.classList.add("active");
    }
  } catch (error) {
    console.error("Optimization failed:", error);
    showNotification("Optimization failed: " + error.message, "error");
  } finally {
    // Reset button and hide loading
    btn.disabled = false;
    btnText.textContent = "Run Optimization";
    loadingOverlay.classList.add("hidden");
  }
}

// Poll optimization progress
// Replace the existing pollOptimizationProgress function with this enhanced version:

async function pollOptimizationProgress(taskId, loadingMessageElement) {
  const maxPolls = 60; // 5 minutes max (5 second intervals)
  let pollCount = 0;
  let runId = null;

  while (pollCount < maxPolls) {
    try {
      const response = await fetch(`/api/optimization-status/${taskId}/`);

      // If the status endpoint isn't ready yet, wait and retry
      if (response.status === 404) {
        console.warn(
          `Status endpoint not ready for task ${taskId}, retrying...`
        );
        await new Promise((resolve) => setTimeout(resolve, 5000));
        pollCount++;
        continue;
      }

      if (!response.ok) {
        throw new Error(`Status check failed: ${response.status}`);
      }

      const status = await response.json();
      console.log("Optimization status:", status); // Debug log

      // Store run_id for later use
      if (status.run_id) {
        runId = status.run_id;
      }

      // Update progress message with best available info
      const msg =
        status.progress_message ||
        (status.task_info && status.task_info.status) ||
        loadingMessageElement.textContent;
      loadingMessageElement.textContent = msg;
      updateOptimizationProgress(status.progress_percentage, msg);

      // Determine completion/failure status. Always prioritize run.status
      const failed =
        status.status === "failed" || status.task_status === "FAILURE";
      const completed = status.status === "completed";

      if (failed) {
        const errMsg =
          status.error_message || status.task_error || "Optimization failed";
        loadingMessageElement.textContent = errMsg;
        markOptimizationFailed(errMsg);
        displayOptimizationStatus(status.solver_status || "Failed");
        showNotification(errMsg, "error");
        break;
      } else if (completed) {
        loadingMessageElement.textContent =
          "Optimization completed successfully!";
        setOptimizationProgressComplete("Optimization completed successfully!");

        // Fetch and display the actual results
        if (runId) {
          await loadOptimizationResults(runId);
        }

        break;
      }

      // Wait before next poll
      await new Promise((resolve) => setTimeout(resolve, 5000));
      pollCount++;
    } catch (error) {
      console.error("Progress polling error:", error);
      loadingMessageElement.textContent =
        "Optimization failed: " + error.message;
      markOptimizationFailed("Optimization failed: " + error.message);
      displayOptimizationStatus("Failed");
      showNotification("Optimization failed: " + error.message, "error");
      break;
    }
  }

  if (pollCount >= maxPolls) {
    showNotification("Optimization is taking longer than expected", "warning");
    updateOptimizationProgressStatus(
      "Optimization is taking longer than expected."
    );
  }
}

// Add this new function to load and display optimization results:
async function loadOptimizationResults(runId, runMeta = null) {
  try {
    showNotification("Loading optimization results...", "info");

    const response = await apiCall(`/api/optimization-results/${runId}/`);

    if (response.error) {
      throw new Error(response.error);
    }

    // Store the optimization data globally
    currentOptimizationData = response;
    currentRunId = runId;
    setCurrentRunDetails(response.run || runMeta);
    selectedRunId = runId;
    updateLoadRunButton();

    // Update charts with real data
    updateChartsWithOptimizationData(response.chart_data);

    // Update forecast table
    updateForecastTableWithData(response.chart_data.forecast_data);

    // Show summary statistics
    if (response.summary) {
      showOptimizationSummary(response.summary);
    }

    const summaryBias = response.summary?.r_bias_cfs;
    const initialBias = deriveBiasFromChartData(
      response.chart_data,
      summaryBias
    );
    if (initialBias !== null) {
      setAppliedBiasValue(initialBias);
    } else if (summaryBias !== undefined) {
      setAppliedBiasValue(summaryBias);
    } else {
      setAppliedBiasValue(null);
    }

    if (response.solver_status) {
      displayOptimizationStatus(response.solver_status);
    }

    showNotification("Optimization results loaded successfully!", "success");
  } catch (error) {
    console.error("Error loading optimization results:", error);
    showNotification(
      "Failed to load optimization results: " + error.message,
      "error"
    );

    // Fall back to sample data
    generateSampleData();
    updateForecastTable();
    currentRunId = null;
    setCurrentRunDetails(null);
    selectedRunId = null;
    updateLoadRunButton();
  }
}

async function loadLatestResults() {
  // Safety check for formatters (in case of loading issues)
  if (typeof TABLE_TIME_FORMATTER === 'undefined') {
      console.warn("TABLE_TIME_FORMATTER missing, defining fallback");
      window.TABLE_TIME_FORMATTER = new Intl.DateTimeFormat("en-US", {
          timeZone: "America/Los_Angeles",
          hour: "2-digit",
          minute: "2-digit",
          hour12: true,
      });
  }
  if (typeof TABLE_DAY_FORMATTER === 'undefined') {
      window.TABLE_DAY_FORMATTER = new Intl.DateTimeFormat("en-US", {
          timeZone: "America/Los_Angeles",
          weekday: "short",
      });
  }
  if (typeof TABLE_MONTH_DAY_FORMATTER === 'undefined') {
      window.TABLE_MONTH_DAY_FORMATTER = new Intl.DateTimeFormat("en-US", {
          timeZone: "America/Los_Angeles",
          month: "short",
          day: "numeric",
      });
  }
  if (typeof TABLE_DATE_TIME_FORMATTER === 'undefined') {
      window.TABLE_DATE_TIME_FORMATTER = new Intl.DateTimeFormat("en-US", {
          timeZone: "America/Los_Angeles",
          month: "short",
          day: "2-digit",
          hour: "2-digit",
          minute: "2-digit",
          hour12: true,
      });
  }

  try {
    const response = await apiCall("/api/optimization-results/latest/");
    if (response.error) {
      throw new Error(response.error);
    }
    currentOptimizationData = response;
    currentRunId = response.run_id || null;
    setCurrentRunDetails(response.run || null);
    selectedRunId = response.run_id || selectedRunId;
    updateLoadRunButton();
    updateChartsWithOptimizationData(response.chart_data);
    updateForecastTableWithData(response.chart_data.forecast_data);
    const summaryBias = response.summary?.r_bias_cfs;
    const initialBias = deriveBiasFromChartData(
      response.chart_data,
      summaryBias
    );
    if (initialBias !== null) {
      setAppliedBiasValue(initialBias);
    } else if (summaryBias !== undefined) {
      setAppliedBiasValue(summaryBias);
    } else {
      setAppliedBiasValue(null);
    }
    if (response.solver_status) {
      displayOptimizationStatus(response.solver_status);
    }
  } catch (error) {
    console.warn("Could not load latest optimization results:", error);
    generateSampleData();
    updateForecastTable();
    setAppliedBiasValue(null);
  }
}

// Add function to update charts with real optimization data:
function updateChartsWithOptimizationData(chartData) {
  if (!chartData || !elevationChart || !oxphChart) return;
  latestChartData = normalizeChartData(chartData);
  applyElevationChartData(latestChartData);
  refreshPowerChart();
}

// Add function to update forecast table with real data:
function updateForecastTableWithData(forecastDataArray) {
  if (!forecastDataArray || forecastDataArray.length === 0) return;

  actualsApplied = false;

  let previousSetpointChangeIso = null;

  // Convert to the format expected by updateForecastTable
  forecastData = forecastDataArray.map((row) => {
    const datetime = row.datetime ? new Date(row.datetime) : new Date();
    const biasValue = toFiniteNumber(row.bias_cfs ?? row.additional_bias);
    const setpoint =
      toFiniteNumber(
        row.setpoint ?? row.oxph_setpoint ?? row.oxph ?? row.oxph_actual
      ) ?? 0;
    const oxphValue = toFiniteNumber(row.oxph ?? row.oxph_actual) ?? 0;

    const mfraActual = toRoundedInteger(row.mfra_actual);
    const mfraForecast = toRoundedInteger(row.mfra_forecast);
    const resolvedMfra = mfraForecast ?? mfraActual ?? 0;

    const r4Actual = toRoundedInteger(row.r4_actual);
    const r4Forecast = toRoundedInteger(row.r4_forecast);
    const resolvedR4 = r4Forecast ?? r4Actual ?? 0;

    const r30Actual = toRoundedInteger(row.r30_actual);
    const r30Forecast = toRoundedInteger(row.r30_forecast);
    const resolvedR30 = r30Forecast ?? r30Actual ?? 0;

    const r20Forecast = toFiniteNumber(row.r20_forecast ?? row.r20_actual);
    const r5lForecast = toFiniteNumber(row.r5l_forecast ?? row.r5l_actual);
    const r26Forecast = toFiniteNumber(row.r26_forecast ?? row.r26_actual);
    const r20Actual = toFiniteNumber(row.r20_actual);
    const r5lActual = toFiniteNumber(row.r5l_actual);
    const r26Actual = toFiniteNumber(row.r26_actual);
    const abayElevation = toFiniteNumber(row.abay_elevation);
    const expectedAbay =
      toFiniteNumber(row.expected_abay ?? row.abay_elevation) ?? 0;
    const floatLevel = toFiniteNumber(
      row.float_level ?? row.float ?? row.abay_float_ft
    );
    const oxphActual = toFiniteNumber(row.oxph_actual);

    const rawSetpointChange =
      row.setpoint_change ??
      row.setpoint_change_time ??
      row.setpointChange ??
      row.oxph_setpoint_change_time ??
      null;
    let setpointChangeDate = null;
    if (rawSetpointChange) {
      const parsed = new Date(rawSetpointChange);
      if (!Number.isNaN(parsed.getTime())) {
        const isoValue = parsed.toISOString();
        if (isoValue !== previousSetpointChangeIso) {
          setpointChangeDate = parsed;
          previousSetpointChangeIso = isoValue;
        } else {
          setpointChangeDate = null;
        }
      } else {
        previousSetpointChangeIso = null;
      }
    } else {
      previousSetpointChangeIso = null;
    }

    return {
      datetime,
      setpoint,
      oxph: oxphValue,
      setpointChange: setpointChangeDate,
      r4: resolvedR4,
      r30: resolvedR30,
      r20: r20Forecast ?? 0,
      r5l: r5lForecast ?? 0,
      r26: r26Forecast ?? 0,
      r4Actual: r4Actual ?? null,
      r30Actual: r30Actual ?? null,
      r20Actual: r20Actual ?? null,
      r5lActual: r5lActual ?? null,
      r26Actual: r26Actual ?? null,
      mode: row.mode_forecast ?? row.mode ?? null,
      modeActual: row.mode_actual ?? row.ccs_mode ?? null,
      abayElevation: abayElevation ?? null,
      elevation: expectedAbay,
      mfra: resolvedMfra,
      mfraActual: mfraActual ?? null,
      floatLevel: floatLevel ?? null,
      oxphActual: oxphActual ?? null,
      biasCfs: biasValue ?? null,
      additionalBias: biasValue ?? null,
    };
  });

  originalData = JSON.parse(JSON.stringify(forecastData));
  updateForecastTable();
  updateNextSetpointCard(forecastData);
  markForecastDirty(false);

  // Update live system schematic with current values from first data row
  if (typeof updateSchematicData === 'function' && forecastData.length) {
    const row = forecastData[0];
    updateSchematicData({
      mfra: row.mfraActual ?? row.mfra ?? null,
      r30: row.r30Actual ?? row.r30 ?? null,
      r4: row.r4Actual ?? row.r4 ?? null,
      elevation: row.abayElevation ?? row.elevation ?? null,
      oxph: row.oxphActual ?? row.oxph ?? null,
      spill: 0,
    });
  }
}

function updateNextSetpointCard(data) {
    const container = document.getElementById('nextSetpointCard');
    if (!container) return;

    const renderCard = (bodyHtml) => {
        container.innerHTML = `
            <div class="setpoint-card-content">
                <div class="setpoint-icon">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/>
                    </svg>
                </div>
                <div class="setpoint-info">
                    ${bodyHtml}
                </div>
            </div>
        `;
    };

    if (!data || !data.length) {
        renderCard('<h3>Next Setpoint Changes</h3><div class="no-changes">No forecast data available</div>');
        return;
    }

    const now = new Date();
    const changes = [];
    let currentSetpoint = null;

    // Find the current setpoint (first future point or current point)
    // Assuming data is sorted by time
    
    // Find the first point in the future
    const futureData = data.filter(d => new Date(d.datetime) > now);
    
    if (futureData.length === 0) {
         renderCard('<h3>Next Setpoint Changes</h3><div class="no-changes">No future setpoint changes scheduled</div>');
         return;
    }

    // Current setpoint is the one active right now (most recent past or current)
    // But for "Next Setpoint", we want the *next* change.
    
    let lastVal = futureData[0].setpoint;
    
    for (let i = 1; i < futureData.length; i++) {
        const point = futureData[i];
        if (Math.abs(point.setpoint - lastVal) > 0.01) {
            changes.push({
                time: new Date(point.datetime),
                from: lastVal,
                to: point.setpoint
            });
            lastVal = point.setpoint;
            if (changes.length >= 2) break;
        }
    }

    if (changes.length === 0) {
        renderCard(`
            <h3>Next Setpoint Changes</h3>
            <div class="no-changes">Steady operation at ${lastVal.toFixed(1)} MW</div>
        `);
        return;
    }

    let changesHtml = '';
    changes.forEach(change => {
        const timeStr = change.time.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
        const dayStr = change.time.toLocaleDateString([], { weekday: 'short' });
        
        changesHtml += `
            <div class="setpoint-change-item">
                <div class="change-time">${dayStr} ${timeStr}</div>
                <div class="change-value">${change.to.toFixed(1)} <span style="font-size: 0.8em; color: #718096;">MW</span></div>
            </div>
            ${change === changes[changes.length - 1] ? '' : '<div class="change-arrow">&rarr;</div>'}
        `;
    });

    renderCard(`
        <h3>Next Setpoint Changes</h3>
        <div class="setpoint-changes">
            ${changesHtml}
        </div>
    `);
}

// Add function to show optimization summary:
function showOptimizationSummary(summary) {
  let summaryHtml =
    '<div class="optimization-summary"><h4>Optimization Summary:</h4><ul>';

  if (summary.total_spillage_af !== null) {
    summaryHtml += `<li>Total Spillage: ${summary.total_spillage_af.toFixed(
      1
    )} AF</li>`;
  }
  if (summary.avg_oxph_utilization_pct !== null) {
    summaryHtml += `<li>OXPH Utilization: ${summary.avg_oxph_utilization_pct.toFixed(
      1
    )}%</li>`;
  }
  if (summary.peak_elevation_ft !== null) {
    summaryHtml += `<li>Peak Elevation: ${summary.peak_elevation_ft.toFixed(
      2
    )} ft</li>`;
  }
  if (summary.min_elevation_ft !== null) {
    summaryHtml += `<li>Min Elevation: ${summary.min_elevation_ft.toFixed(
      2
    )} ft</li>`;
  }
  if (summary.r_bias_cfs !== null) {
    summaryHtml += `<li>R-Bias: ${summary.r_bias_cfs.toFixed(2)} CFS</li>`;
  }

  summaryHtml += "</ul></div>";

  // You can add this to a summary container or show in a notification
  showNotification(summaryHtml, "info", 5000); // Show for 5 seconds
}

// Add these new functions for price data handling
async function fetchElectricityPrices(nodeId = "20000002064") {
  try {
    showNotification("Fetching electricity price data...", "warning");

    const response = await apiCall(
      `/api/electricity-prices/?node_id=${nodeId}`
    );

    if (response.error) {
      throw new Error(response.error);
    }

    currentPriceData = response;
    updatePriceChart(response.price_data);
    updatePriceStatistics(response.statistics);

    const sourceMessage =
      response.data_source === "simulation"
        ? "Using simulated price data"
        : `Loaded ${response.data_count} price points from YES Energy`;

    showNotification(sourceMessage, "success");
    return response;
  } catch (error) {
    console.error("Error fetching electricity prices:", error);
    showNotification("Failed to fetch price data: " + error.message, "error");
    return null;
  }
}

function updatePriceChart(priceData) {
  if (!priceChart || !priceData) return;

  const labels = [];
  const dayAheadPrices = [];
  const realTimePrices = [];
  const fifteenMinPrices = [];

  priceData.forEach((point) => {
    const date = new Date(point.timestamp);
    labels.push(formatChartDateTime(date));
    dayAheadPrices.push(point.day_ahead_price);
    realTimePrices.push(point.real_time_price);
    fifteenMinPrices.push(point.fifteen_min_price);
  });

  priceChart.setOption({
    xAxis: { data: labels },
    series: [
      { name: 'Day-Ahead Price', data: dayAheadPrices },
      { name: 'Real-Time Price', data: realTimePrices },
      { name: '15-Min Price', data: fifteenMinPrices }
    ]
  });
}

function updatePriceStatistics(statistics) {
  // Update price statistics in the UI
  if (!statistics) return;

  Object.keys(statistics).forEach((priceType) => {
    const stats = statistics[priceType];
    const container = document.getElementById(
      `${priceType.toLowerCase()}_stats`
    );

    if (container) {
      container.innerHTML = `
                <div class="price-stat">
                    <span class="stat-label">Current:</span>
                    <span class="stat-value">$${
                      stats.current?.toFixed(2) || "N/A"
                    }</span>
                </div>
                <div class="price-stat">
                    <span class="stat-label">Min:</span>
                    <span class="stat-value">$${
                      stats.min?.toFixed(2) || "N/A"
                    }</span>
                </div>
                <div class="price-stat">
                    <span class="stat-label">Max:</span>
                    <span class="stat-value">$${
                      stats.max?.toFixed(2) || "N/A"
                    }</span>
                </div>
                <div class="price-stat">
                    <span class="stat-label">Avg:</span>
                    <span class="stat-value">$${
                      stats.mean?.toFixed(2) || "N/A"
                    }</span>
                </div>
            `;
    }
  });
}

async function calculateRevenue() {
  if (!currentPriceData || !forecastData) {
    showNotification(
      "Need both price data and optimization schedule to calculate revenue",
      "warning"
    );
    return;
  }

  try {
    // Convert forecast data to the format expected by the API
    const oxphSchedule = forecastData.map((point) => ({
      timestamp: point.datetime.toISOString(),
      oxph_mw: point.oxph,
    }));

    const response = await apiCall("/api/price-analysis/", {
      method: "POST",
      body: JSON.stringify({
        oxph_schedule: oxphSchedule,
        price_data: currentPriceData.price_data,
      }),
    });

    if (response.error) {
      throw new Error(response.error);
    }

    displayRevenueAnalysis(response.revenue_analysis);
    showNotification("Revenue analysis completed", "success");
  } catch (error) {
    console.error("Error calculating revenue:", error);
    showNotification("Failed to calculate revenue: " + error.message, "error");
  }
}

function displayRevenueAnalysis(analysis) {
  const container = document.getElementById("revenueAnalysis");
  if (!container) return;

  container.innerHTML = `
        <div class="revenue-summary">
            <h4>Revenue Analysis (24 Hours)</h4>
            <div class="revenue-metrics">
                <div class="metric">
                    <span class="metric-label">Total Revenue:</span>
                    <span class="metric-value">$${
                      analysis.total_revenue_24h?.toFixed(2) || "0.00"
                    }</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Average Price:</span>
                    <span class="metric-value">$${
                      analysis.average_price_mwh?.toFixed(2) || "0.00"
                    }/MWh</span>
                </div>
                ${
                  analysis.peak_revenue_hour
                    ? `
                <div class="metric">
                    <span class="metric-label">Peak Revenue Hour:</span>
                    <span class="metric-value">${new Date(
                      analysis.peak_revenue_hour.timestamp
                    ).toLocaleString("en-US", {
                      timeZone: "America/Los_Angeles",
                    })}</span>
                </div>
                `
                    : ""
                }
            </div>
        </div>
    `;
}

// Get CSRF token for Django
function getCsrfToken() {
  const name = "csrftoken";
  let cookieValue = null;
  if (document.cookie && document.cookie !== "") {
    const cookies = document.cookie.split(";");
    for (let i = 0; i < cookies.length; i++) {
      const cookie = cookies[i].trim();
      if (cookie.substring(0, name.length + 1) === name + "=") {
        cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
        break;
      }
    }
  }
  return cookieValue;
}

// Refresh charts
async function refreshCharts() {
  try {
    showNotification("Refreshing data...", "warning");
    await apiCall("/api/refresh-pi-data/", { method: "POST" });
    await loadLatestResults();
    showNotification("Data refreshed successfully", "success");
  } catch (error) {
    console.error("Error refreshing data:", error);
    showNotification("Failed to refresh data: " + error.message, "error");
  }
}

// Add this to your existing refreshCharts function
async function refreshChartsWithPrices() {
  // Refresh existing charts
  refreshCharts();

  // Refresh price data
  await fetchElectricityPrices();

  // Recalculate revenue if we have optimization data
  if (forecastData && forecastData.length > 0) {
    await calculateRevenue();
  }
}

// Save parameters
function saveParameters() {
  // In production, this would save to backend/database
  const parameters = {};
  document.querySelectorAll("#parameters .form-control").forEach((input) => {
    const key = input.id || input.name || input.getAttribute("data-param");
    if (key) {
      parameters[key] = input.value;
    }
  });

  localStorage.setItem("abayOptimizationParams", JSON.stringify(parameters));
  showNotification("Parameters saved successfully", "success");
}

// Reset parameters
function resetParameters() {
  if (
    confirm("Are you sure you want to reset all parameters to default values?")
  ) {
    // Reset all parameter inputs to their default values
    document.querySelectorAll("#parameters .form-control").forEach((input) => {
      if (input.defaultValue !== undefined) {
        input.value = input.defaultValue;
      }
    });
    showNotification("Parameters reset to defaults", "warning");
  }
}

// Load historical data
function loadHistoricalData() {
  const startDateInput = document.getElementById("historyStartDate");
  const endDateInput = document.getElementById("historyEndDate");

  if (!startDateInput || !endDateInput) {
    showNotification("Date input elements not found", "error");
    return;
  }

  const startDate = startDateInput.value;
  const endDate = endDateInput.value;

  if (!startDate || !endDate) {
    showNotification("Please select both start and end dates", "error");
    return;
  }

  if (new Date(startDate) >= new Date(endDate)) {
    showNotification("Start date must be before end date", "error");
    return;
  }

  showNotification("Loading historical data...", "warning");

  // Simulate loading historical data
  setTimeout(() => {
    try {
      // Generate sample historical data
      const labels = [];
      const actualData = [];
      const expectedData = [];
      const biasData = [];

      const start = new Date(startDate);
      const end = new Date(endDate);
      const diffTime = Math.abs(end - start);
      const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));

      for (let i = 0; i <= diffDays * 24; i++) {
        const date = new Date(start.getTime() + i * 60 * 60 * 1000);
        labels.push(
          date.toLocaleDateString("en-US", {
            timeZone: "America/Los_Angeles",
            month: "short",
            day: "numeric",
            hour: "2-digit",
          })
        );

        const baseValue = 1170 + Math.sin(i / 24) * 2;
        actualData.push(baseValue + Math.random() * 0.5);
        expectedData.push(baseValue + 0.2 + Math.random() * 0.3);
        biasData.push(baseValue + 0.4 + Math.random() * 0.2);
      }

      historicalChart.setOption({
        xAxis: { data: labels },
        series: [
          {
            name: 'Actual Elevation',
            type: 'line',
            data: actualData,
            smooth: true,
            lineStyle: { width: 2 },
            symbol: 'none'
          },
          {
            name: 'One-Step Expected',
            type: 'line',
            data: expectedData,
            smooth: true,
            lineStyle: { width: 2, type: 'dashed' },
            symbol: 'none'
          },
          {
            name: 'Bias Corrected',
            type: 'line',
            data: biasData,
            smooth: true,
            lineStyle: { width: 2, type: 'dotted' },
            symbol: 'none'
          }
        ]
      });

      showNotification("Historical data loaded successfully", "success");
    } catch (error) {
      console.error("Error loading historical data:", error);
      showNotification("Failed to load historical data", "error");
    }
  }, 1500);
}

// Show notification
function showNotification(message, type = "success") {
  const notification = document.getElementById("notification");
  if (!notification) return;

  notification.textContent = message;
  notification.className = `notification ${type}`;
  notification.classList.add("show");

  setTimeout(() => {
    notification.classList.remove("show");
  }, 3000);
}

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    const setpointModal = document.getElementById("setpointModal");
    const runModal = document.getElementById("runHistoryModal");
    const raftingModal = document.getElementById("raftingWarningModal");

    if (setpointModal && !setpointModal.classList.contains("hidden")) {
      closeSetpointModal();
    } else if (runModal && !runModal.classList.contains("hidden")) {
      closeRunHistoryModal();
    } else if (raftingModal && !raftingModal.classList.contains("hidden")) {
      cancelRaftingWarning();
      closeSetpointModal();
    }
  }

  // Global shortcuts
  if (e.ctrlKey || e.metaKey) {
    switch (e.key) {
      case "r":
        e.preventDefault();
        refreshChartsWithPrices();
        break;
      case "s":
        e.preventDefault();
        saveParameters();
        break;
      case "Enter":
        if (document.activeElement.closest("#optimization")) {
          e.preventDefault();
          runOptimization();
        }
        break;
    }
  }
});

// Auto-save functionality for parameters
document.addEventListener("input", function (e) {
  if (e.target.closest("#parameters")) {
    // Debounce auto-save
    clearTimeout(window.autoSaveTimeout);
    window.autoSaveTimeout = setTimeout(() => {
      const parameters = {};
      document
        .querySelectorAll("#parameters .form-control")
        .forEach((input) => {
          const key =
            input.id || input.name || input.getAttribute("data-param");
          if (key) {
            parameters[key] = input.value;
          }
        });
      localStorage.setItem(
        "abayOptimizationParamsTemp",
        JSON.stringify(parameters)
      );
    }, 1000);
  }
});

// Load saved parameters on page load
window.addEventListener("load", function () {
  const saved = localStorage.getItem("abayOptimizationParams");
  if (saved) {
    try {
      const parameters = JSON.parse(saved);
      Object.keys(parameters).forEach((key) => {
        const input =
          document.getElementById(key) ||
          document.querySelector(`[name="${key}"]`) ||
          document.querySelector(`[data-param="${key}"]`);
        if (input) {
          input.value = parameters[key];
        }
      });
    } catch (e) {
      console.warn("Failed to load saved parameters:", e);
    }
  }
});

// Export functionality
function exportData(format = "csv") {
  if (!currentOptimizationData) {
    showNotification("No optimization data to export", "warning");
    return;
  }

  // In production, this would generate actual export files
  showNotification(`Exporting data as ${format.toUpperCase()}...`, "success");
}

// Real-time data updates (simulated)
setInterval(() => {
  // Simulate real-time updates to current state
  const now = new Date();
  if (now.getSeconds() === 0) {
    // Update every minute
    // In production, this would fetch real data from the backend
    // updateRealTimeData();
  }
}, 1000);

// Additional utility functions
function formatNumber(num, decimals = 2) {
  return parseFloat(num).toFixed(decimals);
}

function formatDateTime(date) {
  return date.toLocaleString("en-US", {
    timeZone: "America/Los_Angeles",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

// Format date/time for chart labels: "Fri Jun 6, 18" format
function formatChartDateTime(date) {
  const options = {
    timeZone: "America/Los_Angeles",
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    hour12: false, // Use 24-hour format
  };

  const formatted = date.toLocaleString("en-US", options);
  // Extract parts and reformat to "Fri Jun 6, 18"
  const parts = formatted.split(" ");
  const weekday = parts[0].replace(",", ""); // Remove comma from weekday
  const month = parts[1];
  const day = parts[2].replace(",", ""); // Remove comma from day
  const timeParts = parts[3].split(":");
  const hour = timeParts[0];
  const minute = timeParts[1];

  return `${weekday} ${month} ${day}, ${hour}:${minute}`;
}

// Error handling for missing elements
function safeGetElement(id) {
  const element = document.getElementById(id);
  if (!element) {
    console.warn(`Element with id '${id}' not found`);
  }
  return element;
}

// API helper functions
async function apiCall(url, options = {}) {
  try {
    const defaultOptions = {
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCsrfToken(),
      },
    };

    const response = await fetch(url, { ...defaultOptions, ...options });

    if (!response.ok) {
      throw new Error(
        `API call failed: ${response.status} ${response.statusText}`
      );
    }

    return await response.json();
  } catch (error) {
    console.error("API call error:", error);
    throw error;
  }
}

// Chart utility functions
function updateChartData(chart, newData) {
  if (!chart || !newData) return;

  try {
    chart.setOption(newData);
  } catch (error) {
    console.error("Error updating chart:", error);
  }
}

// Tab switching functionality
function switchTab(tabName, event) {
  if (event) {
    event.preventDefault();
  }

  document.querySelectorAll(".tab-content").forEach((content) => {
    content.classList.remove("active");
  });
  document.querySelectorAll(".nav-item").forEach((btn) => {
    btn.classList.remove("active");
  });

  const targetContent = document.getElementById(tabName);
  if (targetContent) {
    targetContent.classList.add("active");
  }

  let clickedButton = event ? event.currentTarget : null;
  if (!clickedButton) {
    clickedButton = document.querySelector(`.nav-item[onclick*="${tabName}"]`);
  }
  if (clickedButton) {
    clickedButton.classList.add("active");
  }

  const pageTitle = document.querySelector(".page-title");
  if (pageTitle && clickedButton) {
    const text = clickedButton.querySelector("span")?.textContent;
    if (text) pageTitle.textContent = text;
  }

  setTimeout(() => {
    if (tabName === "dashboard") {
      if (elevationChart) elevationChart.resize();
      if (oxphChart) oxphChart.resize();
      if (timelineChart) timelineChart.resize();
    } else if (tabName === "prices") {
      if (priceChart) priceChart.resize();
    } else if (tabName === "data") {
      if (forecastHot) forecastHot.render();
    }
  }, 100);
}

async function refreshRaftingTimes() {
    try {
        showNotification('Refreshing rafting times...', 'warning');

        const response = await apiCall('/api/rafting-times/');

        if (response.error) {
            throw new Error(response.error);
        }

        currentRaftingData = response;
        updateRaftingTimesDisplay(response);

        showNotification('Rafting times updated', 'success');

    } catch (error) {
        console.error('Error refreshing rafting times:', error);
        showNotification('Failed to refresh rafting times: ' + error.message, 'error');
    }
}

function updateRaftingTimesDisplay(data) {
    const todayInfo = data.today;

    if (todayInfo.has_rafting) {
        const startEl = document.getElementById('todayStartTime');
        if (startEl) {
            startEl.textContent = todayInfo.start_time;
            if (todayInfo.is_early_release) {
                startEl.textContent += ' (Early Release)';
                startEl.style.color = '#e74c3c';
            }
        }
        const endEl = document.getElementById('todayEndTime');
        if (endEl) endEl.textContent = todayInfo.end_time;
        
        const adjEl = document.getElementById('todayAdjustmentTime');
        if (adjEl) adjEl.textContent = todayInfo.oxph_adjustment_time;
        
        const setEl = document.getElementById('todayOxphSetting');
        if (setEl) setEl.textContent = todayInfo.current_oxph_setting;

        const infoEl = document.getElementById('todayRaftingInfo');
        if (infoEl) infoEl.style.opacity = '1';
    } else {
        const startEl = document.getElementById('todayStartTime');
        if (startEl) startEl.textContent = 'No Rafting';
        
        const endEl = document.getElementById('todayEndTime');
        if (endEl) endEl.textContent = '--';
        
        const adjEl = document.getElementById('todayAdjustmentTime');
        if (adjEl) adjEl.textContent = '--';
        
        const setEl = document.getElementById('todayOxphSetting');
        if (setEl) setEl.textContent = '--';
        
        const infoEl = document.getElementById('todayRaftingInfo');
        if (infoEl) infoEl.style.opacity = '0.5';
    }

    const tomorrowInfo = data.tomorrow;

    if (tomorrowInfo.has_rafting) {
        const startEl = document.getElementById('tomorrowStartTime');
        if (startEl) {
            startEl.textContent = tomorrowInfo.start_time;
            if (tomorrowInfo.is_early_release) {
                startEl.textContent += ' (Early Release)';
                startEl.style.color = '#e74c3c';
            }
        }
        const endEl = document.getElementById('tomorrowEndTime');
        if (endEl) endEl.textContent = tomorrowInfo.end_time;
        
        const adjEl = document.getElementById('tomorrowAdjustmentTime');
        if (adjEl) adjEl.textContent = tomorrowInfo.oxph_adjustment_time;
        
        const setEl = document.getElementById('tomorrowOxphSetting');
        if (setEl) setEl.textContent = tomorrowInfo.current_oxph_setting;

        const infoEl = document.getElementById('tomorrowRaftingInfo');
        if (infoEl) infoEl.style.opacity = '1';
    } else {
        const startEl = document.getElementById('tomorrowStartTime');
        if (startEl) startEl.textContent = 'No Rafting';
        
        const endEl = document.getElementById('tomorrowEndTime');
        if (endEl) endEl.textContent = '--';
        
        const adjEl = document.getElementById('tomorrowAdjustmentTime');
        if (adjEl) adjEl.textContent = '--';
        
        const setEl = document.getElementById('tomorrowOxphSetting');
        if (setEl) setEl.textContent = '--';
        
        const infoEl = document.getElementById('tomorrowRaftingInfo');
        if (infoEl) infoEl.style.opacity = '0.5';
    }
}

async function calculateRampTime() {
    try {
        const currentMW = parseFloat(document.getElementById('currentMW').value);
        const targetMW = parseFloat(document.getElementById('targetMW').value);
        const targetTime = document.getElementById('targetTime').value;
        const targetDate = document.getElementById('targetDate').value;

        if (!targetTime) {
            showNotification('Please enter a target time', 'warning');
            return;
        }

        const finalTargetDate = targetDate || new Date().toISOString().split('T')[0];

        showNotification('Calculating ramp time...', 'warning');

        const response = await apiCall('/api/ramp-calculator/', {
            method: 'POST',
            body: JSON.stringify({
                current_mw: currentMW,
                target_mw: targetMW,
                target_time: targetTime,
                target_date: finalTargetDate
            })
        });

        if (response.error) {
            throw new Error(response.error);
        }

        if (response.calculation && response.calculation.adjustment_needed) {
            const calc = response.calculation;
             const adjEl = document.getElementById('adjustmentTime');
             if (adjEl) adjEl.textContent = calc.adjustment_time;
             
             const durEl = document.getElementById('rampDuration');
             if (durEl) durEl.textContent = `${calc.ramp_duration_formatted} (${calc.ramp_duration_minutes} min)`;

             const resEl = document.getElementById('rampResult');
             if (resEl) resEl.style.display = 'block';

            showNotification(`Adjustment needed at ${calc.adjustment_time}`, 'success');
        } else {
             const resEl = document.getElementById('rampResult');
             if (resEl) resEl.style.display = 'none';
            showNotification('No adjustment needed - already at target', 'success');
        }

    } catch (error) {
        console.error('Error calculating ramp time:', error);
        showNotification('Failed to calculate ramp time: ' + error.message, 'error');
    }
}

function updateWaterYearType() {
    const waterYearType = document.getElementById('waterYearType').value;
    showNotification(`Water Year Type would be updated to: ${waterYearType}`, 'warning');
    setTimeout(refreshRaftingTimes, 1000);
}

// Run Optimization Modal Functions
function openRunOptimizationModal() {
    const modal = document.getElementById('runOptimizationModal');
    const backdrop = document.getElementById('runOptimizationBackdrop');
    if (modal && backdrop) {
        modal.classList.remove('hidden');
        backdrop.classList.remove('hidden');
        modal.classList.add('active');
        backdrop.classList.add('active');
        
        // Set default date if empty
        const dateInput = document.getElementById('modal_historicalDate');
        if (dateInput && !dateInput.value) {
            const yesterday = new Date();
            yesterday.setDate(yesterday.getDate() - 1);
            dateInput.value = yesterday.toISOString().split('T')[0];
        }
    }
}

function closeRunOptimizationModal() {
    const modal = document.getElementById('runOptimizationModal');
    const backdrop = document.getElementById('runOptimizationBackdrop');
    if (modal && backdrop) {
        modal.classList.add('hidden');
        backdrop.classList.add('hidden');
        modal.classList.remove('active');
        backdrop.classList.remove('active');
    }
}

// ==========================================
// SCHEMATIC DRILL-DOWN MODAL
// ==========================================

let schematicDrillDownChart = null;

var SCHEMATIC_DRILL_DOWN_CONFIG = {
  oxph: {
    title: 'OXPH Output',
    unit: 'MW',
    yAxisName: 'Power Output (MW)',
    yMin: 0,
    getSeries: function (d) {
      return [
        { name: 'Historical', data: d.oxph.historical, color: '#27ae60', dash: false },
        { name: 'Optimized Schedule', data: d.oxph.optimized, color: '#9b59b6', dash: true }
      ];
    },
    getCurrent: function (d) {
      var h = d.oxph.historical;
      if (!Array.isArray(h)) return null;
      for (var i = h.length - 1; i >= 0; i--) { if (h[i] != null) return h[i]; }
      return null;
    }
  },
  abay: {
    title: 'ABAY Elevation',
    unit: 'ft',
    yAxisName: 'Elevation (ft)',
    yMin: 1166,
    getSeries: function (d) {
      return [
        { name: 'Actual', data: d.elevation.actual, color: '#e74c3c', dash: false },
        { name: 'Optimized Forecast', data: d.elevation.optimized, color: '#3498db', dash: true },
        { name: 'Float Level', data: d.elevation.float, color: '#dc3545', dash: [10, 5] }
      ];
    },
    getCurrent: function (d) {
      var a = d.elevation.actual;
      if (!Array.isArray(a)) return null;
      for (var i = a.length - 1; i >= 0; i--) { if (a[i] != null) return a[i]; }
      return null;
    }
  },
  mfra: {
    title: 'MFRA Generation',
    unit: 'MW',
    yAxisName: 'Power Output (MW)',
    yMin: 0,
    getSeries: function (d) {
      return [
        { name: 'Historical', data: d.mfra.historical, color: '#2980b9', dash: false },
        { name: 'Forecast', data: d.mfra.forecast, color: '#e67e22', dash: true }
      ];
    },
    getCurrent: function (d) {
      var h = d.mfra.historical;
      if (!Array.isArray(h)) return null;
      for (var i = h.length - 1; i >= 0; i--) { if (h[i] != null) return h[i]; }
      return null;
    }
  },
  r4: {
    title: 'R4 River Flow',
    unit: 'CFS',
    yAxisName: 'Flow (CFS)',
    yMin: 0,
    getSeries: function (d) {
      return [
        { name: 'Observed', data: d.river.r4.actual, color: '#1abc9c', dash: false },
        { name: 'HydroForecast', data: d.river.r4.hydro, color: '#16a085', dash: true },
        { name: 'CNRFC', data: d.river.r4.cnrfc, color: '#48c9b0', dash: [4, 4] }
      ];
    },
    getCurrent: function (d) {
      var a = d.river.r4.actual;
      if (!Array.isArray(a)) return null;
      for (var i = a.length - 1; i >= 0; i--) { if (a[i] != null) return a[i]; }
      return null;
    }
  },
  r30: {
    title: 'R30 River Flow',
    unit: 'CFS',
    yAxisName: 'Flow (CFS)',
    yMin: 0,
    getSeries: function (d) {
      return [
        { name: 'Observed', data: d.river.r30.actual, color: '#e67e22', dash: false },
        { name: 'HydroForecast', data: d.river.r30.hydro, color: '#d35400', dash: true },
        { name: 'CNRFC', data: d.river.r30.cnrfc, color: '#f1c40f', dash: [4, 4] }
      ];
    },
    getCurrent: function (d) {
      var a = d.river.r30.actual;
      if (!Array.isArray(a)) return null;
      for (var i = a.length - 1; i >= 0; i--) { if (a[i] != null) return a[i]; }
      return null;
    }
  },
  downstream: {
    title: 'Spillway',
    unit: 'CFS',
    yAxisName: 'Flow (CFS)',
    yMin: 0,
    getSeries: function () { return []; },
    getCurrent: function () { return null; }
  }
};

window.openSchematicDrillDown = function (nodeKey) {
  if (!latestChartData) return;
  var config = SCHEMATIC_DRILL_DOWN_CONFIG[nodeKey];
  if (!config) return;

  var seriesDefs = config.getSeries(latestChartData);
  var hasData = seriesDefs.some(function (s) { return hasChartValues(s.data); });
  if (!hasData) {
    if (typeof showNotification === 'function') {
      showNotification('No time series data available for ' + config.title, 'info');
    }
    return;
  }

  var modal = document.getElementById('schematicDrillDownModal');
  var backdrop = document.getElementById('schematicDrillDownBackdrop');
  var titleEl = document.getElementById('schematicDrillDownTitle');
  if (!modal || !backdrop) return;

  // Title with current value
  var cur = config.getCurrent(latestChartData);
  var titleText = config.title;
  if (cur != null) {
    titleText += ' \u2014 ' + (Number.isInteger(cur) ? cur : parseFloat(cur).toFixed(1)) + ' ' + config.unit;
  }
  if (titleEl) titleEl.textContent = titleText;

  // Show modal
  backdrop.classList.remove('hidden');
  modal.classList.remove('hidden');
  modal.offsetHeight; // reflow for transition
  backdrop.classList.add('active');
  modal.classList.add('active');

  backdrop.onclick = function () { closeSchematicDrillDown(); };

  var escHandler = function (e) {
    if (e.key === 'Escape') {
      closeSchematicDrillDown();
      document.removeEventListener('keydown', escHandler);
    }
  };
  document.addEventListener('keydown', escHandler);

  _buildDrillDownChart(config, seriesDefs);
};

window.closeSchematicDrillDown = function () {
  var modal = document.getElementById('schematicDrillDownModal');
  var backdrop = document.getElementById('schematicDrillDownBackdrop');
  if (modal) { modal.classList.add('hidden'); modal.classList.remove('active'); }
  if (backdrop) { backdrop.classList.add('hidden'); backdrop.classList.remove('active'); }
  if (schematicDrillDownChart) {
    schematicDrillDownChart.dispose();
    schematicDrillDownChart = null;
  }
};

function _buildDrillDownChart(config, seriesDefs) {
  if (schematicDrillDownChart) {
    schematicDrillDownChart.dispose();
    schematicDrillDownChart = null;
  }

  schematicDrillDownChart = initEChart('schematicDrillDownChart');
  if (!schematicDrillDownChart) return;

  var labels = latestChartData.labels || [];
  var labelCount = labels.length;
  var actualMask = latestChartData.actual_mask || [];

  // Find actual/forecast boundary
  var boundaryIdx = -1;
  for (var i = actualMask.length - 1; i >= 0; i--) {
    if (actualMask[i] === true) { boundaryIdx = i; break; }
  }

  var echartsSeries = [];
  seriesDefs.forEach(function (def, idx) {
    var s = {
      name: def.name,
      type: 'line',
      data: alignSeriesToLabels(def.data, labelCount),
      itemStyle: { color: def.color },
      lineStyle: {
        width: 2,
        type: def.dash === true ? 'dashed' : (Array.isArray(def.dash) ? def.dash : 'solid')
      },
      symbol: 'none',
      smooth: false,
      connectNulls: false
    };

    // "Now" markLine on first series
    if (idx === 0 && boundaryIdx >= 0) {
      s.markLine = {
        silent: true,
        symbol: 'none',
        label: { show: true, position: 'insideEndTop', formatter: 'Now', fontSize: 10 },
        lineStyle: { color: '#ff006e', width: 2, type: 'dashed' },
        data: [{ xAxis: boundaryIdx }]
      };
    }
    echartsSeries.push(s);
  });

  // Add day dividers to first series
  var dividers = buildDayDividers(labels);
  if (echartsSeries.length && dividers.length) {
    var ml = echartsSeries[0].markLine;
    if (ml) {
      ml.data = ml.data.concat(dividers);
    } else {
      echartsSeries[0].markLine = { silent: true, symbol: 'none', label: { show: false }, data: dividers };
    }
  }

  // Y bounds
  var allVals = [];
  echartsSeries.forEach(function (s) {
    s.data.forEach(function (v) { if (v != null && Number.isFinite(v)) allVals.push(v); });
  });
  var yMin = config.yMin != null ? config.yMin : 0;
  var yMax = allVals.length ? Math.ceil(Math.max.apply(null, allVals) * 1.08) : undefined;

  schematicDrillDownChart.setOption({
    tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
    legend: { show: true, bottom: 30, textStyle: { fontSize: 11 } },
    grid: { left: 55, right: 20, top: 25, bottom: 75 },
    xAxis: {
      type: 'category',
      data: labels,
      axisLabel: {
        rotate: 40,
        interval: function (index) { return index % 6 === 0; },
        fontSize: 10
      }
    },
    yAxis: {
      type: 'value',
      name: config.yAxisName,
      min: yMin,
      max: yMax,
      nameTextStyle: { fontSize: 11 }
    },
    dataZoom: [
      { type: 'slider', xAxisIndex: 0, start: 0, end: 100, height: 18, bottom: 5 },
      { type: 'inside', xAxisIndex: 0 }
    ],
    series: echartsSeries
  });

  // Resize after modal transition completes
  setTimeout(function () {
    if (schematicDrillDownChart) schematicDrillDownChart.resize();
  }, 350);
}

function toggleModalHistoricalDate() {
    const runMode = document.getElementById('modal_runMode');
    const dateGroup = document.getElementById('modal_historicalDateGroup');
    if (runMode && dateGroup) {
        if (runMode.value === 'historical') {
            dateGroup.classList.remove('hidden');
        } else {
            dateGroup.classList.add('hidden');
        }
    }
}

function toggleAdvancedOptimizationSettings() {
    const settings = document.getElementById('advancedOptimizationSettings');
    if (settings) {
        settings.classList.toggle('hidden');
    }
}

// Advanced Settings Management
let defaultAdvancedSettings = {
    abayMinElevation: 1168.0,
    abayMaxElevationBuffer: 0.3,
    oxphMinMW: 0.8
};

let savedAdvancedSettings = { ...defaultAdvancedSettings };

function saveAdvancedSettings() {
    const minElev = document.getElementById('modal_abayMinElevation');
    const buffer = document.getElementById('modal_abayMaxElevationBuffer');
    const minMW = document.getElementById('modal_oxphMinMW');
    
    if (minElev && buffer && minMW) {
        savedAdvancedSettings = {
            abayMinElevation: parseFloat(minElev.value),
            abayMaxElevationBuffer: parseFloat(buffer.value),
            oxphMinMW: parseFloat(minMW.value)
        };
        showNotification('Advanced settings saved for next run', 'success');
        toggleAdvancedOptimizationSettings(); // Close section
    }
}

function cancelAdvancedSettings() {
    // Restore from saved
    const minElev = document.getElementById('modal_abayMinElevation');
    const buffer = document.getElementById('modal_abayMaxElevationBuffer');
    const minMW = document.getElementById('modal_oxphMinMW');
    
    if (minElev && buffer && minMW) {
        minElev.value = savedAdvancedSettings.abayMinElevation;
        buffer.value = savedAdvancedSettings.abayMaxElevationBuffer;
        minMW.value = savedAdvancedSettings.oxphMinMW;
        toggleAdvancedOptimizationSettings(); // Close section
    }
}

function revertAdvancedSettings() {
    // Restore defaults
    const minElev = document.getElementById('modal_abayMinElevation');
    const buffer = document.getElementById('modal_abayMaxElevationBuffer');
    const minMW = document.getElementById('modal_oxphMinMW');

    if (minElev && buffer && minMW) {
        minElev.value = defaultAdvancedSettings.abayMinElevation;
        buffer.value = defaultAdvancedSettings.abayMaxElevationBuffer;
        minMW.value = defaultAdvancedSettings.oxphMinMW;
        showNotification('Settings reverted to defaults', 'info');
    }
}

// ── CAISO DA Awards ──────────────────────────────────────────────────────
function fetchCAISODAAwards() {
    const btn = document.getElementById('fetchDaAwardsBtn');
    if (btn) {
        btn.disabled = true;
        btn.textContent = 'Fetching...';
    }

    fetch('/api/caiso-da-awards/', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCsrfToken(),
        },
        body: JSON.stringify({}),
    })
    .then(r => r.json())
    .then(data => {
        if (btn) {
            btn.disabled = false;
            btn.textContent = 'Fetch DA Awards';
        }
        if (data.error) {
            showNotification('DA Awards: ' + (data.detail || data.error), 'warning');
            return;
        }
        if (data.has_awards) {
            showNotification(
                `DA Awards loaded: ${data.hours} hours, avg ${data.avg_mw} MW for ${data.trade_date}`,
                'success'
            );
            updateMfraSourceIndicator('da_awards');
        } else {
            showNotification(
                `No DA awards available for ${data.trade_date}. Using persistence.`,
                'info'
            );
            updateMfraSourceIndicator('persistence');
        }
    })
    .catch(err => {
        if (btn) {
            btn.disabled = false;
            btn.textContent = 'Fetch DA Awards';
        }
        showNotification('Failed to fetch DA awards: ' + err.message, 'error');
    });
}

function updateMfraSourceIndicator(source) {
    const badge = document.getElementById('mfraSourceIndicator');
    if (!badge) return;

    badge.style.display = 'inline-block';
    badge.className = 'mfra-source-badge';

    if (source === 'da_awards') {
        badge.textContent = 'MFRA: DA Awards';
        badge.classList.add('mfra-source-da');
    } else {
        badge.textContent = 'MFRA: Persistence';
        badge.classList.add('mfra-source-persistence');
    }
}
