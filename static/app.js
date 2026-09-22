'use strict';
const $ = (selector) => document.querySelector(selector);
const driveDashboard = $('#drive-dashboard');
const driveMain = driveDashboard?.querySelector('.drive-main');
const driveLocation = driveDashboard?.querySelector('.drive-location');
const driveAttitude = driveDashboard?.querySelector('.drive-secondary');
const driveHealth = driveDashboard?.querySelector('.drive-health');
const driveSuspension = driveDashboard?.querySelector('.drive-suspension');

// Location starts inside the powertrain markup for the compact layout.  On the
// Drive dashboard it belongs beside the attitude instrument instead, so both
// circular instruments can share that one panel footprint.
if (driveLocation && driveAttitude) driveAttitude.after(driveLocation);

// The Pi layout gives rear air pressure a dedicated card beside the primary
// gauges. Narrow layouts keep the same card in Vehicle Performance so the
// dashboard continues to stack without introducing implicit grid columns.
const wideDriverLayout = window.matchMedia('(min-width: 901px)');
function placeDriveSuspension() {
  if (!driveMain || !driveHealth || !driveSuspension) return;
  if (wideDriverLayout.matches) driveMain.after(driveSuspension);
  else driveHealth.append(driveSuspension);
}
placeDriveSuspension();
wideDriverLayout.addEventListener?.('change', placeDriveSuspension);

const launchParameters = new URLSearchParams(window.location.search);
let eventHoldUntil = 0;
function showEvent(message, holdMilliseconds = 0) {
  $('#event').textContent = message;
  eventHoldUntil = holdMilliseconds ? Date.now() + holdMilliseconds : 0;
}
window.dashboardEvent = showEvent;

// The Pi launcher marks only the initial boot window as a startup. Window-mode
// relaunches deliberately omit this flag so the welcome voice does not repeat.
if (launchParameters.get('startup') === '1') {
  const startupVoice = new Audio('/media/audio/voice/OVRLand-Start.wav');
  startupVoice.preload = 'auto';
  startupVoice.play().catch(() => {
    // Audio must never prevent the instrument panel from starting. The kiosk
    // launcher permits autoplay, while other browsers may require interaction.
  });
}
const systemTab = document.querySelector('nav button[data-mode="camp"]');
const musicTab = document.createElement('button');
musicTab.dataset.mode = 'music';
musicTab.setAttribute('aria-pressed', 'false');
musicTab.innerHTML = '<span>03</span> OVRadio';
systemTab.querySelector('span').textContent = '04';
systemTab.before(musicTab);
const musicDashboard = document.createElement('section');
musicDashboard.id = 'music-dashboard';
musicDashboard.className = 'music-dashboard panel';
musicDashboard.setAttribute('aria-label', 'Music sources');
musicDashboard.hidden = true;
musicDashboard.innerHTML = '<section class="music-portal cliamp-portal"><span class="label" data-music="preset">CURATED RADIO / CLIAMP</span><span class="music-station" data-music="station" hidden></span><strong data-music="title">—</strong><span data-music="artist">—</span><div class="music-spectrum" data-music="spectrum" aria-label="CLIAMP live 10-band spectrum"></div><div class="music-progress"><span data-music="state">STARTING</span><span data-music="position">—</span></div><div class="music-settings"><span>VOL <b data-music="volume">—</b></span><span>SHUFFLE <b data-music="shuffle">—</b></span><span>REPEAT <b data-music="repeat">—</b></span></div><small data-music="availability">OVRLAND PLAYER · STARTING…</small></section><section class="music-portal spotify-portal"><span class="label">OPTIONAL SOURCE</span><strong>SPOTIFY</strong><span>Account-based streaming</span><small>PLAYER NOT CONFIGURED</small></section><div class="music-hint">DOWN: SOURCE · PRESS: OPEN<br><span>Curated internet radio uses CLIAMP. Spotify remains a separate optional source.</span></div>';
musicDashboard.querySelector('[data-music="spectrum"]').replaceChildren(...Array.from({length: 10}, (_, index) => {
  const bar = document.createElement('i');
  bar.dataset.band = String(index);
  return bar;
}));
$('#camp-dashboard').before(musicDashboard);
const modeButtons = [...document.querySelectorAll('nav button')];
const modes = {
  drive: ['DRIVE / PERFORMANCE', 'POWERTRAIN / VEHICLE TELEMETRY'],
  adventure: ['ADVENTURE / FIELD INSTRUMENTS', 'TERRAIN / WEATHER / DAYLIGHT'],
  music: ['MUSIC / AUDIO', 'CURATED RADIO / SPOTIFY'],
  camp: ['SYSTEM / POWER CONTROLS', 'STOP OVRLAND OR POWER OFF THE PI'],
};
let focusIndex = 0;
let focusTargetIndex = -1;
let sectionLayerIndex = 0;
let navigationLayer = 'tabs';
let calibration = (() => {
  try {
    const saved = JSON.parse(localStorage.getItem('ovrland.attitudeCalibration') || 'null');
    return Number.isFinite(saved?.pitch) && Number.isFinite(saved?.roll)
      ? {pitch: saved.pitch, roll: saved.roll, active: true}
      : {pitch: 0, roll: 0, active: false};
  } catch { return {pitch: 0, roll: 0, active: false}; }
})();
const sectionTargets = {
  drive: [
    ['rpm', '.rpm-gauge', 'ENGINE RPM'], ['speed', '.speed-gauge', 'SPEED'],
    ['health', '.drive-health', 'VEHICLE PERFORMANCE'], ['diagnostics', '.drive-summary', 'DIAGNOSTICS'],
    ['suspension', '.drive-suspension', 'AIR SUSPENSION'],
    ['map', '.map-panel', 'MAP'], ['attitude', '.drive-secondary', 'TILT-OH-SHIT! METER'],
  ],
  adventure: [
    ['location', '.adventure-info', 'LOCATION / AWARENESS'], ['map', '.map-panel', 'MAP'],
    ['conditions', '.adventure-secondary', 'FIELD CONDITIONS'], ['compass', '.trail-compass', 'COMPASS / HEADING'],
    ['attitude', '.trail-attitude', 'TILT-OH-SHIT! METER'],
    ['suspension', '.adventure-suspension', 'AIR SUSPENSION'],
  ],
  music: [
    ['cliamp', '.cliamp-portal', 'CURATED RADIO'],
    ['spotify', '.spotify-portal', 'SPOTIFY'],
  ],
  camp: [
    ['stop-app', '[data-system-action="stop-app"]', 'STOP APP'],
    ['poweroff-pi', '[data-system-action="poweroff-pi"]', 'POWER OFF PI'],
  ],
};
// X moves across the visible row. Y moves through the dashboard's vertical
// layers before it reaches the footer / Camp Mode control.
const sectionLayers = {
  drive: [
    ['rpm', 'speed', 'health', 'diagnostics', 'suspension'],
    ['map', 'attitude'],
  ],
  adventure: [
    ['location', 'conditions'],
    ['map', 'compass', 'attitude', 'suspension'],
  ],
  music: [['cliamp', 'spotify']],
  camp: [['stop-app', 'poweroff-pi']],
};
const footerTargets = [
  ['fullscreen', '#fullscreen', 'CAMP MODE'],
];
function activeSections() { return sectionTargets[$('body').dataset.mode] ?? []; }
function activeSectionLayers() {
  const targets = activeSections();
  const layers = sectionLayers[$('body').dataset.mode] ?? [targets.map(target => target[0])];
  return layers.map(keys => keys.map(key => targets.find(target => target[0] === key)).filter(Boolean));
}
function activeSectionLayer() { return activeSectionLayers()[sectionLayerIndex] ?? []; }
function focusedLayerIndex() {
  return activeSectionLayer().indexOf(activeSections()[focusTargetIndex]);
}
function clearJoystickFocus() {
  modeButtons.forEach(button => button.classList.remove('joy-focus'));
  document.querySelectorAll('.joy-section-focus, .joy-footer-focus')
    .forEach(item => item.classList.remove('joy-section-focus', 'joy-footer-focus'));
}
function setLayerFocus(index, layerIndex = sectionLayerIndex) {
  navigationLayer = 'sections';
  const layers = activeSectionLayers();
  sectionLayerIndex = Math.max(0, Math.min(layerIndex, layers.length - 1));
  const targets = activeSectionLayer();
  const target = targets.length ? targets[(index + targets.length) % targets.length] : null;
  focusTargetIndex = target ? activeSections().indexOf(target) : -1;
  // The tab outline belongs only to the upper navigation layer. Clear it as
  // soon as DOWN enters module navigation so the visible focus follows the
  // joystick layer.
  clearJoystickFocus();
  if (target) $(target[1])?.classList.add('joy-section-focus');
  if (target) $('#event').textContent = `FOCUS / ${target[2]} — PRESS TO OPEN DETAIL`;
}
function setSectionFocus(index) {
  const target = activeSections()[index];
  const layers = activeSectionLayers();
  const layerIndex = layers.findIndex(layer => layer.includes(target));
  const targetIndex = layerIndex < 0 ? 0 : layers[layerIndex].indexOf(target);
  setLayerFocus(targetIndex, layerIndex < 0 ? 0 : layerIndex);
}
function setFooterFocus(index = 0) {
  navigationLayer = 'footer';
  const target = footerTargets[(index + footerTargets.length) % footerTargets.length];
  clearJoystickFocus();
  $(target[1])?.classList.add('joy-footer-focus');
  $('#event').textContent = `FOCUS / ${target[2]} — PRESS TO TOGGLE`;
}
function focusMode(index) {
  navigationLayer = 'tabs';
  sectionLayerIndex = 0;
  focusIndex = (index + modeButtons.length) % modeButtons.length;
  clearJoystickFocus();
  modeButtons.forEach((button, i) => button.classList.toggle('joy-focus', i === focusIndex));
}
for (const [i, button] of modeButtons.entries()) {
  button.addEventListener('click', () => {
    document.body.dataset.mode = button.dataset.mode;
    focusMode(i);
    for (const item of modeButtons) {
      item.classList.toggle('active', item === button);
      item.setAttribute('aria-pressed', String(item === button));
    }
    ['#screen-title', '#mode-caption'].forEach((id, j) => $(id).textContent = modes[button.dataset.mode][j]);
    for (const mode of Object.keys(modes)) $(`#${mode}-dashboard`).hidden = mode !== button.dataset.mode;
    $('#workspace').hidden = ['camp', 'music'].includes(button.dataset.mode);
    document.querySelectorAll('.joy-section-focus, .joy-footer-focus')
      .forEach(item => item.classList.remove('joy-section-focus', 'joy-footer-focus'));
    window.dashboardMap?.resize();
    window.navball?.refresh();
  });
}
const launchedWindowMode = launchParameters.get('window');
if (launchedWindowMode === 'camp') {
  $('#fullscreen').textContent = '⛶ FULL SCREEN';
  footerTargets[0][2] = 'FULL SCREEN';
  const campWarning = document.createElement('div');
  campWarning.setAttribute('role', 'alert');
  campWarning.setAttribute('aria-live', 'assertive');
  campWarning.innerHTML = '<strong>WARNING</strong><span>CO-PILOT USE ONLY</span>';
  Object.assign(campWarning.style, {
    position: 'fixed', inset: '0', zIndex: '2000', display: 'flex',
    flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
    gap: '18px', color: '#fff3df', background: '#160906ed',
    border: '12px solid #d94b2b', boxSizing: 'border-box', textAlign: 'center',
    letterSpacing: '5px',
  });
  campWarning.querySelector('strong').style.cssText =
    'color:#ff6c45;font-size:clamp(34px,8vw,92px)';
  campWarning.querySelector('span').style.cssText =
    'font:900 clamp(22px,5vw,58px) monospace';
  document.body.append(campWarning);

  const exitVoice = new Audio('/media/audio/voice/OVRLand-Fullscreen-Exit.wav');
  let warningTimeout = null;
  const clearCampWarning = () => {
    campWarning.remove();
    if (warningTimeout !== null) window.clearTimeout(warningTimeout);
    warningTimeout = null;
  };
  exitVoice.preload = 'auto';
  exitVoice.addEventListener('ended', clearCampWarning, {once: true});
  exitVoice.addEventListener('error', clearCampWarning, {once: true});
  // The normal path clears the warning precisely when playback ends. This
  // failsafe prevents a stalled media pipeline from leaving it on screen.
  warningTimeout = window.setTimeout(clearCampWarning, 30000);
  exitVoice.play().catch(clearCampWarning);
}
$('#fullscreen').addEventListener('click', async () => {
  const requestedMode = launchedWindowMode === 'camp' ? 'fullscreen' : 'camp';
  try {
    const response = await fetch(`/api/window-mode/${requestedMode}`, {method: 'POST'});
    if (!response.ok) throw new Error('Window mode unavailable');
    $('#fullscreen').disabled = true;
    showEvent(requestedMode === 'camp'
      ? 'OPENING CAMP MODE — returning OVRLand to a desktop window…'
      : 'RETURNING TO FULL SCREEN…', 5000);
  } catch { showEvent('Window mode unavailable. Press Alt+F4 to return to the desktop.', 5000); }
});
let lastReceived = 0;
let joySession = null;
let lastEvent = 0;
let movedDetailNode = null;
let detailRestore = null;
let detailNavballCleanup = null;
let detailModuleKey = null;
let systemHoldAction = null;
let systemHoldStartedAt = null;
let detailControlIndex = 0;
let musicStreams = [];
let musicStreamsLoading = false;
let musicStreamsError = '';
function joystick(data) {
  const meta = data.nano;
  const joy = data.joystick;
  $('#joy-status').textContent = meta?.status?.toUpperCase() ?? 'DEMO';
  $('#joy-button').textContent = joy ? (joy.pressed ? 'PRESSED' : 'RELEASED') : '—';
  if (!joy || meta?.status !== 'live' || document.hidden) {
    joySession = null;
    return;
  }
  const now = performance.now();
  if (systemHoldAction && joy.pressed && systemHoldStartedAt !== null && now - systemHoldStartedAt >= 2000) {
    const action = systemHoldAction;
    systemHoldAction = null;
    systemHoldStartedAt = null;
    runSystemAction(action);
  }
  if (systemHoldAction && !joy.pressed) {
    systemHoldAction = null;
    systemHoldStartedAt = null;
    $('#system-status').textContent = 'SYSTEM STANDBY';
  }
  if (meta.session !== joySession) {
    joySession = meta.session;
    lastEvent = meta.event_id;
    focusMode(modeButtons.findIndex(button => button.classList.contains('active')));
    return;
  }
  for (const event of meta.events) {
    if (event.id <= lastEvent) continue;
    lastEvent = event.id;
    const detailOpen = !$('#detail-overlay').hidden;
    if (detailOpen && (event.action === 'left' || event.action === 'right')) {
      setDetailFocus(detailControlIndex + (event.action === 'left' ? -1 : 1));
    } else if (detailOpen && event.action === 'up') {
      const backIndex = activeDetailControls().findIndex(control =>
        control.key === 'back' || control.key === 'music-player-back');
      if (backIndex >= 0) setDetailFocus(backIndex);
    } else if (!detailOpen && (event.action === 'left' || event.action === 'right')) {
      const direction = event.action === 'left' ? -1 : 1;
      if (navigationLayer === 'tabs') focusMode(focusIndex + direction);
      else if (navigationLayer === 'sections' && activeSectionLayer().length) {
        setLayerFocus(focusedLayerIndex() + direction);
      }
    }
    if (!detailOpen && event.action === 'down' && navigationLayer === 'tabs') setLayerFocus(0, 0);
    else if (!detailOpen && event.action === 'down' && navigationLayer === 'sections') {
      const layers = activeSectionLayers();
      if (sectionLayerIndex < layers.length - 1) setLayerFocus(0, sectionLayerIndex + 1);
      else setFooterFocus();
    }
    else if (!detailOpen && event.action === 'up' && navigationLayer === 'footer') {
      const layers = activeSectionLayers();
      setLayerFocus(0, layers.length - 1);
    } else if (!detailOpen && event.action === 'up' && navigationLayer === 'sections') {
      if (sectionLayerIndex > 0) setLayerFocus(0, sectionLayerIndex - 1);
      else {
        focusMode(focusIndex);
        showEvent('TAB FOCUS — PRESS TO SELECT OR DOWN TO RETURN TO CONTENT', 3000);
      }
    }
    if (event.action === 'select') {
      if (detailOpen) activateDetailControl();
      else if (navigationLayer === 'tabs') modeButtons[focusIndex].click();
      else if (navigationLayer === 'footer') $(footerTargets[0][1])?.click();
      else if ($('body').dataset.mode === 'camp') {
        systemHoldAction = activeSections()[focusTargetIndex]?.[0] ?? null;
        systemHoldStartedAt = systemHoldAction ? now : null;
        if (systemHoldAction) $('#system-status').textContent = 'HOLD BUTTON FOR 2 SECONDS TO CONFIRM';
      } else openDetail(activeSections()[focusTargetIndex]?.[0]);
    }
  }
}
function focusedModule() {
  const target = activeSections()[focusTargetIndex];
  return target ? {key: target[0], selector: target[1], title: target[2]} : null;
}
function activeDetailControls() {
  if (detailModuleKey === 'cliamp') return [
    {key: 'music-prev', label: 'PREVIOUS'},
    {key: 'music-toggle', label: 'PLAY / PAUSE'},
    {key: 'music-next', label: 'NEXT'},
    {key: 'music-streams', label: 'CURATED RADIO'},
    {key: 'music-volume-down', label: 'VOLUME −'},
    {key: 'music-volume-up', label: 'VOLUME +'},
    {key: 'music-shuffle', label: 'SHUFFLE'},
    {key: 'music-repeat', label: 'REPEAT'},
    {key: 'music-stop', label: 'STOP'},
    {key: 'back', label: 'BACK TO DASHBOARD'},
  ];
  if (detailModuleKey === 'cliamp-streams') {
    const controls = musicStreams.map((stream, index) => ({
      key: `music-stream-${index}`,
      label: stream.display_name.toUpperCase(),
      description: `${stream.station_name} · ${stream.provider} — ${stream.description}`,
    }));
    if (!musicStreamsLoading && !controls.length) {
      controls.push({key: 'music-streams-refresh', label: musicStreamsError ? 'RETRY RADIO LIST' : 'NO STATIONS — RETRY'});
    }
    controls.push({key: 'music-player-back', label: musicStreamsLoading ? 'LOADING RADIO… / BACK' : 'BACK TO PLAYER'});
    return controls;
  }
  if (detailModuleKey === 'attitude') return [
    {key: 'calibrate', label: 'CALIBRATE LEVEL'},
    {key: 'back', label: 'BACK TO DASHBOARD'},
  ];
  if (detailModuleKey === 'calibration') {
    const attitude = window.latestTelemetry?.attitude;
    const controls = [];
    if (Number.isFinite(attitude?.pitch_deg) && Number.isFinite(attitude?.roll_deg)) {
      controls.push({key: 'set-level', label: 'SET CURRENT POSITION AS LEVEL'});
    }
    controls.push({key: 'back', label: 'CANCEL'});
    return controls;
  }
  if (detailModuleKey !== 'map') return [{key: 'back', label: 'BACK TO DASHBOARD'}];
  const controls = [
    {key: 'osm', label: 'OPENSTREETMAP'},
    {key: 'gaia', label: 'GAIA'},
    {key: 'earth', label: 'EARTH / DISCOVERY'},
    {key: 'offline', label: 'OFFLINE'},
  ];
  if (window.dashboardMap?.canCenter?.()) controls.push({key: 'center', label: 'CENTER GPS'});
  controls.push({key: 'back', label: 'BACK TO DASHBOARD'});
  return controls;
}
function renderDetailControls(initialKey) {
  const controls = activeDetailControls();
  const container = $('#detail-controls');
  container.replaceChildren(...controls.map(control => {
    const button = document.createElement('button');
    button.type = 'button';
    button.dataset.detailControl = control.key;
    button.textContent = control.label;
    if (control.description) {
      button.title = control.description;
      button.setAttribute('aria-label', `${control.label}: ${control.description}`);
    }
    button.addEventListener('click', () => activateDetailControl(control.key));
    return button;
  }));
  const initialIndex = controls.findIndex(control => control.key === initialKey);
  setDetailFocus(initialIndex >= 0 ? initialIndex : 0);
}
function setDetailFocus(index) {
  const controls = activeDetailControls();
  detailControlIndex = controls.length ? (index + controls.length) % controls.length : -1;
  document.querySelectorAll('.joy-detail-focus').forEach(item => item.classList.remove('joy-detail-focus'));
  const control = controls[detailControlIndex];
  const button = control && $(`[data-detail-control="${control.key}"]`);
  button?.classList.add('joy-detail-focus');
  if (control) $('#event').textContent = `FOCUS / ${control.label} — PRESS TO SELECT`;
}
function activateDetailControl(key = activeDetailControls()[detailControlIndex]?.key) {
  if (key === 'back') {
    closeDetail();
    return;
  }
  if (key === 'center') {
    window.dashboardMap?.center?.();
    renderDetailControls('center');
    return;
  }
  if (key === 'calibrate') {
    openCalibration();
    return;
  }
  if (key === 'set-level') {
    if (!applyCurrentCalibration()) return;
    closeDetail();
    showEvent('LEVEL CALIBRATION ACTIVE — navball display zeroed to the saved reference.', 5000);
    return;
  }
  if (key === 'music-streams' || key === 'music-streams-refresh') {
    openMusicStreams();
    return;
  }
  if (key === 'music-player-back') {
    detailModuleKey = 'cliamp';
    $('#detail-title').textContent = 'CURATED RADIO';
    renderDetailControls('music-streams');
    return;
  }
  if (key?.startsWith('music-stream-')) {
    const index = Number(key.slice('music-stream-'.length));
    if (Number.isInteger(index) && musicStreams[index]) selectMusicStream(musicStreams[index]);
    return;
  }
  if (key?.startsWith('music-')) {
    runMusicAction(key.replace('music-', ''));
    return;
  }
  if (['osm', 'gaia', 'earth', 'offline'].includes(key)) {
    window.dashboardMap?.choose?.(key);
    renderDetailControls(key);
  }
}
function applyCurrentCalibration() {
  const rawPitch = wholeDegree(window.latestTelemetry?.attitude?.pitch_deg);
  const rawRoll = wholeDegree(window.latestTelemetry?.attitude?.roll_deg);
  if (rawPitch === null || rawRoll === null) return false;
  calibration = {pitch: rawPitch, roll: rawRoll, active: true};
  try { localStorage.setItem('ovrland.attitudeCalibration', JSON.stringify(calibration)); } catch {}
  document.querySelectorAll('[data-value="attitude.pitch_deg"]').forEach(field => { field.textContent = '0'; });
  document.querySelectorAll('[data-value="attitude.roll_deg"]').forEach(field => { field.textContent = '0'; });
  window.navball?.update(0, 0);
  return true;
}
function openDetail(key) {
  const module = focusedModule();
  if (!module || module.key !== key) return;
  const dashboard = $(`#${$('body').dataset.mode}-dashboard`);
  const panel = module.key === 'map' ? $('.map-panel')
    : $('body').dataset.mode === 'camp' ? $(module.selector) : dashboard?.querySelector(module.selector);
  if (!panel) return;
  detailRestore = {parent: panel.parentElement, next: panel.nextSibling};
  panel.classList.add('detail-module-panel');
  $('#detail-kicker').textContent = $('body').dataset.mode.toUpperCase();
  $('#detail-title').textContent = module.title;
  $('#detail-body').replaceChildren(panel);
  movedDetailNode = panel;
  detailModuleKey = key;
  document.body.classList.add('detail-module-open');
  if (key === 'map') document.body.classList.add('detail-map-open');
  if (key === 'attitude') {
    const ball = panel.querySelector('canvas.navball');
    if (ball) {
      let held = false;
      let timer = null;
      const start = () => {
        held = false;
        timer = window.setTimeout(() => {
          held = true;
          openCalibration();
        }, 700);
      };
      const end = () => {
        if (timer) window.clearTimeout(timer);
        timer = null;
        if (!held && !$('#detail-overlay').hidden) closeDetail();
      };
      ball.addEventListener('pointerdown', start);
      ball.addEventListener('pointerup', end);
      ball.addEventListener('pointercancel', end);
      detailNavballCleanup = () => {
        if (timer) window.clearTimeout(timer);
        ball.removeEventListener('pointerdown', start);
        ball.removeEventListener('pointerup', end);
        ball.removeEventListener('pointercancel', end);
        detailNavballCleanup = null;
      };
    }
  }
  $('#detail-overlay').hidden = false; document.body.classList.add('detail-open');
  renderDetailControls(key === 'map' ? window.dashboardMap?.source?.()
    : key === 'attitude' ? 'calibrate' : key === 'cliamp' ? 'music-toggle' : 'back');
  requestAnimationFrame(() => {
    window.dashboardMap?.resize();
    window.navball?.refresh();
  });
}
function closeDetail() {
  detailNavballCleanup?.();
  if (movedDetailNode && detailRestore) {
    const wasMap = Boolean(movedDetailNode.querySelector('#street-map'));
    movedDetailNode.classList.remove('detail-module-panel');
    detailRestore.parent.insertBefore(movedDetailNode, detailRestore.next);
    movedDetailNode = null;
    detailRestore = null;
    if (wasMap) window.dashboardMap?.restoreDashboard?.();
    window.dashboardMap?.resize();
  }
  document.body.classList.remove('detail-map-open');
  document.body.classList.remove('detail-module-open');
  $('#detail-overlay').hidden = true;
  document.body.classList.remove('detail-open');
  $('#detail-body').replaceChildren();
  $('#detail-controls').replaceChildren();
  detailModuleKey = null;
  detailControlIndex = 0;
  if (navigationLayer === 'sections' && focusTargetIndex >= 0) setSectionFocus(focusTargetIndex);
}
function openCalibration() {
  const rawPitch = wholeDegree(window.latestTelemetry?.attitude?.pitch_deg);
  const rawRoll = wholeDegree(window.latestTelemetry?.attitude?.roll_deg);
  const pitch = rawPitch === null ? null : wholeDegree(rawPitch - calibration.pitch);
  const roll = rawRoll === null ? null : wholeDegree(rawRoll - calibration.roll);
  $('#detail-kicker').textContent = 'TILT-OH-SHIT! SETUP';
  $('#detail-title').textContent = 'CALIBRATE LEVEL';
  const availability = pitch === null || roll === null
    ? '<p class="calibration-note">Attitude telemetry is unavailable. Calibration can be set when pitch and roll readings return.</p>'
    : '<p class="calibration-note">This applies a display zero offset only. Raw sensor telemetry is unchanged.</p>';
  $('#detail-body').innerHTML = `<div class="calibration-ball">NAVBALL</div><p>Park the vehicle on the level reference you want to use. The current attitude is <strong>${pitch ?? '—'}° pitch / ${roll ?? '—'}° roll</strong>.</p>${availability}`;
  detailModuleKey = 'calibration';
  $('#detail-overlay').hidden = false; document.body.classList.add('detail-open');
  renderDetailControls(pitch === null || roll === null ? 'back' : 'set-level');
}
$('#detail-close').addEventListener('click', closeDetail);
document.querySelectorAll('.suspension-card').forEach(card => {
  card.addEventListener('click', () => {
    if (!$('#detail-overlay').hidden) return;
    const index = activeSections().findIndex(target => target[0] === 'suspension');
    if (index < 0) return;
    setSectionFocus(index);
    openDetail('suspension');
  });
});
$('#detail-overlay').addEventListener('click', event => { if (event.target.id === 'detail-overlay') closeDetail(); });
$('#detail-overlay').addEventListener('dblclick', event => {
  if (event.target.closest?.('canvas.navball')) return;
  closeDetail();
});
async function runSystemAction(action) {
  const button = document.querySelector(`[data-system-action="${action}"]`);
  const status = $('#system-status');
  if (!button || button.disabled) return;
  button.disabled = true;
  status.textContent = action === 'poweroff-pi' ? 'POWERING OFF PI…' : 'STOPPING OVRLAND…';
  try {
    const response = await fetch(`/api/system/${action}`, {method: 'POST'});
    if (response.status === 403) {
      button.disabled = false;
      status.textContent = 'SYSTEM CONTROLS REQUIRE THE LOCAL DASHBOARD ON THE PI';
      return;
    }
    if (!response.ok) throw new Error('System action unavailable');
    const result = await response.json();
    if (result.status === 'simulated') {
      button.disabled = false;
      status.textContent = `${action === 'poweroff-pi' ? 'POWER OFF' : 'STOP APP'} SIMULATED — MOCK MODE`;
      return;
    }
    if (action === 'stop-app') {
      // The launcher also watches the service and closes kiosk Chromium as a
      // fallback. This gives touch users an immediate return to the desktop.
      window.close();
    }
  } catch {
    button.disabled = false;
    status.textContent = 'ACTION FAILED — CHECK APP SERVICE';
  }
}
for (const button of document.querySelectorAll('[data-system-action]')) {
  let holdTimer = null;
  const status = $('#system-status');
  const cancel = () => {
    if (holdTimer) window.clearTimeout(holdTimer);
    holdTimer = null;
    if (!button.disabled) status.textContent = 'SYSTEM STANDBY';
  };
  button.addEventListener('pointerdown', () => {
    status.textContent = 'HOLDING — KEEP PRESSED FOR 2 SECONDS';
    holdTimer = window.setTimeout(() => {
      holdTimer = null;
      runSystemAction(button.dataset.systemAction);
    }, 2000);
  });
  button.addEventListener('pointerup', cancel);
  button.addEventListener('pointercancel', cancel);
  button.addEventListener('pointerleave', cancel);
}
function formatAmbientLightReading(current) {
  if (!current?.available) return `NANO / ${(current?.nano_status || 'UNAVAILABLE').toUpperCase()} — RGB NOT READY`;
  const rgb = current.rgb.map(value => Number.isFinite(value) ? String(Math.round(value)) : '—').join(' / ');
  return `RGB ${rgb} · RELATIVE BRIGHTNESS ${current.brightness_raw}`;
}
function renderAmbientLightCalibration(result) {
  $('#ambient-light-reading').textContent = formatAmbientLightReading(result?.current);
  const entries = Array.isArray(result?.entries) ? result.entries.slice(-12).reverse() : [];
  const log = $('#ambient-calibration-log');
  log.replaceChildren(...(entries.length ? entries.map(entry => {
    const item = document.createElement('li');
    const recordedAt = new Date(entry.timestamp);
    const timestamp = Number.isNaN(recordedAt.valueOf()) ? 'UNKNOWN TIME' : recordedAt.toLocaleString([], {
      month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false,
    });
    const rgb = Array.isArray(entry.rgb) ? entry.rgb.join(' / ') : '—';
    item.innerHTML = `<b>${String(entry.condition || 'unknown').toUpperCase()}</b>${timestamp}<br>RGB ${rgb} · ${entry.brightness_raw ?? '—'}`;
    return item;
  }) : [Object.assign(document.createElement('li'), {textContent: 'No captured references yet.'})]));
}
async function refreshAmbientLightCalibration() {
  try {
    const response = await fetch('/api/ambient-light/calibration');
    if (!response.ok) throw new Error('Ambient calibration unavailable');
    renderAmbientLightCalibration(await response.json());
  } catch {
    renderAmbientLightCalibration({current: {available: false, nano_status: 'unavailable'}, entries: []});
  }
}
async function captureAmbientLightCalibration(condition) {
  const buttons = [...document.querySelectorAll('[data-ambient-capture]')];
  buttons.forEach(button => { button.disabled = true; });
  showEvent(`AMBIENT / CAPTURING ${condition.toUpperCase()} REFERENCE…`);
  try {
    const response = await fetch(`/api/ambient-light/calibration/${condition}`, {method: 'POST'});
    const result = await response.json();
    if (response.status === 403) throw new Error('Capture requires the local dashboard on the Pi');
    if (!response.ok) throw new Error(result.error || 'Ambient capture unavailable');
    renderAmbientLightCalibration(result);
    showEvent(`AMBIENT / ${condition.toUpperCase()} REFERENCE SAVED`, 4000);
  } catch (error) {
    showEvent(`AMBIENT / ${(error.message || 'CAPTURE FAILED').toUpperCase()}`, 5000);
    await refreshAmbientLightCalibration();
  } finally {
    buttons.forEach(button => { button.disabled = false; });
  }
}
document.querySelectorAll('[data-ambient-capture]').forEach(button => {
  button.addEventListener('click', () => captureAmbientLightCalibration(button.dataset.ambientCapture));
});
document.addEventListener('keydown', event => {
  if (event.key !== 'Escape') return;
  if (!$('#detail-overlay').hidden) closeDetail();
  else if (navigationLayer === 'footer') setSectionFocus(focusTargetIndex);
  else if (navigationLayer === 'sections') focusMode(focusIndex);
});
window.openDetail = openDetail;
window.openCalibration = openCalibration;
function formatMusicTime(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) return '—';
  return `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`;
}
function renderMusic(data) {
  const ready = Boolean(data?.ok);
  const preset = data?.preset;
  const station = musicDashboard.querySelector('[data-music="station"]');
  musicDashboard.querySelector('[data-music="preset"]').textContent = preset
    ? preset.display_name.toUpperCase() : 'CURATED RADIO / CLIAMP';
  station.textContent = preset ? `${preset.station_name} · ${preset.provider}` : '';
  station.hidden = !preset;
  musicDashboard.querySelector('[data-music="availability"]').textContent = ready ? 'CLIAMP CONNECTED · OVRLAND MANAGED'
    : (data?.status === 'not_installed' ? 'CLIAMP NOT INSTALLED' : 'CLIAMP NOT RUNNING');
  musicDashboard.querySelector('[data-music="state"]').textContent = ready ? (data.state || 'stopped').toUpperCase() : 'UNAVAILABLE';
  musicDashboard.querySelector('[data-music="title"]').textContent = data?.track?.stream_title || data?.track?.title || '—';
  musicDashboard.querySelector('[data-music="artist"]').textContent = data?.track?.artist || data?.track?.station || '—';
  musicDashboard.querySelector('[data-music="position"]').textContent = data?.track?.realtime ? 'LIVE' : formatMusicTime(data?.position);
  musicDashboard.querySelector('[data-music="volume"]').textContent = Number.isFinite(data?.volume)
    ? `${data.volume > 0 ? '+' : ''}${Math.round(data.volume)} dB` : '—';
  musicDashboard.querySelector('[data-music="shuffle"]').textContent = ready
    ? (data.shuffle ? 'ON' : 'OFF') : '—';
  musicDashboard.querySelector('[data-music="repeat"]').textContent = ready
    ? String(data.repeat || 'off').toUpperCase() : '—';
}
async function refreshMusic() {
  try {
    const response = await fetch('/api/music/status');
    renderMusic(await response.json());
  } catch { renderMusic({ok: false}); }
}
async function refreshMusicSpectrum() {
  if ($('body').dataset.mode !== 'music') return;
  try {
    const response = await fetch('/api/music/spectrum');
    const data = await response.json();
    if (!response.ok || !data.ok) throw new Error('Spectrum unavailable');
    musicDashboard.querySelectorAll('[data-band]').forEach((bar, index) => {
      bar.style.setProperty('--level', String(data.bands[index] || 0));
    });
  } catch {
    musicDashboard.querySelectorAll('[data-band]').forEach(bar => bar.style.setProperty('--level', '0'));
  }
}
async function openMusicStreams() {
  detailModuleKey = 'cliamp-streams';
  musicStreams = [];
  musicStreamsError = '';
  musicStreamsLoading = true;
  $('#detail-title').textContent = 'CURATED RADIO';
  renderDetailControls('music-player-back');
  showEvent('CLIAMP / LOADING CURATED STATIONS…');
  try {
    const response = await fetch('/api/music/streams');
    const result = await response.json();
    if (!response.ok || !result.ok || !Array.isArray(result.streams)) {
      throw new Error(result.error || 'Curated stations unavailable');
    }
    musicStreams = result.streams;
    showEvent(musicStreams.length
      ? 'CLIAMP / CHOOSE A CURATED STATION AND PRESS TO PLAY'
      : 'CLIAMP / NO CURATED STATIONS RETURNED', 4000);
  } catch (error) {
    musicStreamsError = error.message || 'Curated stations unavailable';
    showEvent(`CLIAMP / ${musicStreamsError.toUpperCase()}`, 5000);
  } finally {
    musicStreamsLoading = false;
    if (detailModuleKey === 'cliamp-streams') renderDetailControls(musicStreams.length ? 'music-stream-0' : 'music-streams-refresh');
  }
}
async function selectMusicStream(stream) {
  try {
    showEvent(`CLIAMP / TUNING ${stream.display_name.toUpperCase()}…`);
    const response = await fetch('/api/music/stream', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({id: stream.id}),
    });
    const result = await response.json();
    if (!response.ok || !result.ok) throw new Error(result.error || 'Station unavailable');
    detailModuleKey = 'cliamp';
    $('#detail-title').textContent = 'CURATED RADIO';
    renderDetailControls('music-toggle');
    showEvent(`CLIAMP / PLAYING ${stream.display_name.toUpperCase()} · ${stream.station_name.toUpperCase()} / ${stream.provider.toUpperCase()}`, 4000);
    window.setTimeout(refreshMusic, 250);
  } catch (error) {
    showEvent((error.message || 'STREAM UNAVAILABLE — Check network connection.').toUpperCase(), 5000);
  }
}
async function runMusicAction(action) {
  try {
    const response = await fetch(`/api/music/${action}`, {method: 'POST'});
    const result = await response.json();
    if (!response.ok || !result.ok) throw new Error(result.error || 'CLIAMP action failed');
    const labels = {prev: 'PREVIOUS', toggle: 'PLAY / PAUSE', next: 'NEXT',
      'volume-down': 'VOLUME −', 'volume-up': 'VOLUME +', shuffle: 'SHUFFLE',
      repeat: 'REPEAT', stop: 'STOP'};
    showEvent(`CLIAMP / ${labels[action] || action.replace('-', ' ').toUpperCase()}`, 2000);
    window.setTimeout(refreshMusic, 250);
  } catch { showEvent('CLIAMP CONTROL UNAVAILABLE — check the player daemon.', 5000); }
}
refreshMusic();
refreshAmbientLightCalibration();
window.setInterval(refreshMusic, 2000);
window.setInterval(refreshMusicSpectrum, 200);
// Approximate solar sunset at the standard -0.833° horizon (no terrain correction).
function sunsetAt(latitude, longitude, day) {
  const rad = Math.PI / 180;
  const start = Date.UTC(day.getUTCFullYear(), 0, 0);
  const n = Math.floor((Date.UTC(day.getUTCFullYear(), day.getUTCMonth(), day.getUTCDate()) - start) / 86400000);
  const gamma = 2 * Math.PI / 365 * (n - 1);
  const declination = 0.006918 - 0.399912 * Math.cos(gamma) + 0.070257 * Math.sin(gamma)
    - 0.006758 * Math.cos(2 * gamma) + 0.000907 * Math.sin(2 * gamma)
    - 0.002697 * Math.cos(3 * gamma) + 0.00148 * Math.sin(3 * gamma);
  const equation = 229.18 * (0.000075 + 0.001868 * Math.cos(gamma) - 0.032077 * Math.sin(gamma)
    - 0.014615 * Math.cos(2 * gamma) - 0.040849 * Math.sin(2 * gamma));
  const cosine = (Math.sin(-0.833 * rad) - Math.sin(latitude * rad) * Math.sin(declination))
    / (Math.cos(latitude * rad) * Math.cos(declination));
  if (cosine < -1 || cosine > 1) return null;
  return Date.UTC(day.getUTCFullYear(), day.getUTCMonth(), day.getUTCDate())
    + (720 - 4 * longitude - equation + 4 * Math.acos(cosine) / rad) * 60000;
}
function renderSundown(data, now = Date.now()) {
  const {latitude, longitude} = data.location;
  if (!Number.isFinite(latitude) || !Number.isFinite(longitude) || Math.abs(latitude) > 90 || Math.abs(longitude) > 180) {
    $('#sundown').textContent = '—';
    $('#sundown-note').textContent = 'GPS location unavailable';
    return;
  }
  // Solar-local date handles coordinates on either side of the date line.
  const day = new Date(now + longitude * 240000);
  let sunset = sunsetAt(latitude, longitude, day);
  let next = false;
  if (sunset !== null && sunset <= now) {
    day.setUTCDate(day.getUTCDate() + 1);
    sunset = sunsetAt(latitude, longitude, day);
    next = true;
  }
  if (sunset === null) {
    $('#sundown').textContent = 'NO SUNSET';
    $('#sundown-note').textContent = 'No sunset on this solar day';
    return;
  }
  const minutes = Math.max(0, Math.ceil((sunset - now) / 60000));
  $('#sundown').textContent = `${Math.floor(minutes / 60)}h ${String(minutes % 60).padStart(2, '0')}m`;
  $('#sundown-note').textContent = `${data.source === 'mock' ? 'Demo location · ' : ''}${next ? 'Next sunset' : 'Sunset'} estimate · terrain excluded`;
}
// Quantize the dashboard only; retain the sensor's original telemetry precision.
function wholeDegree(value) {
  return Number.isFinite(value) ? Math.round(value) : null;
}
function tiltAlertLevel(pitch, roll) {
  if (!Number.isFinite(pitch) || !Number.isFinite(roll)) return 'normal';
  const degrees = Math.max(Math.abs(pitch), Math.abs(roll));
  return degrees >= 30 ? 'alarm' : degrees >= 20 ? 'caution' : 'normal';
}
function renderSuspension(data) {
  const suspension = data?.suspension;
  for (const side of ['left', 'right']) {
    const value = suspension?.[`${side}_psi`];
    document.querySelectorAll(`[data-value="suspension.${side}_psi"]`).forEach(field => {
      field.textContent = Number.isFinite(value) ? value.toFixed(1) : '—';
    });
  }
  const stateKey = suspension?.state || 'disconnected';
  const state = {idle: 'Connected', inflating: 'Inflating', deflating: 'Deflating',
    disconnected: 'Disconnected', unknown: 'Unknown'}[suspension?.state] || 'Disconnected';
  document.querySelectorAll('[data-suspension-state]').forEach(field => {
    field.textContent = state;
    if (field.closest('.suspension-card')) field.closest('.suspension-card').dataset.suspensionState = stateKey;
  });
  const status = data?.airlift?.status;
  const note = data?.source === 'mock' ? 'Simulated · Read-only'
    : status === 'disabled' ? 'Read-only · BLE disabled'
    : status === 'stale' ? 'Read-only · Pressure stale'
    : ['live', 'connected'].includes(status) ? (data.airlift.status_uuid
      ? 'Read-only · WirelessAir' : 'Read-only · Status not mapped')
    : 'Read-only · Waiting for BLE';
  document.querySelectorAll('[data-suspension-note]').forEach(field => { field.textContent = note; });
}
function render(data) {
  if (data.schema_version !== 1 || !['mock', 'live'].includes(data.source)) throw new Error('Unknown telemetry contract');
  const live = data.source === 'live';
  window.latestTelemetry = data;
  renderSundown(data);
  const rawPitch = wholeDegree(data.attitude.pitch_deg);
  const rawRoll = wholeDegree(data.attitude.roll_deg);
  const pitch = rawPitch === null ? null : wholeDegree(rawPitch - calibration.pitch);
  const roll = rawRoll === null ? null : wholeDegree(rawRoll - calibration.roll);
  const tiltAlert = tiltAlertLevel(pitch, roll);
  for (const field of document.querySelectorAll('[data-value]')) {
    const value = field.dataset.value.split('.').reduce((item, key) => item?.[key], data);
    if (field.dataset.value === 'attitude.pitch_deg') field.textContent = pitch === null ? '—' : String(pitch);
    else if (field.dataset.value === 'attitude.roll_deg') field.textContent = roll === null ? '—' : String(roll);
    else if (field.dataset.value === 'location.altitude_m') field.textContent = Number.isFinite(value) ? String(Math.round(value)) : '—';
    else if (field.dataset.value === 'location.heading_deg') field.textContent = Number.isFinite(value)
      ? String(((Math.round(value) % 360) + 360) % 360) : '—';
    else field.textContent = value ?? '—';
  }
  $('#data-mode-label').textContent = live ? 'LIVE HARDWARE TEST' : 'SIMULATED DATA';
  renderSuspension(data);
  $('#obd-label').textContent = live ? 'OBD / UNAVAILABLE' : 'OBD / DEMO';
  $('#gps-label').textContent = live ? `GPS / ${data.sources.gps.toUpperCase().replace('_', ' ')}` : 'GPS / DEMO';
  $('#environment-source').textContent = live ? `NANO / ${data.sources.nano.toUpperCase()}` : 'SENSORS / DEMO';
  document.querySelectorAll('.imu-label').forEach(label => {
    label.textContent = live ? (tiltAlert === 'alarm' ? 'TILT / ALARM 30°+'
      : tiltAlert === 'caution' ? 'TILT / CAUTION 20°+'
        : calibration.active ? 'TILT / LEVEL ZEROED' : 'TILT / UNCALIBRATED') : 'IMU / DEMO';
    label.classList.toggle('tilt-caution', tiltAlert === 'caution');
    label.classList.toggle('tilt-alarm', tiltAlert === 'alarm');
  });
  const heading = data.location.heading_deg;
  const validHeading = Number.isFinite(heading);
  document.querySelectorAll('.heading-label').forEach(label => label.textContent = validHeading
    ? ['N','NE','E','SE','S','SW','W','NW'][((Math.round(heading / 45) % 8) + 8) % 8] : 'NO FIX');
  document.querySelectorAll('.compass-dial').forEach(dial => {
    dial.classList.toggle('unavailable', !validHeading);
    dial.querySelector('.compass-needle').style.transform = `rotate(${heading || 0}deg)`;
  });
  const altitudeSource = data.location.altitude_source;
  const altitudeLabel = live
    ? ({gps: 'ALTITUDE / GPS', barometric: 'ALTITUDE / BARO EST.'}[altitudeSource]
      || 'ALTITUDE / UNAVAILABLE') : 'ALTITUDE';
  document.querySelectorAll('[data-altitude-label]').forEach(label => {
    label.textContent = altitudeLabel;
    label.classList.toggle('altitude-from-baro', altitudeSource === 'barometric');
    label.classList.toggle('altitude-from-gps', altitudeSource === 'gps');
  });
  for (const source of ['gps', 'nano', 'obd', 'network']) {
    const status = data.sources[source] || 'unavailable';
    const field = $(`#${source}-state`);
    field.textContent = status.toUpperCase().replace('_', ' ');
    field.classList.toggle('source-connected', ['live', 'connected'].includes(status));
  }
  document.querySelectorAll('[data-gauge]').forEach(gauge => {
    const value = gauge.dataset.gauge.split('.').reduce((item, key) => item?.[key], data);
    const percent = Number.isFinite(value) ? Math.max(0, Math.min(100, value / Number(gauge.dataset.max) * 100)) : 0;
    gauge.querySelector('.gauge-fill').style.strokeDasharray = `${percent} 100`;
  });
  window.dashboardMap?.telemetry(data);
  window.navball?.update(pitch, roll);
  $('#dtc').textContent = data.vehicle.dtc_count == null ? 'DTC UNAVAILABLE' : `${data.vehicle.dtc_count} DTC / SIMULATED`;
  if (navigationLayer === 'tabs' && $('#detail-overlay').hidden && Date.now() >= eventHoldUntil) {
    showEvent(live ? '△ BENCH TEST — Tilt is an uncalibrated gravity estimate, affected by motion. Heading unavailable. Recording off.' : '△ DEMO SESSION — All instrument values are simulated. No hardware or recording connected.');
  }
  joystick(data);
  lastReceived = Date.now();
  document.body.classList.remove('stale');
  $('#connection').textContent = live ? `API CONNECTED / NANO ${data.sources.nano.toUpperCase()}` : 'MOCK FEED / CONNECTED';
}
function stale() {
  document.body.classList.add('stale');
  $('#connection').textContent = 'FEED LOST / RECONNECTING';
  for (const field of document.querySelectorAll('[data-value]')) field.textContent = '—';
  renderSuspension(null);
  for (const source of ['gps', 'nano', 'obd', 'network']) {
    const field = $(`#${source}-state`);
    field.textContent = '—';
    field.classList.remove('source-connected');
  }
  $('#dtc').textContent = 'DTC UNAVAILABLE';
  document.querySelectorAll('.heading-label').forEach(label => label.textContent = 'NO FIX');
  document.querySelectorAll('.compass-dial').forEach(dial => dial.classList.add('unavailable'));
  document.querySelectorAll('.gauge-fill').forEach(gauge => gauge.style.strokeDasharray = '0 100');
  window.dashboardMap?.clearLocation();
  window.navball?.clear();
  $('#sundown').textContent = '—';
  $('#sundown-note').textContent = 'Location feed disconnected';
  $('#joy-status').textContent = 'DISCONNECTED';
  $('#joy-button').textContent = '—';
  joySession = null;
}
function connect() {
  const socket = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws/telemetry`);
  socket.onmessage = (message) => { try { render(JSON.parse(message.data)); } catch { stale(); } };
  socket.onclose = () => { stale(); setTimeout(connect, 2000); };
  socket.onerror = () => socket.close();
}
setInterval(() => {
  $('#clock').textContent = new Date().toLocaleTimeString([], {hour:'2-digit', minute:'2-digit', hour12:false});
  if (lastReceived && Date.now() - lastReceived > 2000) stale();
}, 500);
connect();
// Never replay mode actions accumulated while this browser was hidden.
document.addEventListener('visibilitychange', () => { joySession = null; });
