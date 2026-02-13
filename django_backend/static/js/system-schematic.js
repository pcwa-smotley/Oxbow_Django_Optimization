// system-schematic.js - Animated SVG Water System Schematic

(function () {
  'use strict';

  let schematicVisible = true;
  let animationFrameId = null;
  let particles = [];

  const COLORS = {
    light: {
      bg: '#f0f4f8',
      nodeFill: '#ffffff',
      nodeStroke: '#667eea',
      pathStroke: '#3498db',
      text: '#2c3e50',
      textSecondary: '#718096',
      particleColor: '#3498db',
      reservoirWater: '#3498db',
      reservoirBg: '#e8f0fe',
      highlightStroke: '#667eea'
    },
    dark: {
      bg: 'transparent',
      nodeFill: 'rgba(15, 23, 42, 0.8)',
      nodeStroke: '#00d4ff',
      pathStroke: 'rgba(0, 212, 255, 0.4)',
      text: '#e2e8f0',
      textSecondary: '#94a3b8',
      particleColor: '#00d4ff',
      reservoirWater: '#00d4ff',
      reservoirBg: 'rgba(0, 212, 255, 0.08)',
      highlightStroke: '#00d4ff'
    }
  };

  function getColors() {
    return document.documentElement.getAttribute('data-theme') === 'dark'
      ? COLORS.dark : COLORS.light;
  }

  function createSVG() {
    var wrapper = document.getElementById('schematicSvgWrapper');
    if (!wrapper) return;

    var c = getColors();
    var svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', '0 0 900 260');
    svg.setAttribute('preserveAspectRatio', 'xMidYMid meet');
    svg.id = 'schematicSvg';

    // Define flow paths
    var paths = [
      { id: 'pathMFRA', d: 'M 120 70 L 280 70 Q 310 70 310 100 L 310 130', label: 'MFRA', dataKey: 'mfra' },
      { id: 'pathR30', d: 'M 120 130 L 310 130', label: 'R30', dataKey: 'r30' },
      { id: 'pathR4', d: 'M 120 190 L 280 190 Q 310 190 310 160 L 310 130', label: 'R4', dataKey: 'r4' },
      { id: 'pathOXPH', d: 'M 530 130 L 700 130', label: 'OXPH', dataKey: 'oxph' },
      { id: 'pathSpill', d: 'M 470 200 Q 470 230 500 230 L 700 230', label: 'Spill', dataKey: 'spill' }
    ];

    // Defs for gradients and markers
    var defs = '<defs>' +
      '<linearGradient id="waterGrad" x1="0" y1="0" x2="0" y2="1">' +
      '<stop offset="0%" stop-color="' + c.reservoirWater + '" stop-opacity="0.3"/>' +
      '<stop offset="100%" stop-color="' + c.reservoirWater + '" stop-opacity="0.7"/>' +
      '</linearGradient>' +
      '<filter id="glow"><feGaussianBlur stdDeviation="2" result="blur"/>' +
      '<feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge></filter>' +
      '</defs>';

    // Build flow paths
    var pathsSvg = paths.map(function (p) {
      return '<path id="' + p.id + '" d="' + p.d + '" fill="none" stroke="' + c.pathStroke + '" ' +
        'stroke-width="3" stroke-linecap="round" opacity="0.6"/>';
    }).join('');

    // Inflow Nodes (left side)
    var inflows =
      // MFRA Node
      '<g class="schematic-node" data-node="mfra">' +
      '<rect x="20" y="45" width="100" height="50" rx="10" fill="' + c.nodeFill + '" stroke="' + c.nodeStroke + '" stroke-width="2"/>' +
      '<text x="70" y="65" text-anchor="middle" fill="' + c.text + '" font-size="11" font-weight="600">MFRA</text>' +
      '<text x="70" y="82" text-anchor="middle" fill="' + c.textSecondary + '" font-size="10" id="schMfraValue">-- MW</text>' +
      '</g>' +
      // R30 Node
      '<g class="schematic-node" data-node="r30">' +
      '<rect x="20" y="105" width="100" height="50" rx="10" fill="' + c.nodeFill + '" stroke="' + c.nodeStroke + '" stroke-width="2"/>' +
      '<text x="70" y="125" text-anchor="middle" fill="' + c.text + '" font-size="11" font-weight="600">R30</text>' +
      '<text x="70" y="142" text-anchor="middle" fill="' + c.textSecondary + '" font-size="10" id="schR30Value">-- CFS</text>' +
      '</g>' +
      // R4 Node
      '<g class="schematic-node" data-node="r4">' +
      '<rect x="20" y="165" width="100" height="50" rx="10" fill="' + c.nodeFill + '" stroke="' + c.nodeStroke + '" stroke-width="2"/>' +
      '<text x="70" y="185" text-anchor="middle" fill="' + c.text + '" font-size="11" font-weight="600">R4</text>' +
      '<text x="70" y="202" text-anchor="middle" fill="' + c.textSecondary + '" font-size="10" id="schR4Value">-- CFS</text>' +
      '</g>';

    // ABAY Reservoir (center)
    var reservoirW = 180, reservoirH = 140;
    var rx = 340, ry = 60;
    var reservoir =
      '<g class="schematic-node" data-node="abay">' +
      // Reservoir outline
      '<rect x="' + rx + '" y="' + ry + '" width="' + reservoirW + '" height="' + reservoirH + '" rx="12" ' +
      'fill="' + c.reservoirBg + '" stroke="' + c.nodeStroke + '" stroke-width="2.5"/>' +
      // Water level (will be animated)
      '<rect id="schWaterLevel" x="' + (rx + 3) + '" y="' + (ry + 70) + '" width="' + (reservoirW - 6) + '" height="' + (reservoirH - 73) + '" rx="9" ' +
      'fill="url(#waterGrad)" opacity="0.8"/>' +
      // Labels
      '<text x="' + (rx + reservoirW / 2) + '" y="' + (ry + 25) + '" text-anchor="middle" fill="' + c.text + '" font-size="14" font-weight="700">ABAY</text>' +
      '<text x="' + (rx + reservoirW / 2) + '" y="' + (ry + 50) + '" text-anchor="middle" fill="' + c.textSecondary + '" font-size="11" id="schAbayElev">-- ft</text>' +
      '<text x="' + (rx + reservoirW / 2) + '" y="' + (ry + 70) + '" text-anchor="middle" fill="' + c.textSecondary + '" font-size="9" id="schAbayStatus">--</text>' +
      '</g>';

    // OXPH Powerhouse (right)
    var oxphNode =
      '<g class="schematic-node" data-node="oxph">' +
      '<rect x="700" y="95" width="120" height="70" rx="10" fill="' + c.nodeFill + '" stroke="' + c.nodeStroke + '" stroke-width="2"/>' +
      '<text x="760" y="120" text-anchor="middle" fill="' + c.text + '" font-size="12" font-weight="700">OXPH</text>' +
      '<text x="760" y="140" text-anchor="middle" fill="' + c.textSecondary + '" font-size="11" id="schOxphValue">-- MW</text>' +
      '<text x="760" y="156" text-anchor="middle" fill="' + c.textSecondary + '" font-size="9" id="schOxphCfs">-- CFS</text>' +
      '</g>';

    // Downstream / Spill label
    var downstream =
      '<g class="schematic-node" data-node="downstream">' +
      '<rect x="700" y="205" width="120" height="50" rx="10" fill="' + c.nodeFill + '" stroke="' + c.pathStroke + '" stroke-width="1.5" opacity="0.6"/>' +
      '<text x="760" y="228" text-anchor="middle" fill="' + c.textSecondary + '" font-size="10">Spillway</text>' +
      '<text x="760" y="244" text-anchor="middle" fill="' + c.textSecondary + '" font-size="10" id="schSpillValue">0 CFS</text>' +
      '</g>';

    // Flow direction arrows
    var arrows =
      '<polygon points="280,66 290,70 280,74" fill="' + c.pathStroke + '" opacity="0.7"/>' +
      '<polygon points="280,126 290,130 280,134" fill="' + c.pathStroke + '" opacity="0.7"/>' +
      '<polygon points="280,186 290,190 280,194" fill="' + c.pathStroke + '" opacity="0.7"/>' +
      '<polygon points="660,126 670,130 660,134" fill="' + c.pathStroke + '" opacity="0.7"/>';

    // Particle container
    var particleContainer = '<g id="schParticles"></g>';

    svg.innerHTML = defs + pathsSvg + arrows + inflows + reservoir + oxphNode + downstream + particleContainer;

    wrapper.innerHTML = '';
    wrapper.appendChild(svg);

    // Drill-down click handlers on each node
    var clickableNodes = svg.querySelectorAll('[data-node]');
    for (var ni = 0; ni < clickableNodes.length; ni++) {
      (function (node) {
        node.addEventListener('click', function () {
          var key = node.getAttribute('data-node');
          if (key && typeof window.openSchematicDrillDown === 'function') {
            window.openSchematicDrillDown(key);
          }
        });
      })(clickableNodes[ni]);
    }

    // Start animation
    startParticleAnimation();
  }

  // Particle Animation
  function startParticleAnimation() {
    if (animationFrameId) cancelAnimationFrame(animationFrameId);
    particles = [];

    var pathIds = ['pathMFRA', 'pathR30', 'pathR4', 'pathOXPH'];
    var svg = document.getElementById('schematicSvg');
    if (!svg) return;

    // Create particles for each path
    pathIds.forEach(function (id) {
      var path = document.getElementById(id);
      if (!path) return;
      var length = path.getTotalLength();
      var count = 3;
      for (var i = 0; i < count; i++) {
        particles.push({
          pathId: id,
          path: path,
          length: length,
          offset: (i / count) * length,
          speed: 0.5 + Math.random() * 0.3
        });
      }
    });

    function animate() {
      var c = getColors();
      var container = document.getElementById('schParticles');
      if (!container) return;

      container.innerHTML = '';
      particles.forEach(function (p) {
        p.offset += p.speed;
        if (p.offset >= p.length) p.offset = 0;

        try {
          var point = p.path.getPointAtLength(p.offset);
          var circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
          circle.setAttribute('cx', point.x);
          circle.setAttribute('cy', point.y);
          circle.setAttribute('r', '3');
          circle.setAttribute('fill', c.particleColor);
          circle.setAttribute('opacity', '0.7');
          container.appendChild(circle);
        } catch (e) {
          // Path may not be ready
        }
      });

      animationFrameId = requestAnimationFrame(animate);
    }

    animationFrameId = requestAnimationFrame(animate);
  }

  // Update schematic data values
  window.updateSchematicData = function (data) {
    if (!data) return;

    var setTextSafe = function (id, text) {
      var el = document.getElementById(id);
      if (el) el.textContent = text;
    };

    if (data.mfra != null) setTextSafe('schMfraValue', parseFloat(data.mfra).toFixed(1) + ' MW');
    if (data.r30 != null) setTextSafe('schR30Value', Math.round(data.r30) + ' CFS');
    if (data.r4 != null) setTextSafe('schR4Value', Math.round(data.r4) + ' CFS');
    if (data.elevation != null) setTextSafe('schAbayElev', parseFloat(data.elevation).toFixed(1) + ' ft');
    if (data.oxph != null) {
      setTextSafe('schOxphValue', parseFloat(data.oxph).toFixed(1) + ' MW');
      var cfs = 163.73 * parseFloat(data.oxph) + 83.0;
      setTextSafe('schOxphCfs', Math.round(cfs) + ' CFS');
    }
    if (data.spill != null) setTextSafe('schSpillValue', Math.round(data.spill) + ' CFS');

    // Update water level visual
    if (data.elevation != null) {
      var elev = parseFloat(data.elevation);
      var minElev = 1166, maxElev = 1175;
      var pct = Math.max(0, Math.min(1, (elev - minElev) / (maxElev - minElev)));
      var reservoirH = 140, ry = 60;
      var waterH = Math.round(pct * (reservoirH - 10));
      var waterY = ry + reservoirH - waterH - 3;
      var waterEl = document.getElementById('schWaterLevel');
      if (waterEl) {
        waterEl.setAttribute('y', waterY);
        waterEl.setAttribute('height', Math.max(0, waterH));
      }

      // Status text
      var status = elev < 1168 ? 'LOW' : elev > 1174 ? 'HIGH' : 'Normal';
      setTextSafe('schAbayStatus', status);
    }
  };

  // Toggle schematic visibility
  window.toggleSchematic = function () {
    var container = document.getElementById('systemSchematicContainer');
    if (!container) return;
    schematicVisible = !schematicVisible;
    container.style.display = schematicVisible ? 'block' : 'none';
    if (schematicVisible && !document.getElementById('schematicSvg')) {
      createSVG();
    }
  };

  // Rebuild on theme change
  if (typeof registerChartReinit === 'function') {
    registerChartReinit(function () {
      if (schematicVisible) createSVG();
    });
  }

  // Init on DOM ready
  function init() {
    createSVG();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
