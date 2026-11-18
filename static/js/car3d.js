/**
 * BIG-L AUTOS - High-Performance Interactive 3D Mercedes-Benz Studio
 * 
 * Features:
 * - Full 360° Orbital Free Rotation with Silky Momentum & Inertia Damping
 * - Dynamic Scroll-to-Zoom & Touch Pinch-to-Zoom (70% - 155% Scale Range)
 * - Quick Camera Angle Presets (Hero 3/4, Side Profile, Low Stance, Top Aerial)
 * - Showroom Auto-Turntable 360° Spin with Smart Interactive Pause
 * - Directional 3D Occlusion (Headlights & Star Glint fade naturally when car turns away)
 * - Sinusoidal 360° Dynamic Floor Contact Shadow
 * - Three.js Ambient Particle Field & Camera Depth Synchronization
 * - Keyboard Shortcuts (Space for Turntable, R for Reset, +/- for Zoom, 1-4 for Presets)
 * - Multi-Model Switching (S63 AMG, C63 AMG, AMG GT Coupe)
 */

(function () {
  'use strict';

  // Mercedes-Benz Model Configurations
  const BENZ_MODELS = {
    s63: {
      name: 'Mercedes-Benz S63 AMG V8 Biturbo',
      src: '/static/uploads/benz_1908.png',
      flareLeft: { left: '11.6%', top: '48.8%', size: '50px' },
      flareRight: { left: '57.1%', top: '51.8%', size: '50px' },
      starGlint: { left: '31.0%', top: '21.3%', size: '24px' },
      hint: 'MERCEDES-BENZ S63 AMG • 360° ORBIT • SCROLL TO ZOOM'
    },
    c63: {
      name: 'Mercedes-Benz C63 AMG',
      src: '/static/uploads/benz_1870.png',
      flareLeft: { left: '5.5%', top: '51.5%', size: '46px' },
      flareRight: { left: '39.0%', top: '54.5%', size: '46px' },
      starGlint: { left: '16.5%', top: '54.0%', size: '28px' },
      hint: 'MERCEDES-BENZ C63 AMG • 360° ORBIT • SCROLL TO ZOOM'
    },
    amg_gt: {
      name: 'Mercedes-AMG GT R Coupe',
      src: '/static/uploads/benz_1902.png',
      flareLeft: { left: '12.0%', top: '53.0%', size: '48px' },
      flareRight: { left: '52.0%', top: '56.0%', size: '48px' },
      starGlint: { left: '28.0%', top: '53.5%', size: '26px' },
      hint: 'MERCEDES-AMG GT R • 360° ORBIT • SCROLL TO ZOOM'
    }
  };

  // Quick Camera Presets
  const PRESET_ANGLES = {
    hero: { rotX: 4, rotY: 20, zoom: 1.0, name: 'Hero 3/4' },
    profile: { rotX: 0, rotY: 86, zoom: 1.05, name: 'Side Profile' },
    low: { rotX: -12, rotY: 8, zoom: 1.20, name: 'Low Stance' },
    top: { rotX: 24, rotY: 34, zoom: 0.92, name: 'Top Aerial' }
  };

  const MIN_ZOOM = 0.70;
  const MAX_ZOOM = 1.55;

  let currentModelKey = 's63';
  let activePresetKey = 'hero';

  // DOM Elements
  let container = null;
  let stage = null;
  let bodyWrap = null;
  let carImg = null;
  let sheen = null;
  let floorShadow = null;
  let flareLeft = null;
  let flareRight = null;
  let starGlint = null;
  let hint = null;
  let hintText = null;
  let canvas = null;
  let btnTurntable = null;
  let zoomLevelBadge = null;

  // 3D Motion Physics State
  let targetRotX = 4;
  let targetRotY = 20;
  let targetRotZ = 0;
  let targetTransX = 0;
  let targetTransY = 0;
  let targetTransZ = 0;
  let targetZoom = 1.0;

  let currentRotX = 4;
  let currentRotY = 20;
  let currentRotZ = 0;
  let currentTransX = 0;
  let currentTransY = 0;
  let currentTransZ = 0;
  let currentZoom = 1.0;

  // Interactive Turntable & Control State
  let isTurntableActive = false;
  let turntableSpeed = 0.35;
  let isHovered = false;
  let isDragging = false;
  let dragStartX = 0;
  let dragStartY = 0;
  let dragInitialRotY = 20;
  let dragInitialRotX = 4;
  let dragRotY = 20;
  let dragRotX = 4;
  let dragVelocityY = 0;
  let lastDragX = 0;
  let lastDragTime = 0;
  let lastInteractionTime = performance.now();

  // Touch Pinch Zoom State
  let initialPinchDist = 0;
  let initialPinchZoom = 1.0;

  let mouseNormX = 0;
  let mouseNormY = 0;
  let mouseRelX = 50;
  let mouseRelY = 50;

  // Three.js State
  let scene = null;
  let camera = null;
  let renderer = null;
  let threeSpotLight = null;
  let particlesMesh = null;
  let animFrameId = null;

  function init() {
    container = document.getElementById('car3DContainer');
    stage = document.getElementById('car3DStage');
    bodyWrap = document.getElementById('car3DBodyWrap');
    carImg = document.getElementById('car3DRealImg');
    sheen = document.getElementById('car3DSheen');
    floorShadow = document.getElementById('car3DShadow');
    flareLeft = document.getElementById('flareLeft');
    flareRight = document.getElementById('flareRight');
    starGlint = document.getElementById('starGlint');
    hint = document.getElementById('car3DHint');
    hintText = document.getElementById('hintText');
    canvas = document.getElementById('car3DCanvas');
    btnTurntable = document.getElementById('btnTurntable');
    zoomLevelBadge = document.getElementById('zoomLevelBadge');

    if (!container || !bodyWrap || !carImg) return;

    // Apply initial model coordinates
    applyModelConfig(currentModelKey, false);

    // Initialize Three.js Ambient Particle & Light Field
    initThreeScene();

    // Event Listeners for Mouse, Touch, Drag, Wheel, Pinch & Keyboard
    bindEvents();

    // Start 60fps/120fps Animation Loop
    startAnimationLoop();
  }

  function applyModelConfig(key, animate = true) {
    const config = BENZ_MODELS[key];
    if (!config) return;
    currentModelKey = key;

    if (animate) {
      if (carImg) carImg.style.opacity = '0.1';
      if (sheen) sheen.style.opacity = '0';
      if (flareLeft) flareLeft.style.opacity = '0';
      if (flareRight) flareRight.style.opacity = '0';
      if (starGlint) starGlint.style.opacity = '0';

      setTimeout(() => {
        carImg.src = config.src;
        carImg.alt = config.name;
        updateFlarePositions(config);
        if (hintText) hintText.textContent = config.hint;

        carImg.onload = () => {
          carImg.style.opacity = '1';
          if (flareLeft) flareLeft.style.opacity = '0.85';
          if (flareRight) flareRight.style.opacity = '0.85';
          if (starGlint) starGlint.style.opacity = '0.65';
        };
      }, 180);
    } else {
      carImg.src = config.src;
      carImg.alt = config.name;
      updateFlarePositions(config);
      if (hintText) hintText.textContent = config.hint;
    }
  }

  function updateFlarePositions(config) {
    if (flareLeft) {
      flareLeft.style.left = config.flareLeft.left;
      flareLeft.style.top = config.flareLeft.top;
      flareLeft.style.width = config.flareLeft.size;
      flareLeft.style.height = config.flareLeft.size;
    }
    if (flareRight) {
      flareRight.style.left = config.flareRight.left;
      flareRight.style.top = config.flareRight.top;
      flareRight.style.width = config.flareRight.size;
      flareRight.style.height = config.flareRight.size;
    }
    if (starGlint) {
      starGlint.style.left = config.starGlint.left;
      starGlint.style.top = config.starGlint.top;
      starGlint.style.width = config.starGlint.size;
      starGlint.style.height = config.starGlint.size;
    }
  }

  // Model Switcher exposed to window
  window.switchBenzModel = function (key, btnEl) {
    if (key === currentModelKey) return;
    document.querySelectorAll('.model-pill').forEach(btn => btn.classList.remove('active'));
    if (btnEl) btnEl.classList.add('active');
    applyModelConfig(key, true);
    lastInteractionTime = performance.now();
  };

  // Camera Presets exposed to window
  window.setCarCameraPreset = function (presetKey, btnEl) {
    const preset = PRESET_ANGLES[presetKey];
    if (!preset) return;

    activePresetKey = presetKey;
    document.querySelectorAll('.preset-pill').forEach(btn => btn.classList.remove('active'));
    if (btnEl) {
      btnEl.classList.add('active');
    } else {
      const match = document.querySelector(`.preset-pill[data-preset="${presetKey}"]`);
      if (match) match.classList.add('active');
    }

    dragRotY = preset.rotY;
    dragRotX = preset.rotX;
    targetRotY = preset.rotY;
    targetRotX = preset.rotX;
    targetZoom = preset.zoom;
    dragVelocityY = 0;
    lastInteractionTime = performance.now();

    if (hintText) {
      hintText.textContent = `CAMERA: ${preset.name.toUpperCase()} • DRAG TO ORBIT 360°`;
    }
  };

  // Turntable Auto-Spin Toggle
  window.toggleTurntable = function () {
    isTurntableActive = !isTurntableActive;
    if (btnTurntable) {
      if (isTurntableActive) {
        btnTurntable.classList.add('active');
      } else {
        btnTurntable.classList.remove('active');
      }
    }
    lastInteractionTime = performance.now();

    if (hintText) {
      hintText.textContent = isTurntableActive
        ? 'TURNTABLE ACTIVE • 360° SHOWROOM AUTO-SPIN'
        : 'TURNTABLE PAUSED • DRAG 360° OR SCROLL TO ZOOM';
    }
  };

  // Zoom Controls (+ / -)
  window.zoomCar = function (delta) {
    targetZoom = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, targetZoom + delta));
    lastInteractionTime = performance.now();
    clearActivePreset();
  };

  // Reset View (↺)
  window.resetCarView = function () {
    window.setCarCameraPreset('hero');
    targetTransX = 0;
    targetTransY = 0;
    targetTransZ = 0;
    dragVelocityY = 0;
    if (isTurntableActive) {
      window.toggleTurntable();
    }
  };

  function clearActivePreset() {
    activePresetKey = null;
    document.querySelectorAll('.preset-pill').forEach(btn => btn.classList.remove('active'));
  }

  // Three.js Ambient Showroom Particle Canvas
  function initThreeScene() {
    if (!canvas || typeof THREE === 'undefined') return;

    try {
      scene = new THREE.Scene();

      camera = new THREE.PerspectiveCamera(
        42,
        container.clientWidth / container.clientHeight,
        0.1,
        100
      );
      camera.position.set(0, 0, 10);

      renderer = new THREE.WebGLRenderer({
        canvas: canvas,
        alpha: true,
        antialias: true,
        powerPreference: 'high-performance'
      });
      renderer.setSize(container.clientWidth, container.clientHeight);
      renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
      renderer.setClearColor(0x000000, 0);

      // Showroom Ambient & Directional Lights
      const ambientLight = new THREE.AmbientLight(0xd1fae5, 1.2);
      scene.add(ambientLight);

      threeSpotLight = new THREE.SpotLight(0xffffff, 2.8, 30, Math.PI / 4, 0.4, 1);
      threeSpotLight.position.set(0, 4, 8);
      scene.add(threeSpotLight);

      const mintRimLight = new THREE.DirectionalLight(0x10b981, 1.6);
      mintRimLight.position.set(-8, 5, -5);
      scene.add(mintRimLight);

      // Atmospheric floating particles (luxury showroom dust particles)
      const particleCount = 45;
      const geometry = new THREE.BufferGeometry();
      const positions = new Float32Array(particleCount * 3);
      const scales = new Float32Array(particleCount);

      for (let i = 0; i < particleCount; i++) {
        positions[i * 3] = (Math.random() - 0.5) * 14;
        positions[i * 3 + 1] = (Math.random() - 0.5) * 8;
        positions[i * 3 + 2] = (Math.random() - 0.5) * 8;
        scales[i] = Math.random() * 0.08 + 0.04;
      }

      geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
      geometry.setAttribute('scale', new THREE.BufferAttribute(scales, 1));

      const particleMat = new THREE.PointsMaterial({
        color: 0x6ee7b7,
        size: 0.12,
        transparent: true,
        opacity: 0.4,
        blending: THREE.AdditiveBlending
      });

      particlesMesh = new THREE.Points(geometry, particleMat);
      scene.add(particlesMesh);

      window.addEventListener('resize', onWindowResize);
    } catch (e) {
      console.warn('Three.js initialization notice:', e);
    }
  }

  function onWindowResize() {
    if (!renderer || !camera || !container) return;
    camera.aspect = container.clientWidth / container.clientHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(container.clientWidth, container.clientHeight);
  }

  // Pointer, Drag, Wheel, Touch Pinch, and Keyboard Handlers
  function bindEvents() {
    // 1. Mouse & Pointer Tracking on Container
    function handlePointerMove(e) {
      const rect = container.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;

      mouseNormX = Math.max(-1.5, Math.min(1.5, ((x / rect.width) * 2) - 1));
      mouseNormY = Math.max(-1.5, Math.min(1.5, ((y / rect.height) * 2) - 1));

      mouseRelX = Math.max(0, Math.min(100, (x / rect.width) * 100));
      mouseRelY = Math.max(0, Math.min(100, (y / rect.height) * 100));

      isHovered = (x >= 0 && x <= rect.width && y >= 0 && y <= rect.height);

      if (!isDragging && !isTurntableActive) {
        // Natural 3D response: car angles subtly toward cursor relative to current orbit base
        targetRotY = dragRotY + (mouseNormX * 14);
        targetRotX = dragRotX - (mouseNormY * 9);
        targetRotZ = -(mouseNormX * 3.0);
        targetTransX = mouseNormX * 14;
        targetTransY = mouseNormY * 8;
        targetTransZ = isHovered ? 20 : 0;
      }

      updateSpotlightSheen(mouseRelX, mouseRelY, isHovered);

      if (threeSpotLight) {
        threeSpotLight.position.x = mouseNormX * 6;
        threeSpotLight.position.y = -mouseNormY * 4 + 4;
      }
    }

    container.addEventListener('pointerenter', () => {
      isHovered = true;
      if (hint) hint.style.opacity = '0.4';
    });

    container.addEventListener('pointerleave', () => {
      isHovered = false;
      if (!isDragging && !isTurntableActive) {
        targetRotX = dragRotX;
        targetRotY = dragRotY;
        targetRotZ = 0;
        targetTransX = 0;
        targetTransY = 0;
        targetTransZ = 0;
      }
      if (sheen) sheen.style.opacity = '0';
      if (hint) hint.style.opacity = '0.85';
    });

    window.addEventListener('pointermove', handlePointerMove);

    // 2. Drag to Rotate (Continuous 360° Free Orbit)
    container.addEventListener('pointerdown', (e) => {
      // Don't drag if clicking buttons
      if (e.target.closest('button') || e.target.closest('.car-motion-toolbar') || e.target.closest('.car-preset-bar') || e.target.closest('.car-model-switcher')) {
        return;
      }

      isDragging = true;
      dragStartX = e.clientX;
      dragStartY = e.clientY;
      dragInitialRotY = dragRotY;
      dragInitialRotX = dragRotX;
      lastDragX = e.clientX;
      lastDragTime = performance.now();
      lastInteractionTime = performance.now();
      dragVelocityY = 0;
      container.style.cursor = 'grabbing';
      if (hint) hint.style.opacity = '0.2';
      clearActivePreset();
    });

    window.addEventListener('pointermove', (e) => {
      if (!isDragging) return;
      const deltaX = e.clientX - dragStartX;
      const deltaY = e.clientY - dragStartY;

      const now = performance.now();
      const dt = Math.max(1, now - lastDragTime);
      dragVelocityY = ((e.clientX - lastDragX) / dt) * 14;
      lastDragX = e.clientX;
      lastDragTime = now;
      lastInteractionTime = now;

      // Rotate car dynamically with drag (Continuous 360° horizontal + clamped vertical pitch)
      targetRotY = dragInitialRotY + (deltaX * 0.45);
      targetRotX = Math.max(-16, Math.min(26, dragInitialRotX - (deltaY * 0.28)));
      targetRotZ = (deltaX * 0.04);
    });

    function endDrag() {
      if (!isDragging) return;
      isDragging = false;
      dragRotY = targetRotY;
      dragRotX = targetRotX;
      container.style.cursor = 'grab';
      if (hint) hint.style.opacity = '0.85';
      lastInteractionTime = performance.now();
    }

    window.addEventListener('pointerup', endDrag);
    window.addEventListener('pointercancel', endDrag);

    // 3. Scroll to Zoom (with Page Scroll Protection)
    container.addEventListener('wheel', (e) => {
      e.preventDefault();
      const zoomStep = -Math.sign(e.deltaY) * 0.09;
      window.zoomCar(zoomStep);
    }, { passive: false });

    // 4. Double Click / Double Tap to Toggle Zoom
    container.addEventListener('dblclick', (e) => {
      if (e.target.closest('button')) return;
      if (Math.abs(targetZoom - 1.0) < 0.1) {
        window.zoomCar(0.35); // zoom in
      } else {
        window.resetCarView(); // reset to 100%
      }
    });

    // 5. Touch Pinch-to-Zoom Gesture for Mobile
    container.addEventListener('touchstart', (e) => {
      if (e.touches.length === 2) {
        const t1 = e.touches[0];
        const t2 = e.touches[1];
        initialPinchDist = Math.hypot(t1.clientX - t2.clientX, t1.clientY - t2.clientY);
        initialPinchZoom = targetZoom;
        clearActivePreset();
      }
    }, { passive: true });

    container.addEventListener('touchmove', (e) => {
      if (e.touches.length === 2 && initialPinchDist > 0) {
        e.preventDefault();
        const t1 = e.touches[0];
        const t2 = e.touches[1];
        const currentDist = Math.hypot(t1.clientX - t2.clientX, t1.clientY - t2.clientY);
        const scale = currentDist / initialPinchDist;
        targetZoom = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, initialPinchZoom * scale));
        lastInteractionTime = performance.now();
      }
    }, { passive: false });

    container.addEventListener('touchend', (e) => {
      if (e.touches.length < 2) {
        initialPinchDist = 0;
      }
    }, { passive: true });

    // 6. Keyboard Shortcuts
    window.addEventListener('keydown', (e) => {
      // Don't intercept if user is typing in an input or textarea
      if (['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName)) {
        return;
      }

      if (e.code === 'Space') {
        e.preventDefault();
        window.toggleTurntable();
      } else if (e.key === 'r' || e.key === 'R') {
        window.resetCarView();
      } else if (e.key === '+' || e.key === '=') {
        window.zoomCar(0.12);
      } else if (e.key === '-' || e.key === '_') {
        window.zoomCar(-0.12);
      } else if (e.key === '1') {
        window.setCarCameraPreset('hero');
      } else if (e.key === '2') {
        window.setCarCameraPreset('profile');
      } else if (e.key === '3') {
        window.setCarCameraPreset('low');
      } else if (e.key === '4') {
        window.setCarCameraPreset('top');
      }
    });

    // 7. Mobile Device Gyroscope Support
    if (window.DeviceOrientationEvent && 'ontouchstart' in window) {
      window.addEventListener('deviceorientation', (e) => {
        if (isDragging || isTurntableActive) return;
        const gamma = e.gamma; // Left-Right [-90, 90]
        const beta = e.beta;   // Front-Back [-180, 180]
        if (gamma !== null && beta !== null) {
          const clampedGamma = Math.max(-25, Math.min(25, gamma));
          const clampedBeta = Math.max(-20, Math.min(20, beta - 45));
          targetRotY = dragRotY + (clampedGamma * 0.45);
          targetRotX = dragRotX - (clampedBeta * 0.25);
          targetRotZ = -(clampedGamma * 0.08);
        }
      });
    }
  }

  // Updates the dynamic "Featured Spotlight" specular reflection following the cursor
  function updateSpotlightSheen(pctX, pctY, active) {
    if (!sheen) return;

    if (!active) {
      sheen.style.opacity = '0';
      return;
    }

    sheen.style.background = `radial-gradient(circle 220px at ${pctX}% ${pctY}%, rgba(255, 255, 255, 0.42) 0%, rgba(186, 230, 253, 0.22) 28%, rgba(16, 185, 129, 0.08) 55%, transparent 75%)`;
    sheen.style.opacity = '0.9';

    const config = BENZ_MODELS[currentModelKey];
    if (config && starGlint) {
      const starX = parseFloat(config.starGlint.left);
      const starY = parseFloat(config.starGlint.top);
      const dist = Math.hypot(pctX - starX, pctY - starY);

      if (dist < 18) {
        const glintIntensity = Math.max(0.6, 1 - (dist / 18));
        starGlint.style.opacity = String(glintIntensity);
        starGlint.style.transform = `translate(-50%, -50%) translateZ(35px) scale(${1 + (1 - dist / 18) * 0.6})`;
      } else {
        starGlint.style.transform = 'translate(-50%, -50%) translateZ(35px) scale(1)';
      }
    }
  }

  // Main 60fps/120fps Animation Loop with Spring-Damped Physics
  function startAnimationLoop() {
    let lastTime = performance.now();

    function render(now) {
      const delta = (now - lastTime) / 1000;
      lastTime = now;

      // Auto-Turntable 360° constant rotation
      if (isTurntableActive && !isDragging) {
        // If user recently interacted, pause turntable gently for 2.2s before resuming
        if (now - lastInteractionTime > 2200) {
          dragRotY = (dragRotY + turntableSpeed) % 360;
          targetRotY = dragRotY + (isHovered ? mouseNormX * 8 : 0);
        }
      }

      // Inertial spin decay after dragging
      if (!isDragging && !isTurntableActive && Math.abs(dragVelocityY) > 0.04) {
        dragRotY += dragVelocityY;
        dragVelocityY *= 0.93;
        targetRotY = dragRotY + (mouseNormX * 14);
      }

      // Smooth Lerp Damping (0.085 interpolation factor for silky response)
      const lerp = 0.085;
      currentRotX += (targetRotX - currentRotX) * lerp;
      currentRotY += (targetRotY - currentRotY) * lerp;
      currentRotZ += (targetRotZ - currentRotZ) * lerp;
      currentTransX += (targetTransX - currentTransX) * lerp;
      currentTransY += (targetTransY - currentTransY) * lerp;
      currentTransZ += (targetTransZ - currentTransZ) * lerp;
      currentZoom += (targetZoom - currentZoom) * 0.12;

      // Idle breathing floating motion (subtle showroom hover)
      const idleHover = Math.sin(now * 0.0018) * 5.0;
      const idlePitch = Math.sin(now * 0.0012) * 1.0;

      // Apply 3D perspective matrix transform with zoom scale to Mercedes Body
      if (bodyWrap) {
        const tx = currentTransX;
        const ty = currentTransY + idleHover;
        const tz = currentTransZ;
        const rx = currentRotX + idlePitch;
        const ry = currentRotY;
        const rz = currentRotZ;

        bodyWrap.style.transform = `translate3d(${tx.toFixed(2)}px, ${ty.toFixed(2)}px, ${tz.toFixed(2)}px) rotateX(${rx.toFixed(2)}deg) rotateY(${ry.toFixed(2)}deg) rotateZ(${rz.toFixed(2)}deg) scale(${currentZoom.toFixed(3)})`;
      }

      // Dynamic 360° Contact Floor Shadow Synchronization
      if (floorShadow) {
        const shadowScale = Math.max(0.65, (1 - (currentTransZ * 0.004) - (idleHover * 0.006))) * currentZoom;
        const radY = (currentRotY * Math.PI) / 180;
        const shadowSkew = -Math.sin(radY) * 22; // Periodic skew across all 360 degrees
        const shadowShiftX = currentTransX * 0.45;
        const shadowShiftY = -currentTransY * 0.25;

        floorShadow.style.transform = `rotateX(75deg) translateZ(-40px) translate(${shadowShiftX.toFixed(2)}px, ${shadowShiftY.toFixed(2)}px) scale(${shadowScale.toFixed(3)}) skewX(${shadowSkew.toFixed(2)}deg)`;
        floorShadow.style.opacity = isHovered ? '0.95' : '0.85';
      }

      // Directional 3D Occlusion: Front lights fade when car faces rearwards
      const radY = (currentRotY * Math.PI) / 180;
      const frontFacing = Math.cos(radY); // > 0 when front faces camera
      const flarePulse = 0.85 + Math.sin(now * 0.003) * 0.12;
      const visibilityFactor = Math.max(0, Math.min(1, (frontFacing + 0.25) * 1.6));
      const flareOpacity = (flarePulse * visibilityFactor).toFixed(2);
      const starOpacity = (0.65 * visibilityFactor).toFixed(2);

      if (flareLeft) flareLeft.style.opacity = flareOpacity;
      if (flareRight) flareRight.style.opacity = flareOpacity;
      if (starGlint) starGlint.style.opacity = starOpacity;

      // Update Zoom Level Badge in UI
      if (zoomLevelBadge) {
        zoomLevelBadge.textContent = `${Math.round(currentZoom * 100)}%`;
      }

      // Render Three.js Ambient Particle and Light Field
      if (renderer && scene && camera) {
        if (particlesMesh) {
          particlesMesh.rotation.y = now * 0.00015 + (currentRotY * 0.001);
          particlesMesh.rotation.x = Math.sin(now * 0.0001) * 0.1 + (currentRotX * 0.0008);
        }
        if (threeSpotLight) {
          threeSpotLight.position.x = mouseNormX * 6;
          threeSpotLight.position.y = -mouseNormY * 4 + 4;
          threeSpotLight.position.z = 8 * currentZoom;
        }
        camera.position.z = 10 / currentZoom;
        renderer.render(scene, camera);
      }

      animFrameId = requestAnimationFrame(render);
    }

    animFrameId = requestAnimationFrame(render);
  }

  // Initialize on DOM load
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
