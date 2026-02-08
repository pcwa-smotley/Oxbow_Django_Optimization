// echart-theme.js - Custom ECharts themes for ABAY Dashboard

(function () {
  // ==========================================
  // LIGHT THEME - "oxbow-light"
  // ==========================================
  const lightTheme = {
    color: [
      '#e74c3c', '#f39c12', '#3498db', '#27ae60',
      '#9b59b6', '#1abc9c', '#e67e22', '#2980b9'
    ],
    backgroundColor: 'transparent',
    textStyle: { fontFamily: "'Inter', 'Segoe UI', sans-serif" },
    title: {
      textStyle: { color: '#2c3e50', fontWeight: 600 },
      subtextStyle: { color: '#718096' }
    },
    legend: {
      textStyle: { color: '#2c3e50' },
      pageTextStyle: { color: '#718096' }
    },
    tooltip: {
      backgroundColor: 'rgba(255, 255, 255, 0.95)',
      borderColor: 'rgba(0, 0, 0, 0.08)',
      borderWidth: 1,
      textStyle: { color: '#2c3e50', fontSize: 13 },
      extraCssText: 'backdrop-filter: blur(12px); border-radius: 10px; box-shadow: 0 8px 24px rgba(0,0,0,0.12); padding: 12px 16px;'
    },
    axisPointer: {
      lineStyle: { color: 'rgba(102, 126, 234, 0.4)', width: 1, type: 'dashed' },
      crossStyle: { color: 'rgba(102, 126, 234, 0.4)' },
      label: { backgroundColor: '#667eea', color: '#fff' }
    },
    xAxis: {
      axisLine: { lineStyle: { color: '#e2e8f0' } },
      axisTick: { lineStyle: { color: '#e2e8f0' } },
      axisLabel: { color: '#718096', fontSize: 11 },
      splitLine: { lineStyle: { color: 'rgba(0, 0, 0, 0.04)' } }
    },
    yAxis: {
      axisLine: { lineStyle: { color: '#e2e8f0' } },
      axisTick: { lineStyle: { color: '#e2e8f0' } },
      axisLabel: { color: '#718096', fontSize: 11 },
      splitLine: { lineStyle: { color: 'rgba(0, 0, 0, 0.06)' } }
    },
    dataZoom: [{
      type: 'slider',
      backgroundColor: '#f7fafc',
      borderColor: '#e2e8f0',
      fillerColor: 'rgba(102, 126, 234, 0.12)',
      handleStyle: { color: '#667eea', borderColor: '#667eea' },
      textStyle: { color: '#718096' },
      dataBackground: {
        lineStyle: { color: 'rgba(102, 126, 234, 0.3)' },
        areaStyle: { color: 'rgba(102, 126, 234, 0.08)' }
      }
    }],
    line: {
      smooth: false,
      symbolSize: 0,
      lineStyle: { width: 2 }
    },
    gauge: {
      axisLine: {
        lineStyle: {
          width: 12,
          color: [[0.2, '#e74c3c'], [0.4, '#f39c12'], [0.7, '#27ae60'], [0.9, '#f39c12'], [1, '#e74c3c']]
        }
      },
      pointer: { width: 5, length: '60%' },
      axisTick: { length: 6, lineStyle: { color: '#718096' } },
      splitLine: { length: 12, lineStyle: { color: '#718096' } },
      axisLabel: { color: '#718096', fontSize: 10 },
      detail: { color: '#2c3e50', fontSize: 20, fontWeight: 600 },
      title: { color: '#718096' }
    }
  };

  // ==========================================
  // DARK THEME - "oxbow-dark" (Neon Control Room)
  // ==========================================
  const darkTheme = {
    color: [
      '#00d4ff', '#ff006e', '#00ff88', '#ffbe0b',
      '#7c3aed', '#06b6d4', '#f97316', '#a855f7'
    ],
    backgroundColor: 'transparent',
    textStyle: { fontFamily: "'Inter', 'Segoe UI', sans-serif" },
    title: {
      textStyle: { color: '#e2e8f0', fontWeight: 600 },
      subtextStyle: { color: '#94a3b8' }
    },
    legend: {
      textStyle: { color: '#94a3b8' },
      pageTextStyle: { color: '#64748b' }
    },
    tooltip: {
      backgroundColor: 'rgba(15, 23, 42, 0.92)',
      borderColor: 'rgba(0, 212, 255, 0.15)',
      borderWidth: 1,
      textStyle: { color: '#e2e8f0', fontSize: 13 },
      extraCssText: 'backdrop-filter: blur(16px); border-radius: 10px; box-shadow: 0 8px 24px rgba(0,0,0,0.4), 0 0 15px rgba(0, 212, 255, 0.08); padding: 12px 16px;'
    },
    axisPointer: {
      lineStyle: { color: 'rgba(0, 212, 255, 0.3)', width: 1, type: 'dashed' },
      crossStyle: { color: 'rgba(0, 212, 255, 0.3)' },
      label: { backgroundColor: 'rgba(0, 212, 255, 0.8)', color: '#0a0e1a' }
    },
    xAxis: {
      axisLine: { lineStyle: { color: 'rgba(0, 212, 255, 0.12)' } },
      axisTick: { lineStyle: { color: 'rgba(0, 212, 255, 0.12)' } },
      axisLabel: { color: '#64748b', fontSize: 11 },
      splitLine: { lineStyle: { color: 'rgba(255, 255, 255, 0.03)' } }
    },
    yAxis: {
      axisLine: { lineStyle: { color: 'rgba(0, 212, 255, 0.12)' } },
      axisTick: { lineStyle: { color: 'rgba(0, 212, 255, 0.12)' } },
      axisLabel: { color: '#64748b', fontSize: 11 },
      splitLine: { lineStyle: { color: 'rgba(255, 255, 255, 0.04)' } }
    },
    dataZoom: [{
      type: 'slider',
      backgroundColor: 'rgba(10, 14, 26, 0.6)',
      borderColor: 'rgba(0, 212, 255, 0.1)',
      fillerColor: 'rgba(0, 212, 255, 0.08)',
      handleStyle: { color: '#00d4ff', borderColor: '#00d4ff' },
      textStyle: { color: '#64748b' },
      dataBackground: {
        lineStyle: { color: 'rgba(0, 212, 255, 0.25)' },
        areaStyle: { color: 'rgba(0, 212, 255, 0.05)' }
      }
    }],
    line: {
      smooth: false,
      symbolSize: 0,
      lineStyle: { width: 2 }
    },
    gauge: {
      axisLine: {
        lineStyle: {
          width: 12,
          color: [
            [0.2, '#ff006e'],
            [0.4, '#ffbe0b'],
            [0.7, '#00ff88'],
            [0.9, '#ffbe0b'],
            [1, '#ff006e']
          ]
        }
      },
      pointer: { width: 5, length: '60%', itemStyle: { color: '#00d4ff' } },
      axisTick: { length: 6, lineStyle: { color: 'rgba(148, 163, 184, 0.3)' } },
      splitLine: { length: 12, lineStyle: { color: 'rgba(148, 163, 184, 0.4)' } },
      axisLabel: { color: '#64748b', fontSize: 10 },
      detail: { color: '#e2e8f0', fontSize: 20, fontWeight: 600 },
      title: { color: '#94a3b8' }
    }
  };

  // Register themes
  echarts.registerTheme('oxbow-light', lightTheme);
  echarts.registerTheme('oxbow-dark', darkTheme);

  // Helper to get current theme name
  window.getEChartsTheme = function () {
    return document.documentElement.getAttribute('data-theme') === 'dark'
      ? 'oxbow-dark'
      : 'oxbow-light';
  };

  // Helper to init chart with correct theme
  window.initEChart = function (domId) {
    const dom = document.getElementById(domId);
    if (!dom) return null;
    const existing = echarts.getInstanceByDom(dom);
    if (existing) existing.dispose();
    return echarts.init(dom, getEChartsTheme());
  };

  // Re-init all charts when theme changes
  window.reinitChartsForTheme = function () {
    // This will be called by the dark mode toggle
    // Each chart module should register a reinit callback
    if (window._echartReinitCallbacks) {
      window._echartReinitCallbacks.forEach(function (cb) { cb(); });
    }
  };

  window._echartReinitCallbacks = [];
  window.registerChartReinit = function (callback) {
    window._echartReinitCallbacks.push(callback);
  };

  // Auto-resize charts on window resize
  window.addEventListener('resize', function () {
    if (window._resizeTimer) clearTimeout(window._resizeTimer);
    window._resizeTimer = setTimeout(function () {
      document.querySelectorAll('[_echarts_instance_]').forEach(function (el) {
        var instance = echarts.getInstanceByDom(el);
        if (instance) instance.resize();
      });
    }, 200);
  });
})();
