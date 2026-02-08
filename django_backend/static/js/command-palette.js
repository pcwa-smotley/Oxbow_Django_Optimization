// command-palette.js - Ctrl+K Command Palette & Keyboard Shortcuts

(function () {
  'use strict';

  const TAB_NAMES = ['dashboard', 'optimization', 'parameters', 'data', 'history', 'prices', 'rafting', 'alerts'];
  const TAB_LABELS = ['Dashboard', 'Run Optimization', 'Parameters', 'Data Table', 'History', 'Prices', 'Rafting', 'Alerts'];
  const TAB_ICONS = [
    '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>',
    '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>',
    '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>',
    '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>',
    '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>',
    '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>',
    '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M2 22h20"/><circle cx="12" cy="12" r="4"/></svg>',
    '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>'
  ];

  // Build command list
  const commands = [];

  // Tab navigation commands
  TAB_NAMES.forEach(function (tab, i) {
    commands.push({
      id: 'tab-' + tab,
      label: 'Go to ' + TAB_LABELS[i],
      icon: TAB_ICONS[i],
      shortcut: String(i + 1),
      action: function () { if (typeof switchTab === 'function') switchTab(tab); }
    });
  });

  // Action commands
  commands.push({
    id: 'run-optimization',
    label: 'Run Optimization',
    icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"/></svg>',
    shortcut: '',
    action: function () { if (typeof openRunOptimizationModal === 'function') openRunOptimizationModal(); }
  });

  commands.push({
    id: 'refresh-pi',
    label: 'Refresh PI Data',
    icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21.5 2v6h-6M2.5 22v-6h6M2 11.5a10 10 0 0 1 18.8-4.3M22 12.5a10 10 0 0 1-18.8 4.3"/></svg>',
    shortcut: '',
    action: function () { if (typeof refreshCharts === 'function') refreshCharts(); }
  });

  commands.push({
    id: 'load-run',
    label: 'Load Previous Run',
    icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/></svg>',
    shortcut: '',
    action: function () { if (typeof openRunHistoryModal === 'function') openRunHistoryModal(); }
  });

  commands.push({
    id: 'toggle-dark',
    label: 'Toggle Dark Mode',
    icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>',
    shortcut: 'D',
    action: function () { toggleDarkMode(); }
  });

  commands.push({
    id: 'profile',
    label: 'Open Profile',
    icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>',
    shortcut: '',
    action: function () { window.location.href = '/profile/'; }
  });

  commands.push({
    id: 'shortcuts',
    label: 'View Keyboard Shortcuts',
    icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="4" width="20" height="16" rx="2"/><path d="M6 8h.01M10 8h.01M14 8h.01M18 8h.01M8 12h.01M12 12h.01M16 12h.01M7 16h10"/></svg>',
    shortcut: '?',
    action: function () { toggleShortcutsOverlay(); }
  });

  // State
  let isOpen = false;
  let selectedIndex = 0;
  let filteredCommands = commands.slice();

  // DOM references
  const backdrop = document.getElementById('commandPaletteBackdrop');
  const input = document.getElementById('commandPaletteInput');
  const results = document.getElementById('commandPaletteResults');
  const shortcutsOverlay = document.getElementById('shortcutsOverlay');

  function fuzzyMatch(needle, haystack) {
    needle = needle.toLowerCase();
    haystack = haystack.toLowerCase();
    if (haystack.includes(needle)) return true;
    var ni = 0;
    for (var hi = 0; hi < haystack.length && ni < needle.length; hi++) {
      if (haystack[hi] === needle[ni]) ni++;
    }
    return ni === needle.length;
  }

  function renderResults() {
    results.innerHTML = '';
    filteredCommands.forEach(function (cmd, i) {
      var div = document.createElement('div');
      div.className = 'command-palette-item' + (i === selectedIndex ? ' selected' : '');
      div.innerHTML = cmd.icon +
        '<span class="cmd-label">' + cmd.label + '</span>' +
        (cmd.shortcut ? '<span class="cmd-shortcut">' + cmd.shortcut + '</span>' : '');
      div.addEventListener('click', function () { executeCommand(cmd); });
      div.addEventListener('mouseenter', function () {
        selectedIndex = i;
        updateSelection();
      });
      results.appendChild(div);
    });
  }

  function updateSelection() {
    var items = results.querySelectorAll('.command-palette-item');
    items.forEach(function (el, i) {
      el.classList.toggle('selected', i === selectedIndex);
    });
    // Scroll selected into view
    if (items[selectedIndex]) {
      items[selectedIndex].scrollIntoView({ block: 'nearest' });
    }
  }

  function openPalette() {
    if (!backdrop) return;
    isOpen = true;
    selectedIndex = 0;
    filteredCommands = commands.slice();
    backdrop.classList.add('active');
    if (input) {
      input.value = '';
      input.focus();
    }
    renderResults();
  }

  function closePalette() {
    if (!backdrop) return;
    isOpen = false;
    backdrop.classList.remove('active');
    if (input) input.value = '';
  }

  function executeCommand(cmd) {
    closePalette();
    if (cmd && typeof cmd.action === 'function') {
      setTimeout(cmd.action, 50);
    }
  }

  function filterCommands(query) {
    if (!query) {
      filteredCommands = commands.slice();
    } else {
      filteredCommands = commands.filter(function (cmd) {
        return fuzzyMatch(query, cmd.label);
      });
    }
    selectedIndex = 0;
    renderResults();
  }

  // Dark mode toggle helper
  function toggleDarkMode() {
    var html = document.documentElement;
    var current = html.getAttribute('data-theme');
    var next = current === 'dark' ? 'light' : 'dark';
    html.setAttribute('data-theme', next);
    localStorage.setItem('theme', next);
    // Reinit charts for new theme
    if (typeof reinitChartsForTheme === 'function') {
      reinitChartsForTheme();
    }
  }

  function toggleShortcutsOverlay() {
    if (!shortcutsOverlay) return;
    shortcutsOverlay.classList.toggle('active');
  }

  // Expose for external use
  window.openCommandPalette = openPalette;
  window.closeCommandPalette = closePalette;
  window.toggleDarkMode = toggleDarkMode;

  // Event Listeners
  if (input) {
    input.addEventListener('input', function () {
      filterCommands(this.value);
    });
  }

  if (backdrop) {
    backdrop.addEventListener('click', function (e) {
      if (e.target === backdrop) closePalette();
    });
  }

  // Global keyboard handler
  document.addEventListener('keydown', function (e) {
    var tag = (e.target.tagName || '').toLowerCase();
    var isInput = tag === 'input' || tag === 'textarea' || tag === 'select' || e.target.isContentEditable;

    // Ctrl+K / Cmd+K - always opens palette
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
      e.preventDefault();
      if (isOpen) closePalette(); else openPalette();
      return;
    }

    // When palette is open
    if (isOpen) {
      if (e.key === 'Escape') {
        e.preventDefault();
        closePalette();
        return;
      }
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        selectedIndex = Math.min(selectedIndex + 1, filteredCommands.length - 1);
        updateSelection();
        return;
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        selectedIndex = Math.max(selectedIndex - 1, 0);
        updateSelection();
        return;
      }
      if (e.key === 'Enter') {
        e.preventDefault();
        if (filteredCommands[selectedIndex]) {
          executeCommand(filteredCommands[selectedIndex]);
        }
        return;
      }
      return; // Don't process other shortcuts while palette is open
    }

    // Shortcuts overlay
    if (shortcutsOverlay && shortcutsOverlay.classList.contains('active')) {
      if (e.key === 'Escape' || e.key === '?') {
        e.preventDefault();
        shortcutsOverlay.classList.remove('active');
        return;
      }
    }

    // Don't trigger shortcuts when typing in inputs
    if (isInput) return;

    // Number keys 1-8 for tab switching
    var num = parseInt(e.key);
    if (num >= 1 && num <= 8 && !e.ctrlKey && !e.metaKey && !e.altKey) {
      e.preventDefault();
      var tabName = TAB_NAMES[num - 1];
      if (tabName && typeof switchTab === 'function') switchTab(tabName);
      return;
    }

    // D - Toggle dark mode
    if (e.key === 'd' || e.key === 'D') {
      if (!e.ctrlKey && !e.metaKey) {
        e.preventDefault();
        toggleDarkMode();
        return;
      }
    }

    // ? - Shortcuts overlay
    if (e.key === '?') {
      e.preventDefault();
      toggleShortcutsOverlay();
      return;
    }

    // Escape - Close modals
    if (e.key === 'Escape') {
      if (shortcutsOverlay && shortcutsOverlay.classList.contains('active')) {
        shortcutsOverlay.classList.remove('active');
      }
    }
  });

  // ==========================================
  // BOOT SEQUENCE
  // ==========================================
  function runBootSequence() {
    // Skip if already seen this session
    if (sessionStorage.getItem('bootDone')) {
      var overlay = document.getElementById('bootOverlay');
      if (overlay) overlay.style.display = 'none';
      return;
    }

    var overlay = document.getElementById('bootOverlay');
    if (!overlay) return;

    var checks = overlay.querySelectorAll('.boot-check-item');
    checks.forEach(function (el, i) {
      var delay = parseInt(el.getAttribute('data-delay')) || (i * 300);
      setTimeout(function () {
        el.classList.add('visible');
        setTimeout(function () {
          el.classList.add('checked');
        }, 200);
      }, delay);
    });

    // Fade out after all checks
    var totalDelay = checks.length * 300 + 800;
    setTimeout(function () {
      overlay.classList.add('fade-out');
      setTimeout(function () {
        overlay.style.display = 'none';
      }, 600);
      sessionStorage.setItem('bootDone', '1');
    }, totalDelay);
  }

  // Run boot on DOMContentLoaded
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', runBootSequence);
  } else {
    runBootSequence();
  }

  // ==========================================
  // STATUS BAR UPDATES
  // ==========================================
  window.updateStatusBar = function (data) {
    if (!data) return;

    // ABAY Elevation
    if (data.elevation != null) {
      var elev = parseFloat(data.elevation);
      var elevEl = document.getElementById('statusABAYValue');
      if (elevEl) elevEl.textContent = elev.toFixed(1) + ' ft';

      var dot = document.getElementById('statusABAYDot');
      if (dot) {
        dot.className = 'status-dot ' + (elev < 1168 ? 'red' : elev < 1169 ? 'amber' : 'green');
      }
    }

    // ABAY Trend
    if (data.elevationTrend != null) {
      var trendEl = document.getElementById('statusABAYTrend');
      if (trendEl) {
        var trend = data.elevationTrend;
        if (trend > 0.05) {
          trendEl.textContent = '\u25B2';
          trendEl.className = 'status-trend up';
        } else if (trend < -0.05) {
          trendEl.textContent = '\u25BC';
          trendEl.className = 'status-trend down';
        } else {
          trendEl.textContent = '\u2014';
          trendEl.className = 'status-trend flat';
        }
      }
    }

    // OXPH Output
    if (data.oxph != null) {
      var oxphEl = document.getElementById('statusOXPHValue');
      if (oxphEl) oxphEl.textContent = parseFloat(data.oxph).toFixed(1) + ' MW';
    }

    // Last Run
    if (data.lastRunTime) {
      var lastRunEl = document.getElementById('statusLastRunValue');
      if (lastRunEl) {
        var diff = Date.now() - new Date(data.lastRunTime).getTime();
        var mins = Math.floor(diff / 60000);
        if (mins < 1) lastRunEl.textContent = 'Just now';
        else if (mins < 60) lastRunEl.textContent = mins + 'm ago';
        else lastRunEl.textContent = Math.floor(mins / 60) + 'h ago';
      }
    }

    // PI System status
    if (data.piStatus != null) {
      var piDot = document.getElementById('statusPIDot');
      var piVal = document.getElementById('statusPIValue');
      if (piDot && piVal) {
        if (data.piStatus === 'connected') {
          piDot.className = 'status-dot green';
          piVal.textContent = 'Connected';
        } else if (data.piStatus === 'simulation') {
          piDot.className = 'status-dot amber';
          piVal.textContent = 'Simulation';
        } else {
          piDot.className = 'status-dot red';
          piVal.textContent = 'Offline';
        }
      }
    }

    // WebSocket
    if (data.wsStatus != null) {
      var wsDot = document.getElementById('statusWSDot');
      var wsVal = document.getElementById('statusWSValue');
      if (wsDot && wsVal) {
        wsDot.className = 'status-dot ' + (data.wsStatus ? 'green' : 'red');
        wsVal.textContent = data.wsStatus ? 'Live' : 'Disconnected';
      }
    }
  };

  // Load saved theme on page load
  var savedTheme = localStorage.getItem('theme');
  if (savedTheme) {
    document.documentElement.setAttribute('data-theme', savedTheme);
  }
})();
