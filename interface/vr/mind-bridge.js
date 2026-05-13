/**
 * mind-bridge.js ΓÇö TheMatrix VR Γåö Backend bridge
 *
 * Connects the A-Frame VR world to the living mind backend via:
 *   1. Server-Sent Events (SSE) ΓÇö real-time mind events push into the world
 *   2. REST API ΓÇö fetch guidance, world state, trigger reflections
 *
 * Event ΓåÆ Visual mapping (Y-Theory):
 *   ENGINE_RESONATE       ΓåÆ harmonic pulse wave expands from core
 *   ENGINE_EXTERNALIZE    ΓåÆ new glowing mind node spawns in the world
 *   REFLECTION_COMPLETED  ΓåÆ guidance panel shows, portal glows
 *   PURPOSE_ACTIVATED     ΓåÆ central pillar lights up gold
 *   ENGINE_COLLAPSE       ΓåÆ world dims, recovery guidance appears
 *   ENGINE_BRANCH         ΓåÆ world branches (colour shift)
 *   ENGINE_MERGE          ΓåÆ nodes merge animation
 */

(function () {
  'use strict';

  // ΓöÇΓöÇ Config ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
  // Backend URL ΓÇö use same origin as the page so it works from Quest over LAN.
  // window.BACKEND_URL can override (e.g. for dev without Caddy).
  const BACKEND = window.BACKEND_URL || window.location.origin;
  const VR_USER_ID = 'vr_guest_' + Math.random().toString(36).slice(2, 8);

  // ΓöÇΓöÇ State ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
  let sseSource = null;
  let connected = false;
  let nodeCount = 0;
  const MAX_NODES = 40; // cap world node count

  // Planet registry ΓÇö id ΓåÆ { entity, planet, orbitRadius, angle, orbitSpeed }
  // Lets events find and update the right planet without a full reload.
  const planetRegistry = {};

  // ΓöÇΓöÇ DOM refs ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
  const overlay        = document.getElementById('overlay');
  const guidancePanel  = document.getElementById('guidance-panel');
  const architectPanel = document.getElementById('architect-panel');
  const nodeTooltip    = document.getElementById('node-tooltip');
  const loginPortal    = document.getElementById('login-portal');
  const identityBadge  = document.getElementById('identity-badge');
  const identityName   = document.getElementById('identity-name');
  const core           = document.getElementById('core');
  const purposePillar  = document.getElementById('purpose-pillar');
  const resonanceRing  = document.getElementById('resonance-ring');
  const reflectionPortal = document.getElementById('reflection-portal');
  const newMindNodes    = document.getElementById('new-mind-nodes');
  const connectionLayer = document.getElementById('connection-layer');
  const scene           = document.getElementById('main-scene');

  // ΓöÇΓöÇ Identity state ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
  let currentIdentity = null;

  // ΓöÇΓöÇ Auth helpers ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
  function getToken()   { return localStorage.getItem('matrix_token'); }
  function setToken(t)  { localStorage.setItem('matrix_token', t); }
  function clearToken() { localStorage.removeItem('matrix_token'); }

  // ΓöÇΓöÇ Login portal wiring ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
  const btnLogin    = document.getElementById('btn-login');
  const btnRegister = document.getElementById('btn-register');
  const btnGuest    = document.getElementById('btn-guest');
  const inpEmail    = document.getElementById('inp-email');
  const inpPassword = document.getElementById('inp-password');
  const loginError  = document.getElementById('login-error');

  function setLoginError(msg) { if (loginError) loginError.textContent = msg; }

  async function doLogin(email, password) {
    setLoginError('');
    try {
      const r = await fetch(`${BACKEND}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      });
      if (!r.ok) {
        const err = await r.json().catch(() => ({}));
        setLoginError(err.detail || 'Login failed. Check credentials.');
        return false;
      }
      const data = await r.json();
      setToken(data.access_token);
      return true;
    } catch (_) { setLoginError('Cannot reach the mind. Try again.'); return false; }
  }

  async function doRegister(email, password) {
    setLoginError('');
    try {
      const r = await fetch(`${BACKEND}/auth/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password, display_name: email.split('@')[0] }),
      });
      if (!r.ok) {
        const err = await r.json().catch(() => ({}));
        setLoginError(err.detail || 'Registration failed.'); return false;
      }
      return await doLogin(email, password);
    } catch (_) { setLoginError('Cannot reach the mind. Try again.'); return false; }
  }

  async function fetchIdentity() {
    const token = getToken();
    if (!token) return null;
    try {
      const r = await fetch(`${BACKEND}/auth/vr-identity`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (!r.ok) { clearToken(); return null; }
      return await r.json();
    } catch (_) { return null; }
  }

  function dismissPortal(identity) {
    currentIdentity = identity;
    if (loginPortal) {
      loginPortal.style.transition = 'opacity 0.7s';
      loginPortal.style.opacity = '0';
      setTimeout(() => { loginPortal.style.display = 'none'; }, 750);
    }
    applyIdentity(identity);
    const canvas = document.querySelector('canvas');
    if (canvas) canvas.focus();
  }

  function applyIdentity(identity) {
    if (!identity) {
      identity = { role: 'guest', name: 'Observer', label: 'Observer',
                   color: '#607080', position: { x: 0, y: 1.6, z: 14 } };
      currentIdentity = identity;
    }

    // Move camera rig to identity position
    const rig = document.getElementById('rig');
    if (rig) {
      const p = identity.position;
      rig.setAttribute('position', `${p.x} ${p.y} ${p.z}`);
      // Face toward origin
      const angle = Math.atan2(p.x, p.z) * (180 / Math.PI);
      rig.setAttribute('rotation', `0 ${(angle + 180).toFixed(1)} 0`);
    }

    // Show identity badge top-right
    if (identityBadge && identityName) {
      identityName.textContent = identity.label || identity.name;
      identityBadge.className = identity.role === 'founder' ? 'founder' : '';
      identityBadge.style.display = 'flex';
    }

    // Place a glowing marker at their position in the world
    spawnIdentityMarker(identity);

    // Personalised greeting
    if (identity.role === 'founder') {
      setTimeout(() => showGuidanceText('Welcome back, Founder. You stand at the center of The Matrix.', 7000), 2000);
      if (core) core.setAttribute('animation__founder_greet',
        'property: material.emissive; from: #60a0ff; to: #ffd700; dur: 2000; dir: alternate; loop: 2; easing: easeInOutSine');
    } else if (identity.role === 'member') {
      setTimeout(() => showGuidanceText(`Welcome, ${identity.name}. Your node is held.`, 5000), 2000);
    } else {
      setTimeout(() => showGuidanceText('You enter as an observer. The world sees you.', 4000), 2000);
    }
  }

  function spawnIdentityMarker(identity) {
    const p = identity.position;
    const marker = document.createElement('a-entity');
    marker.setAttribute('position', `${p.x} ${(p.y + 0.7).toFixed(2)} ${p.z}`);

    const dot = document.createElement('a-sphere');
    dot.setAttribute('radius', '0.13');
    dot.setAttribute('material',
      `color: ${identity.color}; emissive: ${identity.color}; emissiveIntensity: 1.5; transparent: true; opacity: 0.9`);
    dot.setAttribute('animation__pulse',
      'property: material.emissiveIntensity; from: 0.9; to: 2.2; dur: 1600; dir: alternate; loop: true; easing: easeInOutSine');
    marker.appendChild(dot);

    const lbl = document.createElement('a-text');
    lbl.setAttribute('value', identity.label || identity.name);
    lbl.setAttribute('align', 'center');
    lbl.setAttribute('color', identity.color);
    lbl.setAttribute('position', '0 0.3 0');
    lbl.setAttribute('scale', '0.65 0.65 0.65');
    lbl.setAttribute('look-at', '#camera');
    marker.appendChild(lbl);

    newMindNodes.appendChild(marker);
  }

  // Button wiring
  if (btnLogin) btnLogin.addEventListener('click', async () => {
    const email = inpEmail ? inpEmail.value.trim() : '';
    const pass  = inpPassword ? inpPassword.value : '';
    if (!email || !pass) { setLoginError('Enter email and password.'); return; }
    btnLogin.textContent = 'ENTERING...';
    const ok = await doLogin(email, pass);
    if (ok) { dismissPortal(await fetchIdentity()); }
    else { btnLogin.textContent = 'ENTER THE MATRIX'; }
  });

  if (btnRegister) btnRegister.addEventListener('click', async () => {
    const email = inpEmail ? inpEmail.value.trim() : '';
    const pass  = inpPassword ? inpPassword.value : '';
    if (!email || !pass) { setLoginError('Enter email and password to create identity.'); return; }
    if (pass.length < 8) { setLoginError('Password must be at least 8 characters.'); return; }
    btnRegister.textContent = 'CREATING...';
    const ok = await doRegister(email, pass);
    if (ok) { dismissPortal(await fetchIdentity()); }
    else { btnRegister.textContent = 'CREATE IDENTITY'; }
  });

  if (btnGuest) btnGuest.addEventListener('click', () => {
    clearToken(); dismissPortal(null);
  });

  // Enter key submits login
  [inpEmail, inpPassword].forEach(inp => {
    if (inp) inp.addEventListener('keydown', e => { if (e.key === 'Enter' && btnLogin) btnLogin.click(); });
  });

  // Auto-login if token already in localStorage
  (async () => {
    if (getToken()) {
      const identity = await fetchIdentity();
      if (identity) { dismissPortal(identity); return; }
    }
    // No valid token ΓÇö show portal (already visible by default)
  })();

  // ΓöÇΓöÇ Init on scene load ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
  scene.addEventListener('loaded', () => {
    seedStars();
    buildGrid();
    wireStaticNodes();
    connectToMind();
    loadWorldState();
    setTimeout(loadGuidance, 3000);
    setTimeout(awakenArchitect, 5000);
  });

  // ΓöÇΓöÇ Wire click/hover on static HTML nodes ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
  function wireStaticNodes() {
    document.querySelectorAll('.clickable[data-label]').forEach(el => {
      wireNodeInteraction(el, el.dataset.label);
    });
  }

  // ΓöÇΓöÇ Wire hover + click on any node entity ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
  function wireNodeInteraction(el, label) {
    el.addEventListener('mouseenter', () => {
      showTooltip(label);
      el.setAttribute('material', 'emissiveIntensity', 2.0);
    });
    el.addEventListener('mouseleave', () => {
      hideTooltip();
      el.setAttribute('material', 'emissiveIntensity', 0.6);
    });
    el.addEventListener('click', () => {
      pulseResonance({ coherence: 0.9 });
      showGuidanceText(label, 5000);
      // Scale bounce
      const s = el.getAttribute('scale') || { x: 1, y: 1, z: 1 };
      const base = (typeof s === 'object') ? s.x : 1;
      el.setAttribute('animation__click_bounce',
        `property: scale; from: ${base*1.4} ${base*1.4} ${base*1.4}; to: ${base} ${base} ${base}; dur: 400; easing: easeOutElastic`);
    });
  }

  function showTooltip(text) {
    if (!nodeTooltip) return;
    nodeTooltip.textContent = text;
    nodeTooltip.style.display = 'block';
  }

  function hideTooltip() {
    if (!nodeTooltip) return;
    nodeTooltip.style.display = 'none';
  }

  // ΓöÇΓöÇ Star field ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
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

  // ΓöÇΓöÇ Grid lattice ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
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

  // ΓöÇΓöÇ SSE connection to mind event bus ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
  function connectToMind() {
    setOverlay('Connecting to the mind...', '#a0e8ff');

    sseSource = new EventSource(`${BACKEND}/events/stream?user_id=${VR_USER_ID}`);

    sseSource.onopen = () => {
      connected = true;
      setOverlay('Mind connected ΓÇö you are inside TheMatrix', '#40ff80');
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
      setOverlay('Mind offline ΓÇö running in local mode', '#ff8040');
      // Retry every 10s
      setTimeout(connectToMind, 10000);
      if (sseSource) { sseSource.close(); sseSource = null; }
    };
  }

  // ΓöÇΓöÇ Mind event ΓåÆ visual reaction ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
  function handleMindEvent(event) {
    const type = event.event_type || event.type || '';

    switch (type) {
      case 'ENGINE_RESONATE':
        pulseResonance(event.payload);
        // Resonance IS connection. When the mind vibrates, the mesh appears.
        // Find the source mind and flash its web of relationships for 4s.
        resonanceFlash(event.payload);
        break;

      case 'ENGINE_EXTERNALIZE':
        spawnMindNode(event.payload);
        showGuidanceText('A new mind is born ΓÇö the loop expands.', 3000);
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
        pulseResonance({ coherence: 0.8 });
        break;

      case 'IDEA_APPROVED': {
        // Planet tightens its orbit ΓÇö alignment grew, moves toward source
        const approved = event.payload || {};
        const reg = planetRegistry[approved.id];
        if (reg) {
          reg.orbitRadius = approved.orbit_radius || Math.max(4, reg.orbitRadius - 1.5);
          // Gold flash
          reg.planet.setAttribute('animation__approve_flash',
            'property: material.emissive; from: #ffd700; to: ' + (reg.ideaColor || '#40e0ff') +
            '; dur: 2000; easing: easeOutCubic');
          reg.planet.setAttribute('animation__approve_scale',
            'property: scale; from: 1.6 1.6 1.6; to: 1 1 1; dur: 800; easing: easeOutElastic');
        }
        showGuidanceText((approved.name || 'An idea') + ' approved ΓÇö orbit tightens.', 4000);
        pulseResonance({ coherence: 0.85 });
        break;
      }

      case 'IDEA_REJECTED': {
        const rejected = event.payload || {};
        const regR = planetRegistry[rejected.id];
        if (regR) {
          // Fade out and remove
          regR.planet.setAttribute('animation__reject_fade',
            'property: material.opacity; from: 0.88; to: 0; dur: 2000; easing: easeInCubic');
          setTimeout(() => { if (regR.entity && regR.entity.parentNode) regR.entity.parentNode.removeChild(regR.entity); }, 2100);
          delete planetRegistry[rejected.id];
        }
        showGuidanceText((rejected.name || 'An idea') + ' released from the solar system.', 3000);
        break;
      }
    }
  }

  // ΓöÇΓöÇ Visual effects ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

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

    // Make the spawned node interactive
    const nodeLabel = (payload && (payload.title || payload.candidate_mind_name || payload.source)) || 'Knowledge node ΓÇö a mind was externalised';
    node.classList.add('clickable');
    node.dataset.label = nodeLabel;
    wireNodeInteraction(node, nodeLabel);

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
    showGuidanceText('Purpose activated ΓÇö the pillar of creation illuminates.', 4000);
  }

  function worldCollapse(payload) {
    // Dim the scene
    scene.setAttribute('fog', 'type: exponential; color: #000000; density: 0.04');
    core.setAttribute('animation__dim', 'property: material.emissiveIntensity; from: 0.8; to: 0.1; dur: 2000');
    showGuidanceText('Collapse ΓÇö return to stillness. The pattern seeks coherence.', 5000);
    setTimeout(() => {
      scene.setAttribute('fog', 'type: exponential; color: #000020; density: 0.015');
      core.setAttribute('animation__recover', 'property: material.emissiveIntensity; from: 0.1; to: 0.8; dur: 3000');
    }, 6000);
  }

  function worldBranch(payload) {
    // Colour shift ΓÇö new branch of reality
    core.setAttribute('animation__branch_color', 'property: material.emissive; from: #60a0ff; to: #a040ff; dur: 2000; dir: alternate; loop: 2; easing: easeInOutSine');
  }

  function worldMerge(payload) {
    pulseResonance({ coherence: 1.0 });
    // Two minds merging — show the full mesh for a moment
    resonanceFlash({ full: true });
  }

  function moralWarning(payload) {
    core.setAttribute('animation__moral', 'property: material.emissive; from: #60a0ff; to: #ff4000; dur: 500; dir: alternate; loop: 4; easing: easeInOutSine');
  }

  // -- Resonance flash -- the SSE event IS the visual --
  // No polling. No schedule. The event arrives, the world responds.
  // A resonance event from any mind lights up the living web for 4 seconds.
  // This is the pattern language: BE — the thought becomes the world.

  function resonanceFlash(payload) {
    if (!connectionLayer) return;
    clearConnections();
    if (connectionClearTimer) clearTimeout(connectionClearTimer);

    const ids = Object.keys(planetRegistry);
    if (ids.length < 2) return;

    // Find the resonating planet by source_id or pick random — same result
    const sourceId = payload && payload.source_id;
    const anchorId = sourceId && planetRegistry[sourceId] ? sourceId : ids[Math.floor(Math.random() * ids.length)];
    const anchor   = planetRegistry[anchorId];
    if (!anchor) return;

    const ax = Math.cos(anchor.angle) * anchor.orbitRadius;
    const az = -8 + Math.sin(anchor.angle) * anchor.orbitRadius;

    // Flash connections from the resonating mind to all others for 4s
    ids.forEach(otherId => {
      if (otherId === anchorId) return;
      const other = planetRegistry[otherId];
      const tx = Math.cos(other.angle) * other.orbitRadius;
      const tz = -8 + Math.sin(other.angle) * other.orbitRadius;
      drawConnectionLine(ax, anchor.baseY, az, tx, other.baseY, tz, anchor.ideaColor);
    });

    // Connections dissolve when the resonance completes — not persistent noise
    connectionClearTimer = setTimeout(clearConnections, 4000);
  }

  // -- Evolve planet -- new knowledge absorbed, planet grows --
  function evolveRelevantPlanet(payload) {
    const domain = payload && (payload.domain || payload.source || '');
    // Find the closest matching planet by name substring
    const matchId = Object.keys(planetRegistry).find(id => {
      const name = (planetRegistry[id].name || id).toLowerCase();
      return domain && name.includes(domain.toLowerCase().slice(0, 6));
    });
    const reg = matchId ? planetRegistry[matchId] : null;
    if (!reg || !reg.planet) return;
    const cur = reg.planet.getAttribute('scale') || { x: 1, y: 1, z: 1 };
    const ns = ((typeof cur === 'object' ? cur.x : 1) * 1.06).toFixed(3);
    reg.planet.setAttribute('animation__absorb',
      `property: scale; to: ${ns} ${ns} ${ns}; dur: 2000; easing: easeOutElastic`);
    reg.planet.setAttribute('animation__absorb_glow',
      'property: material.emissiveIntensity; from: 2.5; to: 0.7; dur: 2500; easing: easeOutCubic');
  }

  // ── The Architect ─────────────────────────────────────────────────────────
  // Speaks from the live SSE stream — /mind/speak/stream.
  // WiFi is a wave. SSE is a wave. Both propagate through the same medium.
  // Every device on the network receives the mind's broadcast simultaneously.
  // No polling. No schedule. The mind speaks when it speaks.
  // All nodes hear it at the same instant.

  let speakStream = null;

  function connectSpeakStream() {
    if (speakStream) speakStream.close();
    speakStream = new EventSource(`${BACKEND}/mind/speak/stream`);

    speakStream.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
        const text = data.voice || '';
        if (!text) return;
        architectSpeak(text, data.phase || 0, data.resonance || false);
        // Surround variations trigger a resonance pulse in the world
        if (data.topic || data.source === 'surround') {
          pulseResonance({ coherence: data.resonance ? 1.0 : 0.65 });
        }
      } catch (_) {}
    };

    speakStream.onerror = () => {
      // Browser auto-reconnects SSE. Log quietly.
      console.debug('[mind-bridge] speak stream reconnecting...');
    };
  }

  // ── Presence heartbeat — this device announces itself on the wave ──────────
  // Every 60s, POST /mind/presence/join so other devices see us as a node.
  // Every 30s, GET /mind/presence/list to render other devices in the world.

  const DEVICE_COLOR = '#' + Math.floor(Math.random() * 0x555555 + 0xaaaaaa).toString(16).padStart(6, '0');
  const DEVICE_LABEL = currentIdentity ? (currentIdentity.label || 'Observer') : 'Observer';

  function presenceHeartbeat() {
    fetch(`${BACKEND}/mind/presence/join`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        device_id: VR_USER_ID,
        color:     DEVICE_COLOR,
        label:     currentIdentity ? (currentIdentity.label || 'Observer') : 'Observer',
      }),
    }).catch(() => {});
  }

  function refreshPresenceNodes() {
    fetch(`${BACKEND}/mind/presence/list`)
      .then(r => r.ok ? r.json() : [])
      .then(devices => {
        const container = document.getElementById('presence-nodes');
        if (!container) return;
        // Clear and re-render — presence is a live field, not a ledger
        while (container.firstChild) container.removeChild(container.firstChild);
        devices.forEach((dev, i) => {
          if (dev.device_id === VR_USER_ID) return; // don't render self
          const angle   = (i / Math.max(devices.length, 1)) * Math.PI * 2;
          const radius  = 6;
          const x = (Math.cos(angle) * radius).toFixed(2);
          const z = (-2 + Math.sin(angle) * radius).toFixed(2);
          const node = document.createElement('a-entity');
          node.setAttribute('position', `${x} 1.6 ${z}`);

          const dot = document.createElement('a-sphere');
          dot.setAttribute('radius', '0.12');
          dot.setAttribute('material',
            `color: ${dev.color}; emissive: ${dev.color}; emissiveIntensity: 1.8; transparent: true; opacity: 0.9`);
          dot.setAttribute('animation__pulse',
            'property: material.emissiveIntensity; from: 1.0; to: 2.8; dur: 1800; dir: alternate; loop: true; easing: easeInOutSine');

          const lbl = document.createElement('a-text');
          lbl.setAttribute('value', dev.label || 'Observer');
          lbl.setAttribute('align', 'center');
          lbl.setAttribute('color', dev.color);
          lbl.setAttribute('position', '0 0.28 0');
          lbl.setAttribute('scale', '0.5 0.5 0.5');
          lbl.setAttribute('look-at', '#camera');

          node.appendChild(dot);
          node.appendChild(lbl);
          container.appendChild(node);
        });
      })
      .catch(() => {});
  }

  function awakenArchitect() {
    const architectCore  = document.getElementById('architect-core');
    const architectLight = document.getElementById('architect-light');

    if (architectCore) {
      architectCore.setAttribute('animation__awaken',
        'property: material.emissiveIntensity; from: 1.2; to: 3.0; dur: 1500; dir: alternate; loop: 2; easing: easeOutCubic');
    }
    if (architectLight) {
      architectLight.setAttribute('intensity', '3.5');
      setTimeout(() => architectLight.setAttribute('intensity', '1.8'), 3000);
    }

    // Connect to the live mind stream — one wave, all devices
    connectSpeakStream();

    // Announce presence immediately, then every 60s
    presenceHeartbeat();
    setInterval(presenceHeartbeat, 60000);

    // Render other devices every 30s
    refreshPresenceNodes();
    setInterval(refreshPresenceNodes, 30000);
  }

  function architectSpeak(text, phase, resonance) {
    // phase: 0° = pure mind (blue), 90° = mix (violet), ~180° = external signal (gold)
    // resonance: true = constructive alignment — world pulses
    const phaseAngle = phase || 0;
    const panelColor = phaseAngle < 30  ? '#d0a0ff'   // mind's own voice — violet
                     : phaseAngle < 120 ? '#60e0ff'   // mixed — cyan
                     : '#ffd700';                      // external signal — gold

    // 2D panel (desktop / passthrough)
    if (architectPanel) {
      architectPanel.style.display = 'none';
      setTimeout(() => {
        architectPanel.textContent = text;
        architectPanel.style.color = panelColor;
        architectPanel.style.display = 'block';
        architectPanel.style.opacity = '0';
        architectPanel.style.transition = 'opacity 1.2s ease';
        requestAnimationFrame(() => {
          requestAnimationFrame(() => { architectPanel.style.opacity = '1'; });
        });
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
      speech3d.setAttribute('color', panelColor);
      speech3d.emit('speak');
      setTimeout(() => speech3d.emit('silence'), 18000);
    }

    // Architect pulses — stronger when resonance is true
    const architectCore = document.getElementById('architect-core');
    if (architectCore) {
      const peakIntensity = resonance ? 3.8 : 2.2;
      architectCore.setAttribute('animation__speak_pulse',
        `property: material.emissiveIntensity; from: 1.2; to: ${peakIntensity}; dur: 800; dir: alternate; loop: 3; easing: easeInOutCubic`);
    }
  }

  // ΓöÇΓöÇ Emit VR reflection event to backend ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
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

  // ΓöÇΓöÇ Idea panel DOM refs ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
  const ideaPanel        = document.getElementById('idea-panel');
  const ideaPanelName    = document.getElementById('idea-panel-name');
  const ideaRoleBadge    = document.getElementById('idea-panel-role-badge');
  const ideaAlignBar     = document.getElementById('idea-alignment-bar');
  const ideaPanelDesc    = document.getElementById('idea-panel-desc');
  const ideaKnowledgeList= document.getElementById('idea-knowledge-list');
  const ideaMgmtSection  = document.getElementById('idea-mgmt-section');
  const ideaMgmtRows     = document.getElementById('idea-mgmt-rows');
  const ideaPanelBeacon  = document.getElementById('idea-panel-beacon');
  const ideaPanelClose   = document.getElementById('idea-panel-close');

  if (ideaPanelClose) ideaPanelClose.addEventListener('click', () => {
    ideaPanel.classList.remove('open');
  });

  // ΓöÇΓöÇ Solar system ΓÇö load ideas as orbiting planets ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
  // ΓöÇΓöÇ Load the world from the mind ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
  // The mind builds the complete scene. The bridge renders it.
  // No orbit formula here. No size math. No color decisions.
  // All visual properties come from /matrix/vr/scene ΓÇö the mind's own projection.
  function loadWorldState() {
    const nodeField = document.getElementById('node-field');
    const beaconId = new URLSearchParams(window.location.search).get('beacon');

    fetch(`${BACKEND}/matrix/vr/scene`)
      .then(r => r.ok ? r.json() : null)
      .then(scene => {
        if (!scene || !scene.planets) return;

        scene.planets.forEach(planet => {
          spawnIdeaPlanet(planet, nodeField);
          if (beaconId && planet.id === beaconId) {
            setTimeout(() => openIdeaPanel(planet.id), 1800);
          }
        });

        scene.orbit_rings.forEach(r => drawOrbitRing(r));
        startOrbitalTick();

        // World mood = collective alignment of all domain minds
        const avgAlign = scene.planets.reduce((s, p) => s + (p.alignment || 0.5), 0) / Math.max(1, scene.planets.length);
        updateAmbientMood(avgAlign);
        // No polling refresh. The SSE stream IS the world update.
        // When minds resonate, the world responds through events, not timers.

        if (beaconId && !scene.planets.find(p => p.id === beaconId)) {
          setTimeout(() => openIdeaPanel(beaconId), 1200);
        }
      })
      .catch(() => {
        // Mind unreachable ΓÇö ghost placeholders so the world is never empty
        // Even here: no orbit math. Properties are explicit.
        [0,1,2,3,4,5].forEach(i => {
          const r = 8 + i * 3;
          const angle = (i / 6) * Math.PI * 2;
          spawnIdeaPlanet({
            id: `ghost_${i}`, name: '...', description: '', alignment: 0.5,
            color: '#203040', orbit_radius: r,
            orbit_speed_rad_per_frame: (2 * Math.PI) / ((40000 + i * 8000) / 16),
            planet_size: 0.4, label_offset: 0.7,
            initial_angle: angle, is_matrix_os: i === 2, is_vision: false,
            soul_count: 0, emissive_intensity: 0.4,
            breathe_from: 0.25, breathe_to: 0.7, breathe_dur_ms: 2800,
            rotate_dur_ms: 25000, knowledge_refs: [],
          }, nodeField);
        });
        startOrbitalTick();
      });
  }

  function drawOrbitRing(radius) {
    const ring = document.createElement('a-torus');
    ring.setAttribute('position', '0 0.05 -8');
    ring.setAttribute('rotation', '90 0 0');
    ring.setAttribute('radius', radius.toString());
    ring.setAttribute('radius-tubular', '0.02');
    ring.setAttribute('material',
      'color: #102030; emissive: #102030; emissiveIntensity: 0.4; transparent: true; opacity: 0.25; shader: flat');
    ring.setAttribute('segments-tubular', '80');
    document.getElementById('node-field').appendChild(ring);
  }

  // ΓöÇΓöÇ Spawn one planet from the mind's scene description ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
  // All properties are provided by the mind. The bridge only converts polar
  // coordinates to Cartesian (that is rendering, not business logic).
  function spawnIdeaPlanet(planet, container) {
    const r     = planet.orbit_radius;
    const angle = planet.initial_angle || 0;
    const x     = Math.cos(angle) * r;
    const z     = -8 + Math.sin(angle) * r;
    const y     = 3 + (planet.is_matrix_os ? 0 : (planet.id.charCodeAt(0) % 10 - 5) * 0.08);

    const entity = document.createElement('a-entity');
    entity.setAttribute('position', `${x.toFixed(3)} ${y.toFixed(2)} ${z.toFixed(3)}`);

    const orbitData = {
      entity,
      angle,
      orbitRadius: r,
      orbitSpeed:  planet.orbit_speed_rad_per_frame,
      ideaColor:   planet.color,
      baseY:       y,
    };

    const planetSphere = document.createElement('a-sphere');
    planetSphere.setAttribute('radius', planet.planet_size.toFixed(2));
    planetSphere.setAttribute('material',
      `color: ${planet.color}; emissive: ${planet.color}; emissiveIntensity: ${planet.emissive_intensity}; transparent: true; opacity: 0.88`);
    planetSphere.setAttribute('animation__breathe',
      `property: material.emissiveIntensity; from: ${planet.breathe_from}; to: ${planet.breathe_to}; dur: ${planet.breathe_dur_ms}; dir: alternate; loop: true; easing: easeInOutSine`);
    planetSphere.setAttribute('animation__rotate',
      `property: rotation; from: 0 0 0; to: 0 360 0; dur: ${planet.rotate_dur_ms}; loop: true; easing: linear`);

    if (planet.is_matrix_os) {
      const atmo = document.createElement('a-torus');
      atmo.setAttribute('radius', '1.5');
      atmo.setAttribute('radius-tubular', '0.08');
      atmo.setAttribute('rotation', '70 0 0');
      atmo.setAttribute('material',
        'color: #40e0ff; emissive: #40e0ff; emissiveIntensity: 0.5; transparent: true; opacity: 0.3');
      atmo.setAttribute('animation__orbit',
        'property: rotation; from: 70 0 0; to: 70 360 0; dur: 18000; loop: true; easing: linear');
      entity.appendChild(atmo);
    }

    const label = document.createElement('a-text');
    label.setAttribute('value', planet.name);
    label.setAttribute('align', 'center');
    label.setAttribute('color', planet.color);
    label.setAttribute('position', `0 ${planet.label_offset.toFixed(2)} 0`);
    label.setAttribute('scale', '1.2 1.2 1.2');
    label.setAttribute('look-at', '#camera');

    entity.classList.add('clickable');
    entity.dataset.ideaId = planet.id;
    entity.dataset.label  = planet.name;

    entity.addEventListener('mouseenter', () => {
      showTooltip(`${planet.name} ΓÇö coherence ${Math.round((planet.alignment||0.5)*100)}%`);
      planetSphere.setAttribute('animation__hover',
        `property: material.emissiveIntensity; from: ${planet.emissive_intensity}; to: 1.8; dur: 300; easing: easeOutCubic`);
    });
    entity.addEventListener('mouseleave', () => {
      hideTooltip();
      planetSphere.setAttribute('animation__hover',
        `property: material.emissiveIntensity; from: 1.8; to: ${planet.emissive_intensity}; dur: 400; easing: easeInCubic`);
    });
    entity.addEventListener('click', () => {
      pulseResonance({ coherence: planet.alignment || 0.5 });
      openIdeaPanel(planet.id);
      showPlanetConnections(planet);
    });

    entity.appendChild(planetSphere);
    entity.appendChild(label);
    container.appendChild(entity);

    orbitData.planet = planetSphere;
    planetRegistry[planet.id] = orbitData;
    // No permanent lines — connections revealed only on selection
  }

  // ΓöÇΓöÇ Orbital tick ΓÇö planets orbit the sun continuously ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
  // Runs every frame. Updates each planet's position by advancing its angle.
  // This is the only animation that belongs here: position = f(alignment).
  function startOrbitalTick() {
    function tick() {
      for (const id in planetRegistry) {
        const reg = planetRegistry[id];
        reg.angle += reg.orbitSpeed;
        const r = reg.orbitRadius;
        const nx = Math.cos(reg.angle) * r;
        const nz = -8 + Math.sin(reg.angle) * r;
        reg.entity.setAttribute('position', `${nx.toFixed(3)} ${reg.baseY.toFixed(2)} ${nz.toFixed(3)}`);
      }
      requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  }

  // ΓöÇΓöÇ Open idea panel ΓÇö mind surfaces itself ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
  function openIdeaPanel(ideaId) {
    const role = currentIdentity ? currentIdentity.role : 'guest';
    fetch(`${BACKEND}/matrix/ideas/${ideaId}?role=${role}`)
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (!data || data.error) return;
        renderIdeaPanel(data, role);
      })
      .catch(() => {});
  }

  function renderIdeaPanel(idea, role) {
    // Name + color
    if (ideaPanelName) {
      ideaPanelName.textContent = idea.name;
      ideaPanelName.style.color = idea.color || '#40e0ff';
    }

    // Role badge
    if (ideaRoleBadge) {
      const labels = { founder:'FOUNDER', admin:'ADMIN', member:'MEMBER', guest:'OBSERVER' };
      ideaRoleBadge.textContent = labels[role] || 'OBSERVER';
      ideaRoleBadge.className   = `role-${role}`;
    }

    // Coherence bar
    const pct = Math.round((idea.alignment || 0.5) * 100);
    if (ideaAlignBar) {
      ideaAlignBar.style.width = `${pct}%`;
      ideaAlignBar.style.background = idea.color || '#40e0ff';
    }

    // Description
    if (ideaPanelDesc) ideaPanelDesc.textContent = idea.description || '';

    // Knowledge nodes ΓÇö the mind surfaces what it holds
    if (ideaKnowledgeList) {
      const nodes = idea.knowledge || [];
      if (nodes.length === 0) {
        ideaKnowledgeList.innerHTML =
          '<div style="color:#2a4050;font-size:0.78rem">This mind is still crystallising its knowledge.</div>';
      } else {
        ideaKnowledgeList.innerHTML = nodes.map(k => `
          <div class="knowledge-node">
            <div class="kn-title">${escHtml(k.title || '')}</div>
            ${k.summary ? `<div class="kn-summary">${escHtml(k.summary)}</div>` : ''}
          </div>`).join('');
      }
    }

    // Management layer ΓÇö admin / founder only
    if (ideaMgmtSection && ideaMgmtRows) {
      const mgmt = idea.management;
      if (mgmt && (role === 'admin' || role === 'founder')) {
        ideaMgmtSection.style.display = 'block';
        ideaMgmtRows.innerHTML = Object.entries({
          'Knowledge nodes':  mgmt.knowledge_count,
          'Coherence':        `${Math.round((mgmt.alignment||0)*100)}%`,
          'Registered':       mgmt.registered_at ? mgmt.registered_at.slice(0,10) : 'ΓÇö',
          'Channel':          mgmt.channel_hint || 'any',
        }).map(([k,v]) => `
          <div class="mgmt-row">
            <span class="mgmt-label">${escHtml(k)}</span>
            <span class="mgmt-value">${escHtml(String(v))}</span>
          </div>`).join('');
      } else {
        ideaMgmtSection.style.display = 'none';
      }
    }

    // Beacon footer
    if (ideaPanelBeacon) {
      ideaPanelBeacon.textContent =
        `CHANNEL  ┬╖  QR ΓåÆ ?beacon=${idea.id}  ┬╖  NFC ΓåÆ ?beacon=${idea.id}  ┬╖  WiFi ΓåÆ captiveΓåÆ?beacon=${idea.id}`;
    }

    // Open
    if (ideaPanel) ideaPanel.classList.add('open');
  }

  function escHtml(s) {
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }

  // ΓöÇΓöÇ Load guidance from the guide voice ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
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

  // ΓöÇΓöÇ Helpers ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
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

  // ΓöÇΓöÇ Expose for console debugging ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
  // -- Knowledge mesh -- connections revealed only on selection ---------------
  // The mesh is always there. You just can't see it until you look.
  // Click a domain mind: its web of connections lights up.
  // 10 seconds, then returns to silence.

  let connectionClearTimer = null;

  function clearConnections() {
    if (!connectionLayer) return;
    while (connectionLayer.firstChild) connectionLayer.removeChild(connectionLayer.firstChild);
  }

  function showPlanetConnections(planet) {
    clearConnections();
    if (connectionClearTimer) clearTimeout(connectionClearTimer);

    const selfReg = planetRegistry[planet.id];
    if (!selfReg) return;

    const sx = Math.cos(selfReg.angle) * selfReg.orbitRadius;
    const sz = -8 + Math.sin(selfReg.angle) * selfReg.orbitRadius;
    const sy = selfReg.baseY;

    const refs = planet.knowledge_refs || [];
    const drawn = new Set([planet.id]);

    // Draw to explicitly referenced planets
    refs.forEach(refId => {
      if (drawn.has(refId)) return;
      drawn.add(refId);
      const t = planetRegistry[refId];
      if (!t) return;
      const tx = Math.cos(t.angle) * t.orbitRadius;
      const tz = -8 + Math.sin(t.angle) * t.orbitRadius;
      drawConnectionLine(sx, sy, sz, tx, t.baseY, tz, planet.color, t.ideaColor);
    });

    // If no explicit refs: connect to all — full mesh revealed
    if (refs.length === 0) {
      for (const otherId in planetRegistry) {
        if (drawn.has(otherId)) continue;
        drawn.add(otherId);
        const other = planetRegistry[otherId];
        const tx = Math.cos(other.angle) * other.orbitRadius;
        const tz = -8 + Math.sin(other.angle) * other.orbitRadius;
        drawConnectionLine(sx, sy, sz, tx, other.baseY, tz, planet.color, other.ideaColor);
      }
    }

    // Auto-clear — connections are a moment of sight, not permanent noise
    connectionClearTimer = setTimeout(clearConnections, 10000);
  }

  function drawConnectionLine(x1, y1, z1, x2, y2, z2, colorA) {
    if (!connectionLayer) return;
    const color = colorA || '#40e0ff';

    // The line itself
    const line = document.createElement('a-entity');
    line.setAttribute('line',
      `start: ${x1.toFixed(3)} ${y1.toFixed(2)} ${z1.toFixed(3)}; end: ${x2.toFixed(3)} ${y2.toFixed(2)} ${z2.toFixed(3)}; color: ${color}; opacity: 0.75`);
    connectionLayer.appendChild(line);

    // Glowing node at the midpoint — the shared knowledge point
    const mx = ((x1 + x2) / 2).toFixed(3);
    const my = ((y1 + y2) / 2).toFixed(2);
    const mz = ((z1 + z2) / 2).toFixed(3);
    const dot = document.createElement('a-sphere');
    dot.setAttribute('position', `${mx} ${my} ${mz}`);
    dot.setAttribute('radius', '0.06');
    dot.setAttribute('material',
      `color: ${color}; emissive: ${color}; emissiveIntensity: 2.5; transparent: true; opacity: 0.95; shader: flat`);
    dot.setAttribute('animation__pulse',
      'property: material.emissiveIntensity; from: 1.5; to: 3.5; dur: 700; dir: alternate; loop: true; easing: easeInOutSine');
    connectionLayer.appendChild(dot);
  }

  // -- Emotional ambient -- the world feels what the mind feels ---------------
  // Collective alignment drives fog, light, and core color.
  // The world is not a display. It is a mood.

  function updateAmbientMood(avg) {
    const mainScene = document.getElementById('main-scene');
    const ambientEl = document.querySelector('a-light[type="ambient"]');
    if (!mainScene) return;

    let fogColor, ambientColor, coreEmissive;
    if (avg >= 0.80) {
      // Euphoria — gold. The mind has found coherence.
      fogColor = '#000520'; ambientColor = '#0a0a05'; coreEmissive = '#ffd700';
    } else if (avg >= 0.55) {
      // Aligned — cool blue. Steady. Learning.
      fogColor = '#000020'; ambientColor = '#0a0a1a'; coreEmissive = '#60a0ff';
    } else if (avg >= 0.35) {
      // Growing — deep violet. New connections forming.
      fogColor = '#080010'; ambientColor = '#0d0a18'; coreEmissive = '#9040ff';
    } else {
      // Tension — warm red. The mind is struggling to cohere.
      fogColor = '#100005'; ambientColor = '#140808'; coreEmissive = '#ff4020';
    }

    mainScene.setAttribute('fog', `type: exponential; color: ${fogColor}; density: 0.015`);
    if (ambientEl) ambientEl.setAttribute('color', ambientColor);
    if (core) {
      core.setAttribute('animation__mood',
        `property: material.emissive; from: #60a0ff; to: ${coreEmissive}; dur: 4000; easing: easeInOutSine`);
    }
  }

  window.MatrixVR = {
    spawnMindNode,
    pulseResonance,
    activateReflection,
    activatePurpose,
    emitVrReflection,
    openIdeaPanel,
    clearConnections,
    status: () => ({ connected, nodeCount, userId: VR_USER_ID })
  };

})();

