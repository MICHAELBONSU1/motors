/**
 * BIG L Autos - Client Application Logic
 * Clean, Humanized, and Professional Interaction
 * No distracting icons, clean navigation, and no green status pills
 */

// Global State
let currentUser = null;
let currentChatId = null;
let chatPollingInterval = null;
let chatPollIntervalMs = 4000;
let consecutiveEmptyPolls = 0;
let lastMessageIdByChat = {};
let initialLoadDoneByChat = {};
let activeRenderedChatId = null;
let pendingInquiryCar = null;

// ============================================================================
// Universal Real-Time Notification & Audio Alert System
// Cross-Browser Support (iOS Safari, Android Chrome, Desktop Chrome, Firefox, Edge)
// ============================================================================
let audioCtx = null;
let phoneChimeAudio = null;
let isAudioUnlocked = false;
let originalDocumentTitle = document.title || 'BIG L Autos';
let tabFlashInterval = null;
let knownLastMessageIdByChat = {};
let hasInitialChatSyncDone = false;
let adminPollingInterval = null;
let swRegistration = null;

// Service Worker Registration
async function registerServiceWorker() {
  if ('serviceWorker' in navigator) {
    try {
      const reg = await navigator.serviceWorker.register('/sw.js', { scope: '/' });
      swRegistration = reg;
    } catch (err) {
      console.warn('Service Worker registration note:', err);
    }
  }
}

// Audio Engine: HTML5 Audio + Web Audio Dual Driver
function initPhoneAudio() {
  if (!phoneChimeAudio) {
    try {
      phoneChimeAudio = new Audio('/static/notification.wav');
      phoneChimeAudio.preload = 'auto';
    } catch (e) {
      console.warn('Audio element initialization note:', e);
    }
  }
}

function getAudioContext() {
  if (!audioCtx) {
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (AudioContextClass) {
      audioCtx = new AudioContextClass();
    }
  }
  if (audioCtx && audioCtx.state === 'suspended') {
    audioCtx.resume().catch(() => {});
  }
  return audioCtx;
}

// Mobile Audio Unlock on ANY user gesture (tap, touch, click, keydown)
function unlockPhoneAudio() {
  if (!phoneChimeAudio) initPhoneAudio();
  if (phoneChimeAudio && !isAudioUnlocked) {
    try {
      phoneChimeAudio.load();
      isAudioUnlocked = true;
    } catch (e) {}
  }
  const ctx = getAudioContext();
  if (ctx) {
    if (ctx.state === 'suspended') {
      ctx.resume().catch(() => {});
    }
    try {
      const buffer = ctx.createBuffer(1, 1, 22050);
      const source = ctx.createBufferSource();
      source.buffer = buffer;
      source.connect(ctx.destination);
      source.start(0);
    } catch (e) {}
  }
}

['touchstart', 'touchend', 'click', 'pointerdown', 'keydown'].forEach(evt => {
  document.addEventListener(evt, unlockPhoneAudio, { passive: true, once: false });
});

function playMessageNotificationSound() {
  // 1. Dual Audio Engine: Web Audio synthesizer bell (A5 880Hz + E6 1318Hz chime)
  try {
    const ctx = getAudioContext();
    if (ctx) {
      if (ctx.state === 'suspended') ctx.resume().catch(() => {});
      const now = ctx.currentTime;

      // Primary clear luxury bell tone (880Hz)
      const osc1 = ctx.createOscillator();
      const gain1 = ctx.createGain();
      osc1.type = 'sine';
      osc1.frequency.setValueAtTime(880, now);
      gain1.gain.setValueAtTime(0.6, now);
      gain1.gain.exponentialRampToValueAtTime(0.001, now + 0.45);
      osc1.connect(gain1);
      gain1.connect(ctx.destination);
      osc1.start(now);
      osc1.stop(now + 0.45);

      // Harmonious second chime note (1318.5Hz)
      const osc2 = ctx.createOscillator();
      const gain2 = ctx.createGain();
      osc2.type = 'sine';
      osc2.frequency.setValueAtTime(1318.5, now + 0.09);
      gain2.gain.setValueAtTime(0.55, now + 0.09);
      gain2.gain.exponentialRampToValueAtTime(0.001, now + 0.7);
      osc2.connect(gain2);
      gain2.connect(ctx.destination);
      osc2.start(now + 0.09);
      osc2.stop(now + 0.7);
    }
  } catch (err) {
    console.warn('Web Audio chime note:', err);
  }

  // 2. Play HTML5 Audio element
  try {
    if (!phoneChimeAudio) initPhoneAudio();
    if (phoneChimeAudio) {
      phoneChimeAudio.currentTime = 0;
      phoneChimeAudio.volume = 1.0;
      phoneChimeAudio.play().catch(() => {});
    }
  } catch (err) {}

  // 3. Physical phone vibration (double pulse)
  if ('vibrate' in navigator) {
    try { navigator.vibrate([250, 100, 250]); } catch (e) {}
  }
}
window.playMessageNotificationSound = playMessageNotificationSound;

function flashTabNotification(alertText) {
  if (tabFlashInterval) clearInterval(tabFlashInterval);
  if (!originalDocumentTitle) originalDocumentTitle = document.title || 'BIG L Autos';
  let toggle = false;
  tabFlashInterval = setInterval(() => {
    document.title = toggle ? alertText : originalDocumentTitle;
    toggle = !toggle;
  }, 900);
}

function stopTabFlashing() {
  if (tabFlashInterval) {
    clearInterval(tabFlashInterval);
    tabFlashInterval = null;
  }
  if (originalDocumentTitle) {
    document.title = originalDocumentTitle;
  }
}

window.addEventListener('focus', () => {
  stopTabFlashing();
});

// Universal Cross-Browser Notification Permission (supports Promise & Callback)
function requestUniversalPermission() {
  return new Promise((resolve) => {
    if (!('Notification' in window)) {
      return resolve('unsupported');
    }
    let resolved = false;
    try {
      const res = Notification.requestPermission((result) => {
        if (!resolved) {
          resolved = true;
          resolve(result);
        }
      });
      if (res && typeof res.then === 'function') {
        res.then((result) => {
          if (!resolved) {
            resolved = true;
            resolve(result);
          }
        }).catch(() => {
          if (!resolved) {
            resolved = true;
            resolve(Notification.permission);
          }
        });
      }
    } catch (e) {
      resolve(Notification.permission || 'denied');
    }
  });
}

// In-App Device Notification Permission Banner (Mobile & Desktop)
function checkAndPromptNotificationPermission() {
  if (!('Notification' in window)) return;
  if (Notification.permission === 'default') {
    showNotificationPermissionBanner();
  }
}
window.checkAndPromptNotificationPermission = checkAndPromptNotificationPermission;

function showNotificationPermissionBanner() {
  if (!('Notification' in window)) return;
  if (Notification.permission !== 'default') return;
  if (sessionStorage.getItem('dismissedNotifBanner')) return;

  let banner = document.getElementById('deviceNotificationBanner');
  if (!banner) {
    banner = document.createElement('div');
    banner.id = 'deviceNotificationBanner';
    banner.className = 'device-notif-banner';
    banner.innerHTML = `
      <div class="notif-banner-inner">
        <div class="notif-banner-text">
          <h4>Enable Phone Notifications</h4>
          <p>Get real-time alerts in your notification bar and lock screen when messages arrive.</p>
        </div>
        <div class="notif-banner-actions">
          <button type="button" onclick="handleBannerEnableNotifications()" class="btn-notif-allow">Allow</button>
          <button type="button" onclick="dismissNotificationBanner()" class="btn-notif-later">Later</button>
        </div>
      </div>
    `;
    document.body.appendChild(banner);
  }

  setTimeout(() => {
    banner.classList.add('active');
  }, 150);
}

function dismissNotificationBanner() {
  const banner = document.getElementById('deviceNotificationBanner');
  if (banner) {
    banner.classList.remove('active');
    setTimeout(() => {
      banner.remove();
    }, 400);
  }
  sessionStorage.setItem('dismissedNotifBanner', 'true');
}
window.dismissNotificationBanner = dismissNotificationBanner;

async function handleBannerEnableNotifications() {
  dismissNotificationBanner();
  await enableUserNotifications();
}
window.handleBannerEnableNotifications = handleBannerEnableNotifications;

function updateNotificationButtonState() {
  const adminBtn = document.getElementById('btnEnableNotifications');
  const custBtn = document.getElementById('btnEnableCustNotifications');
  if (!('Notification' in window)) {
    if (adminBtn) adminBtn.style.display = 'none';
    if (custBtn) custBtn.style.display = 'none';
    return;
  }

  const perm = Notification.permission;
  [adminBtn, custBtn].forEach(btn => {
    if (!btn) return;
    btn.style.display = 'inline-block';
    if (perm === 'granted') {
      btn.innerText = 'Alerts Active';
      btn.style.borderColor = 'rgba(16,185,129,0.7)';
      btn.style.color = '#34d399';
      btn.title = 'Device push notifications are active';
    } else if (perm === 'denied') {
      btn.innerText = 'Alerts Blocked';
      btn.style.borderColor = 'rgba(239,68,68,0.5)';
      btn.style.color = '#f87171';
      btn.title = 'Notifications are blocked in your browser settings';
    } else {
      btn.innerText = 'Enable Alerts';
      btn.style.borderColor = 'rgba(16,185,129,0.35)';
      btn.style.color = 'var(--mint)';
      btn.title = 'Click to enable real-time notifications';
    }
  });
}
window.updateNotificationButtonState = updateNotificationButtonState;

async function enableUserNotifications() {
  unlockPhoneAudio();
  if (!('Notification' in window)) {
    showToast('Sound alerts active! (System notifications not supported in this browser)', 'info');
    return;
  }
  try {
    const perm = await requestUniversalPermission();
    updateNotificationButtonState();
    if (perm === 'granted') {
      playMessageNotificationSound();
      if ('vibrate' in navigator) {
        try { navigator.vibrate([300, 150, 300]); } catch (e) {}
      }
      showToast('Notifications enabled on this device!', 'success');

      const welcomeTitle = 'BIG-L Autos Alerts Active';
      const welcomeOptions = {
        body: 'You will receive real-time notifications when texts arrive.',
        icon: '/static/img/logo-192.png',
        badge: '/static/img/logo-192.png',
        tag: 'welcome-notification',
        renotify: true,
        vibrate: [300, 150, 300],
        data: { url: window.location.href }
      };

      if (!swRegistration && 'serviceWorker' in navigator) {
        try { swRegistration = await navigator.serviceWorker.ready; } catch (e) {}
      }

      let shown = false;
      if (swRegistration && typeof swRegistration.showNotification === 'function') {
        try {
          await swRegistration.showNotification(welcomeTitle, welcomeOptions);
          shown = true;
        } catch (e) {}
      }
      if (!shown) {
        try {
          new Notification(welcomeTitle, welcomeOptions);
        } catch (e) {}
      }
    } else if (perm === 'denied') {
      showToast('Notifications blocked in browser settings.', 'info');
    }
  } catch (err) {
    console.error('Notification permission error:', err);
  }
}
window.enableUserNotifications = enableUserNotifications;

// Floating in-app alert banner for 100% of browsers (including iOS Safari & incognito mode)
function showInAppIncomingAlert(senderName, messageText, chatId) {
  let alertBar = document.getElementById('incomingMessageAlertBar');
  if (!alertBar) {
    alertBar = document.createElement('div');
    alertBar.id = 'incomingMessageAlertBar';
    alertBar.className = 'incoming-msg-bar';
    document.body.appendChild(alertBar);
  }

  const initial = (senderName || 'U')[0].toUpperCase();
  alertBar.innerHTML = `
    <div class="incoming-msg-content" onclick="openChatById(${chatId})">
      <div class="incoming-msg-avatar">${escapeHtml(initial)}</div>
      <div class="incoming-msg-body">
        <strong>${escapeHtml(senderName || 'New Message')}</strong>
        <p>${escapeHtml(messageText || 'Sent a new message')}</p>
      </div>
      <button type="button" class="btn-incoming-view" onclick="event.stopPropagation(); openChatById(${chatId})">Reply</button>
    </div>
  `;

  alertBar.classList.add('visible');
  if (window._incomingAlertTimer) clearTimeout(window._incomingAlertTimer);
  window._incomingAlertTimer = setTimeout(() => {
    alertBar.classList.remove('visible');
  }, 7000);
}

function openChatById(chatId) {
  const alertBar = document.getElementById('incomingMessageAlertBar');
  if (alertBar) alertBar.classList.remove('visible');
  stopTabFlashing();
  if (!chatId) return;
  if (typeof selectAdminChat === 'function' && document.getElementById('adminChatWindow')) {
    selectAdminChat(chatId, true);
  } else if (typeof selectChat === 'function') {
    selectChat(chatId, true);
  }
}
window.openChatById = openChatById;

async function triggerDesktopNotification(senderName, messageText, chatId) {
  // 1. Play sound (HTML5 audio + Web Audio)
  playMessageNotificationSound();

  // 2. Physical phone vibration
  if ('vibrate' in navigator) {
    try { navigator.vibrate([300, 150, 300]); } catch (e) {}
  }

  // 3. Tab title flasher when minimized
  if (document.hidden) {
    flashTabNotification(`New message from ${senderName}`);
  }

  // 4. Universal In-App Floating Alert (works on 100% of browsers including iOS Safari)
  if (currentChatId != chatId) {
    showInAppIncomingAlert(senderName, messageText, chatId);
  }

  // 5. Native OS Push Notification (Android top notification bar & Windows Action Center)
  if ('Notification' in window && Notification.permission === 'granted') {
    let targetUrl = '/';
    if (currentUser) {
      if (currentUser.role === 'admin' || currentUser.role === 'receptionist') {
        targetUrl = '/admin' + (chatId ? `?chat_id=${chatId}` : '');
      } else {
        targetUrl = '/customer' + (chatId ? `?chat_id=${chatId}` : '');
      }
    }

    const notifTitle = `BIG-L Autos: ${senderName}`;
    const notifOptions = {
      body: messageText ? messageText.slice(0, 120) : 'Sent you a new message',
      icon: '/static/img/logo-192.png',
      badge: '/static/img/logo-192.png',
      tag: `bigl-msg-${chatId || Date.now()}`,
      renotify: true,
      requireInteraction: true,
      vibrate: [300, 150, 300],
      data: {
        url: targetUrl,
        chatId: chatId
      }
    };

    let shown = false;

    // Service Worker notification: required for Android phone notification bar
    try {
      let reg = swRegistration;
      if (!reg && 'serviceWorker' in navigator) {
        reg = await navigator.serviceWorker.ready;
      }
      if (reg && typeof reg.showNotification === 'function') {
        await reg.showNotification(notifTitle, notifOptions);
        shown = true;
      }
    } catch (err) {
      console.warn('SW notification note:', err);
    }

    // Direct desktop window fallback (Safari macOS, Firefox, Chrome)
    if (!shown) {
      try {
        const notif = new Notification(notifTitle, notifOptions);
        notif.onclick = () => {
          window.focus();
          stopTabFlashing();
          openChatById(chatId);
          notif.close();
        };
        shown = true;
      } catch (e) {
        console.warn('Direct notification note:', e);
      }
    }
  }
}
window.triggerDesktopNotification = triggerDesktopNotification;

// Utility: Clean Toast notification (No icons)
function showToast(message, type = 'success') {
  let container = document.getElementById('toastContainer');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toastContainer';
    container.className = 'toast-container';
    document.body.appendChild(container);
  }

  const toast = document.createElement('div');
  toast.className = 'toast';
  toast.innerHTML = `<span>${message}</span>`;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(10px)';
    setTimeout(() => toast.remove(), 250);
  }, 3500);
}

// Utility: Currency format in Ghana Cedis (GH₵)
function formatMoney(amount) {
  if (amount === undefined || amount === null || isNaN(amount)) return 'GH₵ 0';
  return 'GH₵ ' + Number(amount).toLocaleString('en-US');
}

// Check Current User Session
async function checkAuthStatus() {
  try {
    const res = await fetch('/api/auth/me');
    const data = await res.json();
    if (data.authenticated) {
      currentUser = data.user;
      if (currentUser.role === 'admin' || currentUser.role === 'receptionist') {
        if (!adminPollingInterval && !document.getElementById('adminChatWindow')) {
          startAdminBackgroundPolling();
        }
      } else {
        if (!chatPollingInterval && !document.getElementById('chatWindow')) {
          startCustomerBackgroundPolling();
        }
      }
    } else {
      currentUser = null;
    }
    updateNavAuthUI();
    updateNotificationButtonState();
  } catch (err) {
    console.error('Auth check error:', err);
  }
}

// Mobile Navigation Controls
function toggleMobileNav() {
  const drawer = document.getElementById('mobileNavDrawer');
  const btn = document.getElementById('mobileNavToggle');
  if (!drawer) return;
  const isOpen = drawer.classList.contains('open');
  if (isOpen) {
    drawer.classList.remove('open');
    btn?.classList.remove('open');
  } else {
    drawer.classList.add('open');
    btn?.classList.add('open');
  }
}

function closeMobileNav() {
  const drawer = document.getElementById('mobileNavDrawer');
  const btn = document.getElementById('mobileNavToggle');
  if (drawer) drawer.classList.remove('open');
  if (btn) btn.classList.remove('open');
}

// Update Nav UI based on auth state (Desktop + Mobile Drawer)
function updateNavAuthUI() {
  const authNav = document.getElementById('navAuthArea');
  const mobileAuth = document.getElementById('mobileNavAuthArea');

  if (currentUser) {
    const isCustomer = currentUser.role === 'customer';
    if (authNav) {
      authNav.innerHTML = `
        <div style="display:flex; align-items:center; gap:8px;">
          <a href="${isCustomer ? '/customer' : '/admin'}" class="btn btn-secondary btn-sm">
            ${currentUser.name.split(' ')[0]} (${isCustomer ? 'Dashboard' : 'Receptionist'})
          </a>
          <button onclick="handleLogout()" class="btn btn-soft-green btn-sm">Log Out</button>
        </div>
      `;
    }
    if (mobileAuth) {
      mobileAuth.innerHTML = `
        <a href="${isCustomer ? '/customer' : '/admin'}" class="btn btn-secondary" onclick="closeMobileNav()" style="width:100%; text-align:center;">
          ${currentUser.name} (${isCustomer ? 'Dashboard' : 'Receptionist Desk'})
        </a>
        <button onclick="closeMobileNav(); handleLogout();" class="btn btn-dark" style="width:100%;">Log Out</button>
      `;
    }
  } else {
    if (authNav) {
      authNav.innerHTML = `
        <div style="display:flex; align-items:center; gap:8px;">
          <button onclick="openAuthModal('login')" class="btn btn-secondary btn-sm">Log In</button>
          <button onclick="openAuthModal('register')" class="btn btn-primary btn-sm">Sign Up</button>
        </div>
      `;
    }
    if (mobileAuth) {
      mobileAuth.innerHTML = `
        <button onclick="closeMobileNav(); openAuthModal('login')" class="btn btn-secondary" style="width:100%;">Log In</button>
        <button onclick="closeMobileNav(); openAuthModal('register')" class="btn btn-primary" style="width:100%;">Create Account</button>
      `;
    }
  }
}

// Toggle password visibility for inputs
function togglePasswordVisibility(inputId, btn) {
  const input = document.getElementById(inputId);
  if (!input) return;
  if (input.type === 'password') {
    input.type = 'text';
    btn.innerText = 'Hide';
  } else {
    input.type = 'password';
    btn.innerText = 'Show';
  }
}

// Open Auth Modal (Advanced Concierge Layout)
function openAuthModal(mode = 'register', carContext = null) {
  const modal = document.getElementById('authModal');
  if (!modal) return;

  const contextBox = document.getElementById('authCarContext');

  if (carContext) {
    pendingInquiryCar = carContext;
    if (contextBox) {
      contextBox.style.display = 'block';
      contextBox.innerHTML = `
        <div class="modal-context-card">
          <div class="modal-context-badge">VEHICLE SELECTED</div>
          <div class="modal-context-body">
            <img src="${carContext.image_url}" class="modal-context-img" alt="${carContext.title}">
            <div class="modal-context-info">
              <h4>${carContext.title}</h4>
              <p class="modal-context-price">${formatMoney(carContext.price)}</p>
              <span class="modal-context-sub">${carContext.year || ''} • ${Number(carContext.mileage || 0).toLocaleString()} km</span>
            </div>
          </div>
          <p class="modal-context-hint">After signing in, a direct negotiation chat with Larry will open immediately for this vehicle.</p>
        </div>
      `;
    }
  } else {
    pendingInquiryCar = null;
    if (contextBox) {
      contextBox.style.display = 'block';
      contextBox.innerHTML = `
        <div class="modal-context-card">
          <div class="modal-context-badge">SHOWROOM SPOTLIGHT</div>
          <div class="modal-context-body">
            <img src="https://images.unsplash.com/photo-1617814076367-b759c7d7e738?auto=format&fit=crop&w=800&q=80" class="modal-context-img" alt="Showroom Spotlight">
            <div class="modal-context-info">
              <h4>2023 Mercedes-AMG GT R</h4>
              <p class="modal-context-price">GH₵ 1,650,000</p>
              <span class="modal-context-sub">Handcrafted V8 • Somanya Showroom</span>
            </div>
          </div>
          <p class="modal-context-hint">Speak directly with Larry to negotiate vehicle prices, cash terms, or submit a car trade-in.</p>
        </div>
      `;
    }
  }

  switchAuthTab(mode);
  modal.classList.add('active');
}

function closeAuthModal() {
  const modal = document.getElementById('authModal');
  if (modal) modal.classList.remove('active');
}

function switchAuthTab(mode) {
  const registerTab = document.getElementById('tabRegisterBtn');
  const loginTab = document.getElementById('tabLoginBtn');
  const registerForm = document.getElementById('registerForm');
  const loginForm = document.getElementById('loginForm');
  const modalTitle = document.getElementById('authModalTitle');
  const modalSubtitle = document.getElementById('authModalSubtitle');

  if (mode === 'register') {
    registerTab?.classList.add('active');
    loginTab?.classList.remove('active');
    if (registerForm) registerForm.style.display = 'block';
    if (loginForm) loginForm.style.display = 'none';
    if (modalTitle) modalTitle.innerText = pendingInquiryCar ? 'Connect with our Receptionist' : 'Create Customer Account';
    if (modalSubtitle) modalSubtitle.innerText = pendingInquiryCar ? 'Create an account to start your chat about this car' : 'Join BIG-L Autos to chat, negotiate, and swap';
  } else {
    loginTab?.classList.add('active');
    registerTab?.classList.remove('active');
    if (loginForm) loginForm.style.display = 'block';
    if (registerForm) registerForm.style.display = 'none';
    if (modalTitle) modalTitle.innerText = 'Welcome Back';
    if (modalSubtitle) modalSubtitle.innerText = 'Log in to continue your conversation with Larry';
  }
}

// Handle Customer Registration
async function handleRegister(e) {
  if (e) e.preventDefault();
  const name = document.getElementById('regName').value.trim();
  const email = document.getElementById('regEmail').value.trim();
  const phone = document.getElementById('regPhone').value.trim();
  const password = document.getElementById('regPassword').value;

  if (!name || !email || !password) {
    showToast('Please fill in your name, email, and password.', 'info');
    return;
  }

  try {
    const res = await fetch('/api/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, email, phone, password })
    });
    const data = await res.json();

    if (res.ok) {
      currentUser = data.user;
      showToast(data.message, 'success');
      closeAuthModal();
      updateNavAuthUI();

      if (pendingInquiryCar) {
        initiateCarInquiry(pendingInquiryCar.id);
        pendingInquiryCar = null;
      } else {
        window.location.href = '/customer';
      }
    } else {
      showToast(data.error || 'Registration failed', 'info');
    }
  } catch (err) {
    console.error('Registration error:', err);
    showToast('Failed to connect to server', 'info');
  }
}

// Handle Login
async function handleLogin(e) {
  if (e) e.preventDefault();
  const email = document.getElementById('loginEmail').value.trim();
  const password = document.getElementById('loginPassword').value;

  if (!email || !password) {
    showToast('Please enter both email and password', 'info');
    return;
  }

  try {
    const res = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password })
    });
    const data = await res.json();

    if (res.ok) {
      currentUser = data.user;
      showToast(data.message, 'success');
      closeAuthModal();
      updateNavAuthUI();

      if (pendingInquiryCar) {
        initiateCarInquiry(pendingInquiryCar.id);
        pendingInquiryCar = null;
      } else {
        if (currentUser.role === 'admin') {
          window.location.href = '/admin';
        } else {
          window.location.href = '/customer';
        }
      }
    } else {
      showToast(data.error || 'Invalid credentials', 'info');
    }
  } catch (err) {
    console.error('Login error:', err);
    showToast('Failed to log in', 'info');
  }
}

// Logout
async function handleLogout() {
  try {
    await fetch('/api/auth/logout', { method: 'POST' });
    currentUser = null;
    showToast('Logged out successfully');
    window.location.href = '/';
  } catch (err) {
    console.error('Logout error:', err);
  }
}

// --- Car Catalog Logic ---
let allCars = [];

async function loadCars(filters = {}) {
  const grid = document.getElementById('carsGrid');
  if (!grid) return;

  grid.innerHTML = `
    <div style="grid-column: 1/-1; text-align:center; padding: 60px 0;">
      <p style="color:var(--gray-500); font-size:15px;">Loading available cars...</p>
    </div>
  `;

  const params = new URLSearchParams();
  if (filters.search) params.append('search', filters.search);
  if (filters.make) params.append('make', filters.make);
  if (filters.body_type) params.append('body_type', filters.body_type);
  if (filters.condition) params.append('condition', filters.condition);
  if (filters.max_price) params.append('max_price', filters.max_price);

  try {
    const res = await fetch(`/api/cars?${params.toString()}`);
    const data = await res.json();
    allCars = data.cars || [];
    renderCarsGrid(allCars);

    const countElem = document.getElementById('catalogCount');
    if (countElem) {
      countElem.innerText = `${allCars.length} Vehicle${allCars.length === 1 ? '' : 's'} Listed`;
    }
  } catch (err) {
    console.error('Error loading cars:', err);
    grid.innerHTML = `<div style="grid-column: 1/-1; text-align:center; color:var(--danger); padding:40px;">Failed to load cars. Please refresh.</div>`;
  }
}

function renderCarsGrid(cars) {
  const grid = document.getElementById('carsGrid');
  if (!grid) return;

  if (cars.length === 0) {
    const isFiltered = Boolean(document.getElementById('searchInput')?.value || document.getElementById('filterMake')?.value || document.getElementById('filterPrice')?.value);
    grid.innerHTML = `
      <div style="grid-column: 1/-1; text-align:center; padding: 56px 20px; background:#030d07; border-radius:12px; border:1px solid rgba(52,211,153,0.18); box-shadow:0 12px 32px rgba(0,0,0,0.5);">
        <h3 style="font-size:18px; font-weight:700; color:#ffffff; margin-bottom:8px;">${isFiltered ? 'No Matching Vehicles Found' : 'Showroom Inventory Updating'}</h3>
        <p style="color:var(--gray-400); font-size:13.5px; max-width:440px; margin:0 auto 18px; line-height:1.5;">${isFiltered ? 'Try resetting your search filters to view all current showroom inventory.' : 'No vehicles are currently listed. Check back shortly or contact Larry at Somanya-Roundabout (0549255121).'}</p>
        ${isFiltered ? '<button onclick="resetFilters()" class="btn btn-secondary" style="padding:8px 20px; font-size:13px; font-weight:600; border-radius:6px; cursor:pointer;">Reset Filters</button>' : '<a href="tel:0549255121" class="btn btn-secondary" style="padding:9px 22px; font-size:13px; font-weight:600; border-radius:6px; text-decoration:none; display:inline-block;">Call Showroom (0549255121)</a>'}
      </div>
    `;
    return;
  }

  grid.innerHTML = cars.map(car => {
    let badgeClass = 'badge-foreign-used';
    if (car.condition === 'Brand New') badgeClass = 'badge-brand-new';
    else if (car.condition === 'Local Used') badgeClass = 'badge-local-used';

    const safeCar = encodeURIComponent(JSON.stringify(car));
    const isUserCar = Boolean(car.is_user_seller);
    const chatBtnText = 'Enquire Now';
    const sellerTag = isUserCar && car.seller_name ? `Listed by ${escapeHtml(car.seller_name)}` : '';

    return `
      <div class="car-card">
        <div class="car-image-wrapper">
          <img src="${car.image_url}" alt="${car.title}" class="car-img" loading="lazy" onerror="this.src='https://images.unsplash.com/photo-1549399542-7e3f8b79c341?auto=format&fit=crop&w=800&q=80'">
          <span class="car-badge ${badgeClass}">${car.condition}</span>
          ${isUserCar ? `<span class="car-badge" style="top:36px; background:rgba(34,197,94,0.18); color:#34d399; border:1px solid rgba(52,211,153,0.35); font-size:10px;">${sellerTag}</span>` : ''}
          ${car.images && car.images.length > 1 ? `<span class="car-photo-badge">${car.images.length} Photos</span>` : ''}
        </div>

        <div class="car-body">
          <div class="car-header">
            <h3 class="car-title">${car.title}</h3>
            <div class="car-price-row">
              <span class="car-price">${formatMoney(car.price)}</span>
              <span class="car-price-note">• ${isUserCar ? 'Direct Seller Price' : 'Price Negotiable'}</span>
            </div>
          </div>

          <div class="car-specs">
            <div class="spec-item">
              <span class="spec-label">Year</span>
              <span class="spec-val">${car.year}</span>
            </div>
            <div class="spec-item">
              <span class="spec-label">Mileage</span>
              <span class="spec-val">${Number(car.mileage).toLocaleString()} mi</span>
            </div>
            <div class="spec-item">
              <span class="spec-label">Transmission</span>
              <span class="spec-val">${car.transmission}</span>
            </div>
            <div class="spec-item">
              <span class="spec-label">Fuel</span>
              <span class="spec-val">${car.fuel_type}</span>
            </div>
            <div class="spec-item">
              <span class="spec-label">Body</span>
              <span class="spec-val">${car.body_type}</span>
            </div>
            <div class="spec-item">
              <span class="spec-label">Color</span>
              <span class="spec-val">${car.color}</span>
            </div>
          </div>

          <div class="car-actions">
            <button onclick="handleCarInquiryClick(${car.id}, '${safeCar}')" class="btn-text-receptionist">
              ${chatBtnText}
            </button>
            <button onclick="openCarDetailsModal('${safeCar}')" class="btn-details">
              Specs
            </button>
          </div>
        </div>
      </div>
    `;
  }).join('');
}

// Filter listeners
function setupFilterListeners() {
  const searchInput = document.getElementById('filterSearch');
  const makeSelect = document.getElementById('filterMake');
  const bodySelect = document.getElementById('filterBody');
  const conditionSelect = document.getElementById('filterCondition');
  const priceSelect = document.getElementById('filterPrice');

  const runFilters = () => {
    const filters = {
      search: searchInput ? searchInput.value.trim() : '',
      make: makeSelect ? makeSelect.value : '',
      body_type: bodySelect ? bodySelect.value : '',
      condition: conditionSelect ? conditionSelect.value : '',
      max_price: priceSelect && priceSelect.value ? priceSelect.value : ''
    };
    loadCars(filters);
  };

  if (searchInput) searchInput.addEventListener('input', debounce(runFilters, 300));
  if (makeSelect) makeSelect.addEventListener('change', runFilters);
  if (bodySelect) bodySelect.addEventListener('change', runFilters);
  if (conditionSelect) conditionSelect.addEventListener('change', runFilters);
  if (priceSelect) priceSelect.addEventListener('change', runFilters);
}

function resetFilters() {
  const searchInput = document.getElementById('filterSearch');
  const makeSelect = document.getElementById('filterMake');
  const bodySelect = document.getElementById('filterBody');
  const conditionSelect = document.getElementById('filterCondition');
  const priceSelect = document.getElementById('filterPrice');

  if (searchInput) searchInput.value = '';
  if (makeSelect) makeSelect.value = '';
  if (bodySelect) bodySelect.value = '';
  if (conditionSelect) conditionSelect.value = '';
  if (priceSelect) priceSelect.value = '';

  loadCars();
}

function debounce(fn, delay) {
  let timer;
  return function(...args) {
    clearTimeout(timer);
    timer = setTimeout(() => fn.apply(this, args), delay);
  };
}

// --- CORE FEATURE: "Text Receptionist" Handler ---
async function handleCarInquiryClick(carId, safeCarEncoded) {
  let carObj = null;
  try {
    carObj = JSON.parse(decodeURIComponent(safeCarEncoded));
  } catch(e) {
    carObj = allCars.find(c => c.id === carId);
  }

  // If user is NOT logged in: Prompt to create account or login!
  if (!currentUser) {
    openAuthModal('register', carObj);
    return;
  }

  // User is logged in: Start / retrieve the inquiry chat for this specific car!
  await initiateCarInquiry(carId);
}

async function initiateCarInquiry(carId) {
  try {
    const res = await fetch('/api/inquiries/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ car_id: carId })
    });
    const data = await res.json();

    if (res.ok) {
      const isUserCar = data.car && data.car.is_user_seller;
      const targetName = isUserCar ? (data.car.seller_name ? `seller ${data.car.seller_name}` : 'the seller') : 'Larry (Dealer)';
      showToast(`Connecting you with ${targetName}...`, 'success');
      window.location.href = `/customer?chat_id=${data.chat_id}`;
    } else {
      if (data.need_auth) {
        openAuthModal('register');
      } else {
        showToast(data.error || 'Failed to start inquiry', 'info');
      }
    }
  } catch (err) {
    console.error('Error starting inquiry:', err);
    showToast('Failed to connect to chat', 'info');
  }
}

// Multi-Photo Carousel State for Car Specs Modal
let currentModalCarPhotos = [];
let currentModalPhotoIndex = 0;

function renderModalPhoto(index) {
  if (!currentModalCarPhotos || currentModalCarPhotos.length === 0) return;
  if (index < 0) index = currentModalCarPhotos.length - 1;
  if (index >= currentModalCarPhotos.length) index = 0;
  currentModalPhotoIndex = index;

  const imgEl = document.getElementById('modalCarImg');
  if (imgEl) {
    imgEl.style.opacity = '0.35';
    setTimeout(() => {
      imgEl.src = currentModalCarPhotos[index];
      imgEl.style.opacity = '1';
    }, 70);
  }

  const counter = document.getElementById('modalPhotoCounter');
  if (counter) {
    counter.textContent = currentModalCarPhotos.length > 1
      ? `Photo ${index + 1} of ${currentModalCarPhotos.length}`
      : '1 Photo';
  }

  // Highlight the active thumbnail
  const thumbs = document.querySelectorAll('.modal-thumb-btn');
  thumbs.forEach((tb, i) => {
    tb.classList.toggle('active', i === index);
  });
}

function prevModalCarPhoto() {
  renderModalPhoto(currentModalPhotoIndex - 1);
}

function nextModalCarPhoto() {
  renderModalPhoto(currentModalPhotoIndex + 1);
}

function switchModalCarPhoto(index) {
  renderModalPhoto(index);
}

// Car Specs Modal with Interactive 5-Photo Gallery
function openCarDetailsModal(safeCarEncoded) {
  let car;
  try {
    car = JSON.parse(decodeURIComponent(safeCarEncoded));
  } catch (e) {
    return;
  }

  const modal = document.getElementById('carDetailsModal');
  if (!modal) return;

  // Populate up to 5 photos
  currentModalCarPhotos = (car.images && Array.isArray(car.images) && car.images.length > 0)
    ? car.images
    : (car.image_url ? [car.image_url] : []);
  currentModalPhotoIndex = 0;

  const thumbsRow = document.getElementById('modalThumbnailsRow');
  const prevBtn = document.getElementById('btnModalPrevPhoto');
  const nextBtn = document.getElementById('btnModalNextPhoto');
  const counter = document.getElementById('modalPhotoCounter');

  if (currentModalCarPhotos.length > 1) {
    if (prevBtn) prevBtn.style.display = 'flex';
    if (nextBtn) nextBtn.style.display = 'flex';
    if (counter) counter.style.display = 'block';
    if (thumbsRow) {
      thumbsRow.style.display = 'grid';
      thumbsRow.innerHTML = currentModalCarPhotos.map((url, i) => `
        <button type="button" class="modal-thumb-btn ${i === 0 ? 'active' : ''}" onclick="switchModalCarPhoto(${i})" title="View photo ${i + 1}">
          <img src="${url}" alt="Thumbnail ${i + 1}" onerror="this.src='https://images.unsplash.com/photo-1549399542-7e3f8b79c341?auto=format&fit=crop&w=400&q=80'">
          <span class="thumb-slot-tag">${i === 0 ? 'Cover' : i + 1}</span>
        </button>
      `).join('');
    }
  } else {
    if (prevBtn) prevBtn.style.display = 'none';
    if (nextBtn) nextBtn.style.display = 'none';
    if (counter) counter.style.display = 'none';
    if (thumbsRow) {
      thumbsRow.style.display = 'none';
      thumbsRow.innerHTML = '';
    }
  }

  renderModalPhoto(0);

  const featuresList = (car.features || '').split(',').map(f => f.trim()).filter(Boolean);

  document.getElementById('modalCarTitle').innerText = car.title;
  document.getElementById('modalCarPrice').innerText = formatMoney(car.price);
  document.getElementById('modalCarCondition').innerText = car.condition;
  document.getElementById('modalCarYear').innerText = car.year;
  document.getElementById('modalCarMileage').innerText = `${Number(car.mileage).toLocaleString()} miles`;
  document.getElementById('modalCarTransmission').innerText = car.transmission;
  document.getElementById('modalCarFuel').innerText = car.fuel_type;
  document.getElementById('modalCarBody').innerText = car.body_type;
  document.getElementById('modalCarColor').innerText = car.color;
  document.getElementById('modalCarDescription').innerText = car.description || 'No description provided.';

  const isUserCar = Boolean(car.is_user_seller);
  const negEl = document.getElementById('modalNegotiableText');
  if (negEl) {
    negEl.innerText = isUserCar ? `Direct negotiation with seller (${car.seller_name || 'Owner'})` : 'Price Negotiable';
  }

  const featuresContainer = document.getElementById('modalCarFeatures');
  if (featuresContainer) {
    featuresContainer.innerHTML = featuresList.length > 0
      ? featuresList.map(f => `<span class="pill-item" style="font-size:12px; padding:4px 10px;">${f}</span>`).join('')
      : '<span style="color:var(--gray-500); font-size:13px;">Standard factory specifications</span>';
  }

  const textBtn = document.getElementById('modalTextReceptionistBtn');
  if (textBtn) {
    textBtn.innerText = 'Enquire Now';
    textBtn.onclick = () => {
      modal.classList.remove('active');
      handleCarInquiryClick(car.id, safeCarEncoded);
    };
  }

  modal.classList.add('active');
}

function closeCarDetailsModal() {
  const modal = document.getElementById('carDetailsModal');
  if (modal) modal.classList.remove('active');
}

// --- Customer Dashboard Logic ---
async function initCustomerDashboard() {
  await checkAuthStatus();
  if (!currentUser) {
    window.location.href = '/';
    return;
  }

  updateNotificationButtonState();

  const greetingElem = document.getElementById('customerWelcomeName');
  if (greetingElem) greetingElem.innerText = currentUser.name;

  const urlParams = new URLSearchParams(window.location.search);
  const targetChatId = urlParams.get('chat_id');

  await loadCustomerChats(targetChatId);
  setupSellSwapForm();

  startCustomerBackgroundPolling();
}

// Real-Time Background Synchronization for Admin and Customer
async function checkBackgroundChats(isAdmin = false) {
  try {
    const res = await fetch('/api/chats');
    if (!res.ok) return;
    const data = await res.json();
    const chats = data.chats || [];

    for (const c of chats) {
      const prevId = knownLastMessageIdByChat[c.id];
      const currentLatestId = c.last_message_id;

      if (currentLatestId) {
        if (hasInitialChatSyncDone) {
          if ((prevId === undefined || currentLatestId > prevId) && currentUser && c.last_sender_id !== currentUser.id) {
            const senderLabel = isAdmin
              ? (c.customer_name || 'Customer')
              : (c.other_party_name || 'Larry (Head Dealer)');
            triggerDesktopNotification(senderLabel, c.last_message, c.id);
          }
        }
        knownLastMessageIdByChat[c.id] = Math.max(knownLastMessageIdByChat[c.id] || 0, currentLatestId);
      }

      // Live update thread cards in DOM
      if (isAdmin) {
        updateAdminSidebarThreadPreview(c.id, c.last_message || 'Inquiry open');
        const badge = document.querySelector(`#admin-thread-${c.id} .thread-unread-badge`);
        if (badge) {
          if (c.unread_count > 0) {
            badge.textContent = `${c.unread_count} new`;
            badge.style.display = 'inline-block';
          } else {
            badge.style.display = 'none';
          }
        }
      } else {
        updateSidebarThreadPreview(c.id, c.last_message || 'Inquiry open');
        const badge = document.querySelector(`#thread-${c.id} .thread-unread-badge`);
        if (badge) {
          if (c.unread_count > 0) {
            badge.textContent = `${c.unread_count}`;
            badge.style.display = 'inline-block';
          } else {
            badge.style.display = 'none';
          }
        }
      }
    }

    if (isAdmin) {
      const container = document.getElementById('adminChatsList');
      if (container && chats.length > container.querySelectorAll('.chat-thread-card').length) {
        loadAdminChats();
      }
    } else {
      const container = document.getElementById('customerChatsList');
      if (container && chats.length > container.querySelectorAll('.chat-thread-card').length) {
        loadCustomerChats(currentChatId);
      }
    }

    hasInitialChatSyncDone = true;

    // Refresh active open conversation
    if (currentChatId) {
      if (isAdmin && typeof loadAdminChatMessages === 'function') {
        loadAdminChatMessages(currentChatId, true);
      } else if (!isAdmin && typeof loadChatMessages === 'function') {
        loadChatMessages(currentChatId, true);
      }
    }
  } catch (err) {
    console.warn('Background chat sync error:', err);
  }
}

function startCustomerBackgroundPolling() {
  if (chatPollingInterval) clearInterval(chatPollingInterval);
  checkBackgroundChats(false);
  chatPollingInterval = setInterval(() => {
    checkBackgroundChats(false);
  }, 3500);
}

function stopChatPolling() {
  if (chatPollingInterval) {
    clearInterval(chatPollingInterval);
    chatPollingInterval = null;
  }
}

// Keep polling in background so user receives audio chime and desktop notification even when minimized!
document.addEventListener('visibilitychange', () => {
  if (!document.hidden) {
    stopTabFlashing();
    if (currentUser) {
      const isAdmin = currentUser.role === 'admin' || currentUser.role === 'receptionist';
      checkBackgroundChats(isAdmin);
    }
  }
});

async function loadCustomerChats(selectChatId = null) {
  const container = document.getElementById('customerChatsList');
  if (!container) return;

  try {
    const res = await fetch('/api/chats');
    const data = await res.json();
    const chats = data.chats || [];

    if (chats.length === 0) {
      container.innerHTML = `
        <div style="text-align:center; padding: 30px 10px; color:var(--gray-500);">
          <p style="font-size:13px; margin-bottom:12px; color:#cbd5e1;">You haven't texted about any car yet.</p>
          <a href="/" class="btn btn-primary btn-sm">Browse Cars</a>
        </div>
      `;
      const chatWindow = document.getElementById('chatWindow');
      if (chatWindow) {
        chatWindow.innerHTML = `
          <div style="display:flex; flex-direction:column; align-items:center; justify-content:center; height:100%; color:#cbd5e1; padding:30px; text-align:center;">
            <h3 style="font-size:18px; color:#ffffff; font-weight:800; margin-bottom:6px;">No Active Conversation</h3>
            <p style="font-size:14px; max-width:340px; margin-bottom:20px; color:#94a3b8;">Browse our inventory, pick any car, and click <strong>"Enquire Now"</strong> to discuss price, swap options, or arrange a test drive.</p>
            <a href="/" class="btn btn-primary btn-sm">Explore Inventory</a>
          </div>
        `;
      }
      return;
    }

    container.innerHTML = chats.map(c => {
      const isSelling = c.chat_type === 'selling';
      const badgeStyle = isSelling
        ? 'background:rgba(245,158,11,0.18); color:#f59e0b; border:1px solid rgba(245,158,11,0.3);'
        : (c.is_user_seller
            ? 'background:rgba(34,197,94,0.15); color:#22c55e; border:1px solid rgba(34,197,94,0.3);'
            : 'background:rgba(52,211,153,0.1); color:#34d399; border:1px solid rgba(52,211,153,0.25);');
      const badgeText = isSelling ? 'Buyer Inquiry' : (c.is_user_seller ? 'Seller Chat' : 'Dealership');
      const partyLabel = isSelling ? `Buyer: ${c.other_party_name}` : (c.is_user_seller ? `Seller: ${c.other_party_name}` : 'Dealer: Larry');

      return `
        <div onclick="selectChat(${c.id}, true)" class="chat-thread-card ${selectChatId == c.id || currentChatId == c.id ? 'active' : ''}" id="thread-${c.id}">
          <img src="${c.car_image}" class="thread-thumb" alt="${c.car_title}">
          <div class="thread-body">
            <div style="display:flex; justify-content:space-between; align-items:center; gap:6px;">
              <span class="thread-title">${escapeHtml(c.car_title)}</span>
              <span style="font-size:10px; font-weight:800; padding:2px 7px; border-radius:100px; white-space:nowrap; ${badgeStyle}">
                ${badgeText}
              </span>
            </div>
            <div class="thread-subtitle">${escapeHtml(partyLabel)} • ${formatMoney(c.car_price)}</div>
            <div class="thread-preview">${escapeHtml(c.last_message || 'Inquiry created')}</div>
          </div>
          ${c.unread_count > 0 ? `<span class="thread-unread-badge" style="background:#10b981; color:#041009; font-size:10px; font-weight:800; padding:2px 7px; border-radius:10px;">${c.unread_count}</span>` : '<span class="thread-unread-badge" style="display:none; background:#10b981; color:#041009; font-size:10px; font-weight:800; padding:2px 7px; border-radius:10px;"></span>'}
        </div>
      `;
    }).join('');

    const urlParams = new URLSearchParams(window.location.search);
    const hasParamChat = Boolean(selectChatId || urlParams.get('chat_id'));
    const chatToOpen = selectChatId ? parseInt(selectChatId) : (currentChatId ? currentChatId : chats[0].id);
    
    // Only call selectChat on fresh open or when switching conversations
    if (!activeRenderedChatId || activeRenderedChatId !== chatToOpen) {
      selectChat(chatToOpen, hasParamChat);
    } else {
      document.querySelectorAll('.chat-thread-card').forEach(el => el.classList.remove('active'));
      const activeEl = document.getElementById(`thread-${chatToOpen}`);
      if (activeEl) activeEl.classList.add('active');
    }

  } catch (err) {
    console.error('Error loading customer chats:', err);
  }
}

// Helper to update thread card preview without re-selecting chat
function updateSidebarThreadPreview(chatId, text) {
  const card = document.getElementById(`thread-${chatId}`);
  if (card) {
    const prev = card.querySelector('.thread-preview');
    if (prev) prev.textContent = text;
    const parent = card.parentElement;
    if (parent && parent.firstElementChild !== card) {
      parent.insertBefore(card, parent.firstElementChild);
    }
  }
}

function updateAdminSidebarThreadPreview(chatId, text) {
  const card = document.getElementById(`admin-thread-${chatId}`);
  if (card) {
    const prev = card.querySelector('.thread-preview');
    if (prev) prev.textContent = text;
    const parent = card.parentElement;
    if (parent && parent.firstElementChild !== card) {
      parent.insertBefore(card, parent.firstElementChild);
    }
  }
}

// Helper for smooth, bulletproof scrolling to the bottom of message containers on mobile
function scrollChatToBottom(container) {
  if (!container) return;
  container.scrollTop = container.scrollHeight;
  requestAnimationFrame(() => {
    container.scrollTop = container.scrollHeight;
    const last = container.lastElementChild;
    if (last && typeof last.scrollIntoView === 'function') {
      last.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  });
  setTimeout(() => {
    container.scrollTop = container.scrollHeight;
  }, 50);
}

// Window resize handler ensuring clean transitions between desktop side-by-side & mobile dual-view
window.addEventListener('resize', () => {
  if (window.innerWidth > 900) {
    document.body.classList.remove('mobile-chat-active');
    const custLayout = document.getElementById('customerDashboardLayout');
    if (custLayout) custLayout.classList.remove('mobile-chat-active');
    const adminLayout = document.getElementById('adminInquiriesLayout');
    if (adminLayout) adminLayout.classList.remove('mobile-chat-active');
  }
});

function openMobileChatView() {
  document.body.classList.add('mobile-chat-active');
  const layout = document.getElementById('customerDashboardLayout');
  if (layout) {
    layout.classList.add('mobile-chat-active');
  }
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function closeMobileChatView() {
  document.body.classList.remove('mobile-chat-active');
  const layout = document.getElementById('customerDashboardLayout');
  if (layout) {
    layout.classList.remove('mobile-chat-active');
  }
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function openMobileAdminChatView() {
  document.body.classList.add('mobile-chat-active');
  const layout = document.getElementById('adminInquiriesLayout');
  if (layout) {
    layout.classList.add('mobile-chat-active');
  }
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function closeMobileAdminChatView() {
  document.body.classList.remove('mobile-chat-active');
  const layout = document.getElementById('adminInquiriesLayout');
  if (layout) {
    layout.classList.remove('mobile-chat-active');
  }
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

async function selectChat(chatId, shouldActivateMobile = false) {
  currentChatId = chatId;
  document.querySelectorAll('.chat-thread-card').forEach(el => el.classList.remove('active'));
  const activeEl = document.getElementById(`thread-${chatId}`);
  if (activeEl) activeEl.classList.add('active');

  if (shouldActivateMobile && window.innerWidth <= 900) {
    openMobileChatView();
  }

  await loadChatMessages(chatId, false);
}

function scrollToThreadList() {
  closeMobileChatView();
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function scrollToAdminThreadList() {
  closeMobileAdminChatView();
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

async function loadChatMessages(chatId, isBackgroundPoll = false) {
  try {
    // Delta request: only fetch messages newer than the last one we already rendered.
    const since = lastMessageIdByChat[chatId] || 0;
    const res = await fetch(`/api/chats/${chatId}/messages?since=${since}`);
    if (!res.ok) return;

    const data = await res.json();
    const chat = data.chat;
    const messages = data.messages || [];

    // Only rebuild the chat frame when opening a *different* conversation.
    // Re-opening the same chat must never wipe the existing messages.
    const needsFrame = !isBackgroundPoll && activeRenderedChatId !== chatId;

    if (needsFrame) {
      renderChatWindowFrame(chat);
      activeRenderedChatId = chatId;
    }

    const container = document.getElementById('chatMessagesContainer');
    if (!container) return;

    if (messages.length === 0) {
      // Nothing new. Only paint the empty state on a truly fresh open.
      if (needsFrame) {
        renderMessagesList([], true);
      }
      adaptChatPolling(false);
      return;
    }

    const newestId = Math.max(...messages.map(m => m.id));
    lastMessageIdByChat[chatId] = Math.max(lastMessageIdByChat[chatId] || 0, newestId);

    if (needsFrame) {
      // Fresh open of this conversation: render full history.
      renderMessagesList(messages, true);
    } else {
      // Background poll / re-open same chat: append only brand-new messages.
      appendMessagesList(messages);
    }

    adaptChatPolling(true);
  } catch (err) {
    console.error('Error loading messages:', err);
  }
}

function messageRowHtml(m) {
  const isSentByMe = currentUser && m.sender_id === currentUser.id;
  const initial = m.sender_name ? m.sender_name[0].toUpperCase() : (isSentByMe ? 'U' : 'S');
  const senderDisplay = isSentByMe ? 'You' : (m.sender_name || 'Seller');
  return `
    <div class="message-row ${isSentByMe ? 'sent' : 'received'}" data-msg-id="${m.id}">
      <div class="msg-avatar ${isSentByMe ? 'customer-avatar' : 'receptionist-avatar'}">${initial}</div>
      <div class="msg-bubble-wrap">
        <div class="msg-bubble">${escapeHtml(m.message)}</div>
        <div class="msg-meta">
          <span class="msg-sender">${escapeHtml(senderDisplay)}</span>
          <span>•</span>
          <span class="msg-time">${m.created_at || 'Recently'}</span>
        </div>
      </div>
    </div>
  `;
}

function appendMessagesList(messages) {
  const container = document.getElementById('chatMessagesContainer');
  if (!container || !messages.length) return;

  const wasAtBottom = container.scrollHeight - container.scrollTop <= container.clientHeight + 140;
  container.insertAdjacentHTML('beforeend', messages.map(messageRowHtml).join(''));

  if (wasAtBottom) {
    scrollChatToBottom(container);
  }
}

function renderChatWindowFrame(chat) {
  const chatWindow = document.getElementById('chatWindow');
  if (!chatWindow) return;

  const isSelling = chat.chat_type === 'selling';
  const otherName = chat.other_party_name || (chat.is_user_seller ? chat.seller_name : 'Larry (Head Dealer)');
  const otherRole = chat.other_party_role || (chat.is_user_seller ? 'Seller' : 'Dealership');

  const chipsHtml = isSelling
    ? `
      <div class="negotiation-chips">
        <span class="negotiation-chip" onclick="quickSend('Yes, the car is still available! Where are you located?')">Confirm availability</span>
        <span class="negotiation-chip" onclick="quickSend('The price is slightly negotiable for serious cash buyers.')">Discuss price</span>
        <span class="negotiation-chip" onclick="quickSend('When would you be free for an inspection or test drive?')">Invite for inspection</span>
      </div>
    `
    : `
      <div class="negotiation-chips">
        <span class="negotiation-chip" onclick="quickSend('Is the price negotiable for cash?')">Ask for cash discount</span>
        <span class="negotiation-chip" onclick="quickSend('Can I come inspect and test drive this car tomorrow?')">Request test drive</span>
        <span class="negotiation-chip" onclick="quickSend('I have a car I would like to swap for this, what is the process?')">Inquire about swap</span>
        <span class="negotiation-chip" onclick="quickSend('What is the lowest last price you can take?')">Ask for best price</span>
      </div>
    `;

  chatWindow.innerHTML = `
    <div class="chat-header">
      <button type="button" class="btn-mobile-chat-back" onclick="scrollToThreadList()" title="Back to conversations">
        ← Chats
      </button>
      <div class="chat-pinned-car">
        <img src="${chat.car_image}" class="pinned-car-img" alt="${chat.car_title}">
        <div class="pinned-car-info">
          <h3>${chat.car_title}</h3>
          <p>${formatMoney(chat.car_price)} <span class="pinned-car-spec">(${chat.car_transmission} • ${Number(chat.car_mileage).toLocaleString()} mi)</span></p>
        </div>
      </div>
      <div class="chat-header-counterpart" style="text-align:right;">
        <span style="font-size:12px; color:#c7ecd9; font-weight:700; display:block;">
          ${escapeHtml(otherRole)}: ${escapeHtml(otherName)}
        </span>
        ${chat.customer_phone && isSelling ? `<a href="tel:${chat.customer_phone}" style="font-size:11px; color:var(--mint); font-weight:600;">Tel: ${chat.customer_phone}</a>` : ''}
        ${chat.seller_phone && !isSelling && chat.is_user_seller ? `<a href="tel:${chat.seller_phone}" style="font-size:11px; color:var(--mint); font-weight:600;">Tel: ${chat.seller_phone}</a>` : ''}
      </div>
    </div>

    ${chipsHtml}

    <!-- Messages Container -->
    <div class="chat-messages-container" id="chatMessagesContainer"></div>

    <!-- Message Input Bar -->
    <div class="chat-input-bar">
      <input type="text" id="chatMessageInput" class="chat-input" placeholder="Type a message..." onkeydown="if(event.key==='Enter') sendMessage()">
      <button type="button" onclick="sendMessage()" class="btn btn-primary btn-sm btn-send-msg" id="btnSendMessage">Send</button>
    </div>
  `;
}

function renderMessagesList(messages, forceScroll = false) {
  const container = document.getElementById('chatMessagesContainer');
  if (!container) return;

  const wasAtBottom = container.scrollHeight - container.scrollTop <= container.clientHeight + 140;

  if (messages.length === 0) {
    container.innerHTML = `
      <div style="text-align:center; padding:30px 16px; color:#94a3b8; font-size:13px;">
        <p>No messages yet in this conversation.</p>
        <p style="margin-top:6px; font-size:12px; color:#64748b;">Type a message below to start negotiating!</p>
      </div>
    `;
    return;
  }

  container.innerHTML = messages.map(messageRowHtml).join('');

  if (forceScroll || wasAtBottom) {
    scrollChatToBottom(container);
  }
}

async function sendMessage() {
  const input = document.getElementById('chatMessageInput');
  const btn = document.getElementById('btnSendMessage');
  if (!input || !currentChatId) return;

  const text = input.value.trim();
  if (!text) return;

  const pendingId = 'pending-' + Date.now();
  const container = document.getElementById('chatMessagesContainer');
  input.value = '';
  btn.disabled = true;

  // Optimistic: show the outgoing message immediately so the UI feels instant on mobile.
  const meInitial = (currentUser && currentUser.name ? currentUser.name[0].toUpperCase() : 'U');
  const optimisticRow = `
    <div class="message-row sent" data-client-id="${pendingId}">
      <div class="msg-avatar customer-avatar">${meInitial}</div>
      <div class="msg-bubble-wrap">
        <div class="msg-bubble">${escapeHtml(text)}</div>
        <div class="msg-meta"><span class="msg-sender">You</span><span>•</span><span class="msg-time">Sending…</span></div>
      </div>
    </div>`;
  if (container) {
    container.insertAdjacentHTML('beforeend', optimisticRow);
    scrollChatToBottom(container);
  }

  let serverMsg = null;
  let sendOk = false;
  try {
    const res = await fetch(`/api/chats/${currentChatId}/messages`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text })
    });
    if (res.ok) {
      const data = await res.json();
      serverMsg = data.message;
      sendOk = true;
      lastMessageIdByChat[currentChatId] = Math.max(lastMessageIdByChat[currentChatId] || 0, data.message_id);
    }
  } catch (err) {
    console.error('Error sending message:', err);
  } finally {
    btn.disabled = false;
  }

  // Replace the optimistic row with the server-confirmed message.
  const pendingEl = container ? container.querySelector(`[data-client-id="${pendingId}"]`) : null;
  if (pendingEl) pendingEl.remove();

  if (sendOk && serverMsg && container) {
    container.insertAdjacentHTML('beforeend', messageRowHtml(serverMsg));
    scrollChatToBottom(container);
    // Fetch any newer replies (e.g. receptionist auto-response) without refetching history.
    setTimeout(() => {
      loadChatMessages(currentChatId, true);
    }, 150);
    // Live update thread preview in sidebar WITHOUT re-selecting or triggering window.scrollTo(0)
    updateSidebarThreadPreview(currentChatId, text);
    input.focus();
  } else {
    // Send failed: put the text back so the user can retry.
    input.value = text;
    input.focus();
    showToast('Failed to send message', 'info');
  }
}

function quickSend(messageText) {
  const input = document.getElementById('chatMessageInput');
  if (input) {
    input.value = messageText;
    sendMessage();
  }
}

// Sell / Swap Form in Customer Dashboard
function setupSellSwapForm() {
  const form = document.getElementById('sellSwapForm');
  if (!form) return;

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const type = document.getElementById('swapType').value;
    const make = document.getElementById('swapMake').value.trim();
    const model = document.getElementById('swapModel').value.trim();
    const year = document.getElementById('swapYear').value;
    const mileage = document.getElementById('swapMileage').value;
    const price = document.getElementById('swapPrice').value;
    const notes = document.getElementById('swapNotes').value.trim();

    try {
      const res = await fetch('/api/swap-sell', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          request_type: type,
          car_make: make,
          car_model: model,
          car_year: parseInt(year),
          car_mileage: parseInt(mileage || 0),
          expected_price: parseFloat(price || 0),
          condition_notes: notes
        })
      });
      const data = await res.json();
      if (res.ok) {
        showToast(data.message, 'success');
        form.reset();
        loadCustomerSwapRequests();
      } else {
        showToast(data.error || 'Submission failed', 'info');
      }
    } catch (err) {
      console.error('Swap submit error:', err);
      showToast('Error submitting request', 'info');
    }
  });

  loadCustomerSwapRequests();
}

async function loadCustomerSwapRequests() {
  const container = document.getElementById('customerSwapList');
  if (!container) return;

  try {
    const res = await fetch('/api/swap-sell');
    const data = await res.json();
    const list = data.requests || [];

    if (list.length === 0) {
      container.innerHTML = `<p style="color:var(--gray-500); font-size:13px;">No sell or swap evaluations submitted yet.</p>`;
      return;
    }

    container.innerHTML = list.map(r => `
      <div style="background:var(--white); border:1px solid var(--gray-200); border-radius:var(--radius-sm); padding:14px; margin-bottom:10px;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
          <span style="font-size:11px; font-weight:700; text-transform:uppercase; padding:3px 8px; border-radius:4px; background:var(--gray-100); color:var(--gray-800);">
            ${r.request_type === 'swap' ? 'Swap Request' : 'Sell Evaluation'}
          </span>
          <span style="font-size:12px; font-weight:600; color:var(--gray-600);">${r.status}</span>
        </div>
        <h4 style="font-size:15px; font-weight:750; color:var(--black-deep);">${r.car_year} ${r.car_make} ${r.car_model}</h4>
        <p style="font-size:13px; color:var(--gray-600); margin:4px 0;">Expected Valuation: ${formatMoney(r.expected_price || 0)} • ${Number(r.car_mileage || 0).toLocaleString()} mi</p>
        ${r.condition_notes ? `<p style="font-size:12px; color:var(--gray-500); font-style:italic;">"${escapeHtml(r.condition_notes)}"</p>` : ''}
      </div>
    `).join('');
  } catch (err) {
    console.error('Error loading swap list:', err);
  }
}

// --- Admin / Receptionist Portal Logic ---
async function initAdminPortal() {
  await checkAuthStatus();
  if (!currentUser || (currentUser.role !== 'admin' && currentUser.role !== 'receptionist')) {
    window.location.href = '/';
    return;
  }

  updateNotificationButtonState();
  loadAdminStats();
  loadAdminCars();
  loadAdminChats();
  loadAdminSwapRequests();
  setupAddCarForm();

  startAdminBackgroundPolling();
}

function startAdminBackgroundPolling() {
  if (adminPollingInterval) clearInterval(adminPollingInterval);
  checkBackgroundChats(true);
  adminPollingInterval = setInterval(() => {
    checkBackgroundChats(true);
  }, 3500);
}

async function loadAdminStats() {
  try {
    const res = await fetch('/api/admin/stats');
    const data = await res.json();
    document.getElementById('statTotalCars').innerText = data.total_cars;
    document.getElementById('statAvailableCars').innerText = data.available_cars;
    document.getElementById('statActiveChats').innerText = data.total_chats;
    document.getElementById('statPendingRequests').innerText = data.pending_requests;
  const psEl = document.getElementById('statPendingSellers');
  if (psEl) psEl.innerText = data.pending_sellers || 0;
  const badge = document.getElementById('pendingSellersBadge');
  if (badge) {
    const count = data.pending_sellers || 0;
    badge.textContent = count;
    badge.style.display = count > 0 ? 'inline-block' : 'none';
  }
  } catch (err) {
    console.error('Error loading stats:', err);
  }
}

async function loadAdminCars() {
  const container = document.getElementById('adminCarsList');
  if (!container) return;

  try {
    const res = await fetch('/api/cars');
    const data = await res.json();
    const cars = data.cars || [];

    container.innerHTML = cars.map(c => `
      <div class="admin-car-item" style="display:flex; align-items:center; justify-content:space-between; background:var(--white); border:1px solid var(--gray-200); border-radius:var(--radius-sm); padding:12px 16px; margin-bottom:10px;">
        <div style="display:flex; align-items:center; gap:14px;">
          <img src="${c.image_url}" style="width:52px; height:52px; border-radius:6px; object-fit:cover;" alt="${c.title}">
          <div>
            <h4 style="font-size:14px; font-weight:750; color:var(--black-deep);">${c.title}</h4>
            <p style="font-size:13px; font-weight:700; color:var(--green-primary);">${formatMoney(c.price)} <span style="font-size:11px; font-weight:500; color:var(--gray-500);">• ${c.year} • ${c.transmission} • ${c.status}</span></p>
          </div>
        </div>
        <div class="admin-car-item-actions" style="display:flex; align-items:center; gap:8px;">
          <button onclick="toggleCarStatus(${c.id}, '${c.status === 'Available' ? 'Sold' : 'Available'}')" class="btn btn-secondary btn-sm" style="font-size:11px;">
            Mark as ${c.status === 'Available' ? 'Sold' : 'Available'}
          </button>
          <button onclick="deleteCarListing(${c.id})" class="btn btn-sm" style="background:#fee2e2; color:#b91c1c; border:none; font-size:11px;">
            Delete
          </button>
        </div>
      </div>
    `).join('');
  } catch (err) {
    console.error('Error loading admin cars:', err);
  }
}

async function toggleCarStatus(carId, newStatus) {
  try {
    const res = await fetch(`/api/cars/${carId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: newStatus })
    });
    if (res.ok) {
      showToast(`Car marked as ${newStatus}`);
      loadAdminCars();
      loadAdminStats();
    }
  } catch (err) {
    console.error('Status toggle error:', err);
  }
}

async function deleteCarListing(carId) {
  if (!confirm('Are you sure you want to remove this car listing?')) return;

  try {
    const res = await fetch(`/api/cars/${carId}`, { method: 'DELETE' });
    if (res.ok) {
      showToast('Car listing removed');
      loadAdminCars();
      loadAdminStats();
    }
  } catch (err) {
    console.error('Delete error:', err);
  }
}

// 5-Photo Upload State for Admin Car Publishing
let adminUploadedFiles = [];

function renderAdminPhotoSlots() {
  const grid = document.getElementById('adminPhotoSlotsGrid');
  const badge = document.getElementById('adminPhotoBadge');
  const container = document.getElementById('imagePreviewContainer');
  if (!grid) return;

  const urlInput = document.getElementById('carImageUrls');
  const urlList = (urlInput ? urlInput.value.split('\n') : [])
    .map(u => u.trim())
    .filter(u => u.startsWith('http'));

  const allItems = [];
  adminUploadedFiles.forEach((file, idx) => {
    allItems.push({ type: 'file', data: file, src: URL.createObjectURL(file), index: idx });
  });
  urlList.forEach((url, idx) => {
    if (allItems.length < 5) {
      allItems.push({ type: 'url', data: url, src: url, index: idx });
    }
  });

  if (badge) {
    badge.textContent = `${allItems.length} / 5 Selected`;
  }

  if (allItems.length === 0) {
    if (container) container.style.display = 'none';
    grid.innerHTML = '';
    return;
  }

  if (container) container.style.display = 'block';

  grid.innerHTML = allItems.map((item, i) => `
    <div class="preview-slot-card" style="position:relative; aspect-ratio:4/3; border-radius:6px; overflow:hidden; border:${i === 0 ? '2px solid #10b981' : '1px solid rgba(255,255,255,0.18)'}; background:#000;">
      <img src="${item.src}" style="width:100%; height:100%; object-fit:cover;" alt="Photo ${i + 1}">
      <span style="position:absolute; bottom:2px; left:2px; font-size:9px; font-weight:800; padding:1px 5px; border-radius:3px; background:${i === 0 ? '#059669' : 'rgba(0,0,0,0.75)'}; color:#fff;">
        ${i === 0 ? 'Cover' : `Slot ${i + 1}`}
      </span>
      <button type="button" onclick="removeAdminPhotoSlot(${i}, '${item.type}')" title="Remove photo" style="position:absolute; top:2px; right:2px; width:18px; height:18px; border-radius:50%; background:rgba(239,68,68,0.9); color:#fff; border:none; cursor:pointer; font-size:11px; font-weight:900; line-height:1; display:flex; align-items:center; justify-content:center;">&times;</button>
    </div>
  `).join('');
}

function removeAdminPhotoSlot(slotIdx, itemType) {
  if (itemType === 'file') {
    adminUploadedFiles.splice(slotIdx, 1);
  } else {
    const urlInput = document.getElementById('carImageUrls');
    if (urlInput) {
      const urls = urlInput.value.split('\n').map(u => u.trim()).filter(Boolean);
      const urlIdx = slotIdx - adminUploadedFiles.length;
      if (urlIdx >= 0 && urlIdx < urls.length) {
        urls.splice(urlIdx, 1);
        urlInput.value = urls.join('\n');
      }
    }
  }
  renderAdminPhotoSlots();
}

// Add Car Form with 5-Photo Uploading
function setupAddCarForm() {
  const form = document.getElementById('addCarForm');
  if (!form) return;

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const formData = new FormData(form);

    // Ensure all 5 curated files are appended to formData
    formData.delete('image_files');
    formData.delete('image_file');
    adminUploadedFiles.forEach(file => {
      formData.append('image_files', file);
    });

    try {
      const res = await fetch('/api/cars', {
        method: 'POST',
        body: formData
      });
      const data = await res.json();
      if (res.ok) {
        showToast(data.message || 'Vehicle with up to 5 photos published successfully!', 'success');
        form.reset();
        adminUploadedFiles = [];
        renderAdminPhotoSlots();
        closeModal('addCarModal');
        loadAdminCars();
        loadAdminStats();
      } else {
        showToast(data.error || 'Failed to upload car', 'info');
      }
    } catch (err) {
      console.error('Add car error:', err);
      showToast('Server error while uploading car', 'info');
    }
  });

  const filesInput = document.getElementById('carImageFiles') || document.getElementById('carImageFile');
  if (filesInput) {
    filesInput.addEventListener('change', () => {
      const newFiles = Array.from(filesInput.files);
      for (const f of newFiles) {
        if (adminUploadedFiles.length < 5) {
          adminUploadedFiles.push(f);
        }
      }
      renderAdminPhotoSlots();
    });
  }

  const urlsTextarea = document.getElementById('carImageUrls');
  if (urlsTextarea) {
    urlsTextarea.addEventListener('input', () => {
      renderAdminPhotoSlots();
    });
  }
}

function escapeJs(str) {
  if (!str) return '';
  return String(str).replace(/\\/g, '\\\\').replace(/'/g, "\\'").replace(/"/g, '&quot;');
}
window.escapeJs = escapeJs;

// Admin Delete Individual User Account
async function deleteUserAccount(userId, userName, userEmail) {
  if (!userId) return;
  const nameStr = userName || `User #${userId}`;
  const emailStr = userEmail ? ` (${userEmail})` : '';
  const confirmed = confirm(
    `Are you sure you want to permanently delete the account for:\n\n• ${nameStr}${emailStr}\n\nThis will permanently remove the user, all their chat messages, inquiries, and vehicle listings.\n\nThis action cannot be undone.`
  );
  if (!confirmed) return;

  try {
    const res = await fetch(`/api/admin/users/${userId}`, {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' }
    });
    const data = await res.json();
    if (res.ok && data.success) {
      showToast(data.message || 'Account deleted successfully.', 'success');
      if (typeof loadAdminSellers === 'function') loadAdminSellers();
      if (typeof loadAdminChats === 'function') loadAdminChats();
      if (typeof loadAdminStats === 'function') loadAdminStats();
      if (window.currentChatCustomerId == userId) {
        const chatWin = document.getElementById('adminChatWindow');
        if (chatWin) {
          chatWin.innerHTML = `
            <div style="display:flex; flex-direction:column; align-items:center; justify-content:center; height:100%; color:#cbd5e1; text-align:center; padding:30px;">
              <h3 style="font-family:var(--font-heading); font-size:18px; color:#ffffff; font-weight:800; margin-bottom:6px;">Receptionist Chat Center</h3>
              <p style="font-size:13.5px; max-width:340px; color:#94a3b8; line-height:1.5;">Customer account deleted. Select another customer inquiry on the left.</p>
            </div>
          `;
        }
      }
    } else {
      showToast(data.error || 'Failed to delete account', 'error');
    }
  } catch (err) {
    console.error('Delete account error:', err);
    showToast('Network error while deleting account', 'error');
  }
}
window.deleteUserAccount = deleteUserAccount;

// Admin Clean Users Helper
async function cleanAllNonAdminUsers() {
  if (!confirm("Are you sure you want to remove everyone from the system except the administrator?\n\nThis will permanently delete all customer/test accounts, chats, and submissions, keeping only Larry (Head Dealer & Admin).")) {
    return;
  }

  try {
    const res = await fetch('/api/admin/clean-users', { method: 'POST' });
    const data = await res.json();
    if (res.ok && data.success) {
      showToast(data.message, 'success');
      if (typeof loadAdminSellers === 'function') loadAdminSellers();
      if (typeof loadAdminChats === 'function') loadAdminChats();
      if (typeof loadAdminStats === 'function') loadAdminStats();
    } else {
      showToast(data.error || 'Failed to clean users', 'info');
    }
  } catch (err) {
    console.error('Clean users error:', err);
    showToast('Server error during user cleanup', 'info');
  }
}

// Admin / Receptionist Chat Management
async function loadAdminChats() {
  const container = document.getElementById('adminChatsList');
  if (!container) return;

  try {
    const res = await fetch('/api/chats');
    const data = await res.json();
    const chats = data.chats || [];

    if (chats.length === 0) {
      container.innerHTML = `<p style="color:#cbd5e1; font-size:13px; padding:20px; text-align:center;">No customer inquiries yet.</p>`;
      return;
    }

    container.innerHTML = chats.map(c => `
      <div onclick="selectAdminChat(${c.id}, true)" class="chat-thread-card ${currentChatId == c.id ? 'active' : ''}" id="admin-thread-${c.id}">
        <img src="${c.car_image}" class="thread-thumb" alt="${c.car_title}">
        <div class="thread-body">
          <div style="display:flex; justify-content:space-between; align-items:center; gap:6px;">
            <span style="font-size:14px; font-weight:800; color:#ffffff;">${c.customer_name}</span>
            <span style="font-size:10px; font-weight:700; padding:2px 6px; border-radius:4px; ${c.is_user_seller ? 'background:rgba(245,158,11,0.2); color:#f59e0b;' : 'background:rgba(34,197,94,0.15); color:#22c55e;'}">
              ${c.is_user_seller ? 'Seller: ' + (c.seller_name || 'User') : 'Dealer Car'}
            </span>
            ${c.unread_count > 0 ? `<span class="thread-unread-badge" style="background:#10b981; color:#041009; font-size:10px; font-weight:800; padding:2px 7px; border-radius:10px;">${c.unread_count} new</span>` : '<span class="thread-unread-badge" style="display:none; background:#10b981; color:#041009; font-size:10px; font-weight:800; padding:2px 7px; border-radius:10px;"></span>'}
          </div>
          <div class="thread-subtitle">${c.car_title}</div>
          <div class="thread-preview">${c.last_message || 'Inquiry open'}</div>
        </div>
      </div>
    `).join('');

    if (!currentChatId && chats.length > 0) {
      selectAdminChat(chats[0].id, false);
    }
  } catch (err) {
    console.error('Error loading admin chats:', err);
  }
}

async function selectAdminChat(chatId, shouldScroll = false) {
  currentChatId = chatId;
  document.querySelectorAll('.chat-thread-card').forEach(el => el.classList.remove('active'));
  const activeEl = document.getElementById(`admin-thread-${chatId}`);
  if (activeEl) activeEl.classList.add('active');

  if (shouldScroll && window.innerWidth <= 900) {
    openMobileAdminChatView();
  }

  await loadAdminChatMessages(chatId, false);

  if (shouldScroll && window.innerWidth <= 900) {
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }
}

async function loadAdminChatMessages(chatId, isBackgroundPoll = false) {
  try {
    const res = await fetch(`/api/chats/${chatId}/messages`);
    if (!res.ok) return;

    const data = await res.json();
    const chat = data.chat;
    const messages = data.messages || [];

    if (!isBackgroundPoll || activeRenderedChatId !== chatId) {
      renderAdminChatWindowFrame(chat);
      activeRenderedChatId = chatId;
      renderAdminMessagesList(messages, chat, true);
    } else {
      renderAdminMessagesList(messages, chat, false);
    }

  } catch (err) {
    console.error('Error loading admin chat messages:', err);
  }
}

function renderAdminChatWindowFrame(chat) {
  const windowElem = document.getElementById('adminChatWindow');
  if (!windowElem) return;

  window.currentChatCustomerId = chat.customer_id;

  const sellerBadge = chat.is_user_seller
    ? `<span style="font-size:11px; background:rgba(245,158,11,0.2); color:#f59e0b; padding:3px 8px; border-radius:100px; font-weight:700;">Seller: ${escapeHtml(chat.seller_name || 'User')}</span>`
    : `<span style="font-size:11px; background:rgba(34,197,94,0.15); color:#22c55e; padding:3px 8px; border-radius:100px; font-weight:700;">Dealership Vehicle</span>`;

  windowElem.innerHTML = `
    <div class="chat-header">
      <button type="button" class="btn-mobile-chat-back" onclick="scrollToAdminThreadList()" title="Back to inquiries">
        ← Inquiries
      </button>
      <div class="chat-pinned-car">
        <img src="${chat.car_image}" class="pinned-car-img" alt="${chat.car_title}">
        <div class="pinned-car-info">
          <h3>${chat.customer_name} <span class="pinned-car-spec">(${chat.customer_phone || chat.customer_email})</span></h3>
          <p>${chat.car_title} • ${formatMoney(chat.car_price)} ${sellerBadge}</p>
        </div>
      </div>
      <div style="display:flex; gap:6px; align-items:center;">
        <a href="tel:${chat.customer_phone}" class="btn btn-secondary btn-sm" style="font-size:11px; padding:5px 9px;">Call</a>
        <button type="button" onclick="deleteUserAccount(${chat.customer_id}, '${escapeJs(chat.customer_name)}', '${escapeJs(chat.customer_email || '')}')" class="btn btn-sm" style="background:#450a0a; color:#f87171; border:1px solid #991b1b; font-size:11px; padding:5px 9px; font-weight:700; cursor:pointer;" title="Delete this customer's account">Delete Account</button>
      </div>
    </div>

    <!-- Quick receptionist canned responses (No icons) -->
    <div class="negotiation-chips">
      <span class="negotiation-chip" onclick="quickAdminSend('Hello! Yes, the price is slightly negotiable for serious cash buyers. What offer do you have in mind?')">Cash price response</span>
      <span class="negotiation-chip" onclick="quickAdminSend('We would love to show you the car. Would tomorrow between 10am and 4pm work for a viewing and test drive?')">Schedule viewing</span>
      <span class="negotiation-chip" onclick="quickAdminSend('We accept vehicle swaps! Could you tell me the year, make, and mileage of the car you wish to swap?')">Request swap details</span>
    </div>

    <div class="chat-messages-container" id="adminMessagesContainer"></div>

    <div class="chat-input-bar">
      <input type="text" id="adminChatInput" class="chat-input" placeholder="Type a reply..." onkeydown="if(event.key==='Enter') sendAdminMessage()">
      <button type="button" onclick="sendAdminMessage()" class="btn btn-primary btn-sm btn-send-msg" id="btnAdminSend">Send</button>
    </div>
  `;
}

function renderAdminMessagesList(messages, chat, forceScroll = false) {
  const container = document.getElementById('adminMessagesContainer');
  if (!container) return;

  const currentCount = container.querySelectorAll('.message-row').length;
  if (!forceScroll && currentCount === messages.length) {
    return;
  }

  const wasAtBottom = container.scrollHeight - container.scrollTop <= container.clientHeight + 140;

  container.innerHTML = messages.map(m => {
    const isReceptionist = m.sender_role === 'admin';
    let senderLabel = chat.customer_name || 'Buyer';
    if (isReceptionist) {
      senderLabel = 'Larry (Head Dealer & Admin)';
    } else if (m.sender_role === 'seller' || (chat.seller_id && m.sender_id === chat.seller_id)) {
      senderLabel = `${chat.seller_name || 'Seller'}`;
    }

    return `
      <div class="message-row ${isReceptionist ? 'sent' : 'received'}">
        <div class="msg-avatar ${isReceptionist ? 'receptionist-avatar' : 'customer-avatar'}">
          ${isReceptionist ? 'L' : (senderLabel ? senderLabel[0].toUpperCase() : 'U')}
        </div>
        <div class="msg-bubble-wrap">
          <div class="msg-bubble">
            ${escapeHtml(m.message)}
          </div>
          <div class="msg-meta">
            <span class="msg-sender">${escapeHtml(senderLabel)}</span>
            <span>•</span>
            <span class="msg-time">${m.created_at || 'Recently'}</span>
          </div>
        </div>
      </div>
    `;
  }).join('');

  if (forceScroll || wasAtBottom) {
    scrollChatToBottom(container);
  }
}

async function sendAdminMessage() {
  const input = document.getElementById('adminChatInput');
  const btn = document.getElementById('btnAdminSend');
  if (!input || !currentChatId) return;

  const text = input.value.trim();
  if (!text) return;

  const container = document.getElementById('adminMessagesContainer');
  input.value = '';
  if (btn) btn.disabled = true;

  // Optimistic preview for admin desk
  if (container) {
    container.insertAdjacentHTML('beforeend', `
      <div class="message-row sent">
        <div class="msg-avatar receptionist-avatar">L</div>
        <div class="msg-bubble-wrap">
          <div class="msg-bubble">${escapeHtml(text)}</div>
          <div class="msg-meta">
            <span class="msg-sender">Larry (Head Dealer &amp; Admin)</span>
            <span>•</span>
            <span class="msg-time">Just now</span>
          </div>
        </div>
      </div>
    `);
    scrollChatToBottom(container);
  }

  try {
    const res = await fetch(`/api/chats/${currentChatId}/messages`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text })
    });
    if (res.ok) {
      setTimeout(() => {
        loadAdminChatMessages(currentChatId, true);
      }, 100);
      updateAdminSidebarThreadPreview(currentChatId, text);
    }
  } catch (err) {
    console.error('Error sending admin message:', err);
  } finally {
    if (btn) btn.disabled = false;
  }
}

function quickAdminSend(text) {
  const input = document.getElementById('adminChatInput');
  if (input) {
    input.value = text;
    sendAdminMessage();
  }
}

// Load Swap and Sell Requests in Admin
async function loadAdminSwapRequests() {
  const container = document.getElementById('adminSwapTableBody');
  if (!container) return;

  try {
    const res = await fetch('/api/swap-sell');
    const data = await res.json();
    const list = data.requests || [];

    if (list.length === 0) {
      container.innerHTML = `<tr><td colspan="6" style="text-align:center; padding:20px; color:var(--gray-500);">No swap/sell submissions yet.</td></tr>`;
      return;
    }

    container.innerHTML = list.map(r => `
      <tr style="border-bottom:1px solid var(--gray-100);">
        <td style="padding:12px 14px;">
          <span style="font-size:11px; font-weight:700; padding:2px 6px; border-radius:4px; background:var(--gray-100); color:var(--gray-800);">
            ${r.request_type.toUpperCase()}
          </span>
        </td>
        <td style="padding:12px 14px;">
          <strong>${r.user_name}</strong><br>
          <span style="font-size:11px; color:var(--gray-500);">${r.user_phone || r.user_email}</span>
        </td>
        <td style="padding:12px 14px;">
          <strong>${r.car_year} ${r.car_make} ${r.car_model}</strong><br>
          <span style="font-size:11px; color:var(--gray-500);">${Number(r.car_mileage || 0).toLocaleString()} mi • Exp: ${formatMoney(r.expected_price || 0)}</span>
        </td>
        <td style="padding:12px 14px; font-size:13px;">
          ${r.target_car_title ? `<span style="color:var(--gray-800); font-weight:600;">For: ${r.target_car_title}</span>` : '<span style="color:var(--gray-500);">Outright Cash Sale</span>'}
        </td>
        <td style="padding:12px 14px;">
          <span style="font-size:12px; font-weight:600; color:var(--gray-700);">${r.status}</span>
        </td>
        <td style="padding:12px 14px;">
          <div style="display:flex; gap:6px;">
            <button onclick="updateSwapStatus(${r.id}, 'Accepted')" class="btn btn-sm" style="background:var(--gray-100); color:var(--black-deep); padding:4px 8px; font-size:11px;">Accept</button>
            <button onclick="updateSwapStatus(${r.id}, 'Reviewed')" class="btn btn-secondary btn-sm" style="padding:4px 8px; font-size:11px;">Reviewed</button>
          </div>
        </td>
      </tr>
    `).join('');
  } catch (err) {
    console.error('Error loading admin swap list:', err);
  }
}

async function updateSwapStatus(reqId, status) {
  try {
    const res = await fetch(`/api/swap-sell/${reqId}/status`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status })
    });
    if (res.ok) {
      showToast(`Status updated to ${status}`);
      loadAdminSwapRequests();
      loadAdminStats();
    }
  } catch (err) {
    console.error('Status update error:', err);
  }
}

// Modal generic helpers
function openModal(id) {
  const m = document.getElementById(id);
  if (m) m.classList.add('active');
}

function closeModal(id) {
  const m = document.getElementById(id);
  if (m) m.classList.remove('active');
}

function escapeHtml(text) {
  if (!text) return '';
  const div = document.createElement('div');
  div.innerText = text;
  return div.innerHTML;
}

// Enhanced Splash Screen Handler
function initSplashScreen() {
  const splash = document.getElementById('splashScreen');
  if (!splash) return;

  const percentEl = document.getElementById('splashPercent');
  const barEl = document.getElementById('splashBar');
  
  const duration = 1750; // ms
  const startTime = performance.now();

  function updateTelemetry(now) {
    if (splash.classList.contains('fade-out')) return;

    const elapsed = now - startTime;
    const progress = Math.min(elapsed / duration, 1);
    // Easing out cubic curve for natural acceleration & deceleration
    const ease = 1 - Math.pow(1 - progress, 3);
    const percent = Math.floor(ease * 100);

    if (percentEl) percentEl.innerText = `${percent}%`;
    if (barEl) barEl.style.width = `${percent}%`;

    if (progress < 1) {
      requestAnimationFrame(updateTelemetry);
    } else {
      if (percentEl) percentEl.innerText = '100%';
      if (barEl) barEl.style.width = '100%';
      // Brief moment at 100% to view before smooth reveal
      window._splashTimer = setTimeout(() => {
        dismissSplashScreen();
      }, 350);
    }
  }

  requestAnimationFrame(updateTelemetry);
}

function dismissSplashScreen() {
  const splash = document.getElementById('splashScreen');
  if (!splash || splash.classList.contains('fade-out')) return;

  if (window._splashTimer) {
    clearTimeout(window._splashTimer);
  }

  splash.classList.add('fade-out');
  setTimeout(() => {
    if (splash.parentNode) {
      splash.parentNode.removeChild(splash);
    }
    checkAndPromptNotificationPermission();
  }, 750);
}

// Global initialization
document.addEventListener('DOMContentLoaded', () => {
  registerServiceWorker();
  initSplashScreen();
  checkAuthStatus();

  // If page does not have a splash screen (e.g. subpages), prompt after short delay
  if (!document.getElementById('splashScreen')) {
    setTimeout(() => {
      checkAndPromptNotificationPermission();
    }, 1200);
  }

  if (document.getElementById('carsGrid')) {
    loadCars();
    setupFilterListeners();
  }

  const params = new URLSearchParams(window.location.search);
  if (params.get('open_auth')) {
    openAuthModal(params.get('open_auth'));
  }
});
