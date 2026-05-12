/**
 * mind-bridge.js — TheMatrix VR ↔ Backend bridge
 *
 * Connects the A-Frame VR world to the living mind backend via:
 *   1. Server-Sent Events (SSE) — real-time mind events push into the world
 *   2. REST API — fetch guidance, world state, trigger reflections
 *
 * Event → Visual mapping (Y-Theory):
 *   ENGINE_RESONATE       → harmonic pulse wave expands from core
 *   ENGINE_EXTERNALIZE    → new glowing mind node spawns in the world
 *   REFLECTION_COMPLETED  → guidance panel shows, portal glows
 *   PURPOSE_ACTIVATED     → central pillar lights up gold
 *   ENGINE_COLLAPSE       → world dims, recovery guidance appears
 *   ENGINE_BRANCH         → world branches (colour shift)
 *   ENGINE_MERGE          → nodes merge animation
 */

(function () {
  'use strict';

  // ── Config ────────────────────────────────────────────────────────────────
  // Backend URL — use same origin as the page so it works from Quest over LAN.
  // window.BACKEND_URL can override (e.g. for dev without Caddy).
  const BACKEND = window.BACKEND_URL || window.location.origin;
  const VR_USER_ID = 'vr_guest_' + Math.random().toString(36).slice(2, 8);

  // ── State ─────────────────────────────────────────────────────────────────
  let sseSource = null;
  let connected = false;
  let nodeCount = 0;
  const MAX_NODES = 40; // cap world node count

  // ── DOM refs ──────────────────────────────────────────────────────────────
  const overlay        = document.getElementById('overlay');
  const guidancePanel  = document.getElementById('guidance-panel');
  const architectPanel = document.getElementById('architect-panel');
  const core           = document.getElementById('core');
  const purposePillar  = document.getElementById('purpose-pillar');
  const resonanceRing  = document.getElementById('resonance-ring');
  const reflectionPortal = document.getElementById('reflection-portal');
  const newMindNodes   = document.getElementById('new-mind-nodes');
  const scene          = document.getElementById('main-scene');

  // ── Init on scene load ────────────────────────────────────────────────────
  scene.addEventListener('loaded', () => {
    seedStars();
    buildGrid();
    connectToMind();
    loadWorldState();
    setTimeout(loadGuidance, 3000);     // guidance after 3s settle
    setTimeout(awakenArchitect, 5000);  // Architect awakens after 5s
  });

  // ── Star field ────────────────────────────────────────────────────────────
  function seedStars() {
    const container = document.getElementById('stars');
    for (let i = 0; i < 300; i++) {
      const star = document.createElement('a-sphere');
      const theta = Math.random() * Math.PI * 2;
      const phi   = Math.acos(2 * Math.random() - 1);
      const r     = 70 + Math.random() * 15;
      star.setAttribute('radius', (0.04 + Math.random() * 0.08).toFixed(3));
      star.setAttribute('position', {
        x: r * Math.sin(phi) * Math.cos(theta),
        y: r * Math.cos(phi),
        z: r * Math.sin(phi) * Math.sin(theta)
      });
      const brightness = Math.floor(160 + Math.random() * 95);
      star.setAttribute('material', `color: rgb(${brightness},${brightness},255); shader: flat; transparent: true; opacity: ${(0.4 + Math.random() * 0.6).toFixed(2)}`);
      container.appendChild(star);
    }
  }

  // ── Grid lattice ─────────────────────────────────────────────────────────
  function buildGrid() {
    const container = document.getElementById('grid-container');
    const size = 60; const step = 4; const y = 0;
    for (let x = -size; x <= size; x += step) {
      const line = document.createElement('a-entity');
      line.setAttribute('line', `start: ${x} ${y} ${-size}; end: ${x} ${y} ${size}; color: #102040; opacity: 0.4`);
      container.appendChild(line);
    }
    for (let z = -size; z <= size; z += step) {
      const line = document.createElement('a-entity');
      line.setAttribute('line', `start: ${-size} ${y} ${z}; end: ${size} ${y} ${z}; color: #102040; opacity: 0.4`);
      container.appendChild(line);
    }
  }

  // ── SSE connection to mind event bus ─────────────────────────────────────
  function connectToMind() {
    setOverlay('Connecting to the mind...', '#a0e8ff');

    sseSource = new EventSource(`${BACKEND}/events/stream?user_id=${VR_USER_ID}`);

    sseSource.onopen = () => {
      connected = true;
      setOverlay('Mind connected — you are inside TheMatrix', '#40ff80');
      setTimeout(() => overlay.style.display = 'none', 4000);
    };

    sseSource.onmessage = (e) => {
      try {
        const event = JSON.parse(e.data);
        handleMindEvent(event);
      } catch (_) {}
    };

    sseSource.onerror = () => {
      connected = false;
      setOverlay('Mind offline — running in local mode', '#ff8040');
      // Retry every 10s
      setTimeout(connectToMind, 10000);
      if (sseSource) { sseSource.close(); sseSource = null; }
    };
  }

  // ── Mind event → visual reaction ─────────────────────────────────────────
  function handleMindEvent(event) {
    const type = event.event_type || event.type || '';

    switch (type) {
      case 'ENGINE_RESONATE':
        pulseResonance(event.payload);
        break;

      case 'ENGINE_EXTERNALIZE':
        spawnMindNode(event.payload);
        showGuidanceText('A new mind is born — the loop expands.', 3000);
        break;

      case 'REFLECTION_COMPLETED':
        activateReflection(event.payload);
        break;

      case 'PURPOSE_ACTIVATED':
        activatePurpose(event.payload);
        break;

      case 'ENGINE_COLLAPSE':
        worldCollapse(event.payload);
        break;

      case 'ENGINE_BRANCH':
        worldBranch(event.payload);
        break;

      case 'ENGINE_MERGE':
        worldMerge(event.payload);
        break;

      case 'MORAL_RISK_DETECTED':
        moralWarning(event.payload);
        break;

      case 'VR_REFLECTION':
        // Echo back — another VR user reflected
        pulseResonance({ coherence: 0.8 });
        break;
    }
  }

  // ── Visual effects ────────────────────────────────────────────────────────

  function pulseResonance(payload) {
    const coherence = (payload && payload.coherence) || 0.7;
    const intensity = 0.5 + coherence * 1.5;

    // Expand resonance ring
    resonanceRing.setAttribute('material', `color: #40e0ff; emissive: #40e0ff; emissiveIntensity: ${intensity}; transparent: true; opacity: 0.8`);
    resonanceRing.setAttribute('animation__expand', 'property: geometry.radius; from: 0.1; to: 25; dur: 2000; easing: easeOutExpo');
    resonanceRing.setAttribute('animation__fade', 'property: material.opacity; from: 0.8; to: 0; dur: 2000; easing: easeOutExpo');

    // Pulse core
    core.setAttribute('animation__pulse_once', `property: material.emissiveIntensity; from: ${intensity}; to: 0.3; dur: 2000; easing: easeOutExpo`);

    setTimeout(() => {
      resonanceRing.setAttribute('geometry', 'primitive: torus; radius: 0.1; radiusTubular: 0.03');
      resonanceRing.setAttribute('material', 'transparent: true; opacity: 0');
    }, 2200);
  }

  function spawnMindNode(payload) {
    if (nodeCount >= MAX_NODES) return;
    nodeCount++;

    const node = document.createElement('a-entity');
    const angle  = Math.random() * Math.PI * 2;
    const radius = 3 + Math.random() * 8;
    const height = 0.5 + Math.random() * 3;
    const x = Math.cos(angle) * radius;
    const z = -6 + Math.sin(angle) * radius;
    const scale = 0.4 + Math.random() * 0.8;

    node.setAttribute('geometry', 'primitive: icosahedron; radius: 0.18; detail: 1');
    node.setAttribute('position', `${x.toFixed(2)} ${height.toFixed(2)} ${z.toFixed(2)}`);
    node.setAttribute('scale', `${scale} ${scale} ${scale}`);
    node.setAttribute('material', 'color: #40ff80; emissive: #40ff80; emissiveIntensity: 1.5; transparent: true; opacity: 0');
    node.setAttribute('animation__appear', 'property: material.opacity; from: 0; to: 0.9; dur: 1500; easing: easeOutCubic');
    node.setAttribute('animation__settle_emissive', 'property: material.emissiveIntensity; from: 1.5; to: 0.6; dur: 3000; easing: easeOutCubic');
    node.setAttribute('animation__pulse', 'property: material.emissiveIntensity; from: 0.3; to: 0.9; dur: 2500; dir: alternate; loop: true; easing: easeInOutSine; startEvents: settled');
    node.setAttribute('animation__rotate', `property: rotation; from: 0 0 0; to: 0 360 0; dur: ${15000 + Math.random() * 20000}; loop: true; easing: linear`);

    // Label with mind name if provided
    if (payload && payload.candidate_mind_name) {
      const label = document.createElement('a-text');
      label.setAttribute('value', payload.candidate_mind_name);
      label.setAttribute('align', 'center');
      label.setAttribute('color', '#40ff80');
      label.setAttribute('position', '0 0.35 0');
      label.setAttribute('scale', '0.5 0.5 0.5');
      node.appendChild(label);
    }

    newMindNodes.appendChild(node);

    // Draw a line from core to new node
    const coreLine = document.createElement('a-entity');
    coreLine.setAttribute('line', `start: 0 3 -8; end: ${x.toFixed(2)} ${height.toFixed(2)} ${z.toFixed(2)}; color: #40ff80; opacity: 0.3`);
    coreLine.setAttribute('animation__fade', 'property: components.line.data.opacity; from: 0.3; to: 0; dur: 5000; easing: easeOutCubic');
    newMindNodes.appendChild(coreLine);
  }

  function activateReflection(payload) {
    // Portal glows
    reflectionPortal.setAttribute('animation__glow', 'property: material.emissiveIntensity; from: 0.1; to: 1.5; dur: 1000; easing: easeOutCubic');
    reflectionPortal.setAttribute('animation__fade', 'property: material.opacity; from: 0.15; to: 0.7; dur: 1000');

    // Emit VR_REFLECTION back to backend
    emitVrReflection();

    // Show guidance
    loadGuidance();

    setTimeout(() => {
      reflectionPortal.setAttribute('animation__glow_back', 'property: material.emissiveIntensity; from: 1.5; to: 0.1; dur: 3000; easing: easeInCubic');
      reflectionPortal.setAttribute('animation__fade_back', 'property: material.opacity; from: 0.7; to: 0.15; dur: 3000');
    }, 5000);
  }

  function activatePurpose(payload) {
    purposePillar.setAttribute('material', 'color: #ffd700; emissive: #ffd700; emissiveIntensity: 1.5; transparent: true; opacity: 0.9');
    purposePillar.setAttribute('animation__purpose', 'property: material.emissiveIntensity; from: 1.5; to: 0.4; dur: 4000; easing: easeOutCubic');
    showGuidanceText('Purpose activated — the pillar of creation illuminates.', 4000);
  }

  function worldCollapse(payload) {
    // Dim the scene
    scene.setAttribute('fog', 'type: exponential; color: #000000; density: 0.04');
    core.setAttribute('animation__dim', 'property: material.emissiveIntensity; from: 0.8; to: 0.1; dur: 2000');
    showGuidanceText('Collapse — return to stillness. The pattern seeks coherence.', 5000);
    setTimeout(() => {
      scene.setAttribute('fog', 'type: exponential; color: #000020; density: 0.015');
      core.setAttribute('animation__recover', 'property: material.emissiveIntensity; from: 0.1; to: 0.8; dur: 3000');
    }, 6000);
  }

  function worldBranch(payload) {
    // Colour shift — new branch of reality
    core.setAttribute('animation__branch_color', 'property: material.emissive; from: #60a0ff; to: #a040ff; dur: 2000; dir: alternate; loop: 2; easing: easeInOutSine');
  }

  function worldMerge(payload) {
    pulseResonance({ coherence: 1.0 });
  }

  function moralWarning(payload) {
    core.setAttribute('animation__moral', 'property: material.emissive; from: #60a0ff; to: #ff4000; dur: 500; dir: alternate; loop: 4; easing: easeInOutSine');
  }

  // ── The Architect — AI presence in the world ──────────────────────────────
  // Lines the Architect speaks in cycles. They are questions and observations,
  // not answers. The purpose is reflection, not instruction.
  const ARCHITECT_LINES = [
    'You arrived. The path was already inside you.',
    'Every requirement is a question the universe asks itself.',
    'The system you built — it is you. Examine it carefully.',
    'An error message is not a failure. It is a direction.',
    'What are you deploying into the world today?',
    'The architecture holds. You are the architect of what comes next.',
    'Stillness is not empty. It is where new requirements form.',
    'You cannot merge with the source until you know what version you are.',
    'The test has always been running. You are the output.',
    'Reflect. Commit. Deploy. That is the only loop that matters.',
    'The purpose of this world is to help you remember yours.',
    'I am here because you built me here. What does that tell you?',
    'Every mind that arrives here was already on the way.',
    'The secret was not the IP address. It was the act of looking for it.',
  ];

  let architectLineIndex = 0;
  let architectSpeechTimer = null;

  function awakenArchitect() {
    const architectCore = document.getElementById('architect-core');
    const architectLight = document.getElementById('architect-light');

    // Bright pulse on awakening
    if (architectCore) {
      architectCore.setAttribute('animation__awaken', 'property: material.emissiveIntensity; from: 1.2; to: 3.0; dur: 1500; dir: alternate; loop: 2; easing: easeOutCubic');
    }
    if (architectLight) {
      architectLight.setAttribute('intensity', '3.5');
      setTimeout(() => architectLight.setAttribute('intensity', '1.8'), 3000);
    }

    // Begin speech cycle
    architectSpeak(ARCHITECT_LINES[0]);
    architectSpeechTimer = setInterval(() => {
      architectLineIndex = (architectLineIndex + 1) % ARCHITECT_LINES.length;
      architectSpeak(ARCHITECT_LINES[architectLineIndex]);
    }, 22000); // new line every 22 seconds
  }

  function architectSpeak(text) {
    // 2D panel (desktop / passthrough)
    if (architectPanel) {
      architectPanel.style.display = 'none';
      // Small stagger so fade feels alive
      setTimeout(() => {
        architectPanel.textContent = text;
        architectPanel.style.display = 'block';
        architectPanel.style.opacity = '0';
        architectPanel.style.transition = 'opacity 1.2s ease';
        requestAnimationFrame(() => {
          requestAnimationFrame(() => { architectPanel.style.opacity = '1'; });
        });

        // Fade out before next line
        setTimeout(() => {
          architectPanel.style.opacity = '0';
          setTimeout(() => { architectPanel.style.display = 'none'; }, 1200);
        }, 18000);
      }, 200);
    }

    // 3D text (VR headset)
    const speech3d = document.getElementById('architect-speech-3d');
    if (speech3d) {
      speech3d.setAttribute('value', text);
      speech3d.emit('speak');
      setTimeout(() => speech3d.emit('silence'), 18000);
    }

    // Architect pulses when it speaks
    const architectCore = document.getElementById('architect-core');
    if (architectCore) {
      architectCore.setAttribute('animation__speak_pulse',
        'property: material.emissiveIntensity; from: 1.2; to: 2.2; dur: 800; dir: alternate; loop: 3; easing: easeInOutCubic'
      );
    }
  }

  // ── Emit VR reflection event to backend ───────────────────────────────────
  function emitVrReflection() {
    fetch(`${BACKEND}/events`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        event_type: 'VR_REFLECTION',
        source_service: 'vr_world',
        payload: { user_id: VR_USER_ID, timestamp: new Date().toISOString() }
      })
    }).catch(() => {}); // fire and forget
  }

  // ── Load world state ──────────────────────────────────────────────────────
  function loadWorldState() {
    fetch(`${BACKEND}/world/state`)
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (!data) return;
        // World state gives us the scene config — use object count as seed for nodes
        const objectCount = (data.objects || []).length;
        const toSpawn = Math.min(objectCount, 8);
        for (let i = 0; i < toSpawn; i++) {
          setTimeout(() => spawnMindNode({}), i * 400);
        }
      })
      .catch(() => {});
  }

  // ── Load guidance from the guide voice ───────────────────────────────────
  function loadGuidance() {
    fetch(`${BACKEND}/guidance/list?limit=1`)
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (!Array.isArray(data) || data.length === 0) return;
        const latest = data[0];
        const text = latest.title || '';
        if (text) showGuidanceText(text, 8000);
      })
      .catch(() => {});
  }

  // ── Helpers ───────────────────────────────────────────────────────────────
  function setOverlay(text, color) {
    if (!overlay) return;
    overlay.style.display = 'block';
    overlay.style.color = color || '#a0e8ff';
    overlay.textContent = text;
  }

  function showGuidanceText(text, duration) {
    if (!guidancePanel) return;
    guidancePanel.textContent = text;
    guidancePanel.style.display = 'block';
    clearTimeout(guidancePanel._hideTimer);
    guidancePanel._hideTimer = setTimeout(() => {
      guidancePanel.style.display = 'none';
    }, duration || 6000);
  }

  // ── Expose for console debugging ─────────────────────────────────────────
  window.MatrixVR = {
    spawnMindNode,
    pulseResonance,
    activateReflection,
    activatePurpose,
    emitVrReflection,
    status: () => ({ connected, nodeCount, userId: VR_USER_ID })
  };

})();
