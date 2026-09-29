'use strict';
class SystemHoldGuard {
  constructor(duration = 2000) {
    this.duration = duration;
    this.action = null;
    this.origin = null;
    this.startedAt = null;
    this.releaseRequired = false;
  }
  arm(action, origin, now) {
    if (!action || this.releaseRequired || this.action) return false;
    this.action = action;
    this.origin = origin;
    this.startedAt = now;
    return true;
  }
  update({origin, events = [], pressed, now}) {
    if (!pressed) {
      this.cancel(false);
      this.releaseRequired = false;
      return null;
    }
    if (!this.action) return null;
    if (origin !== this.origin || events.some(event => event.action !== 'select')) {
      this.cancel(true);
      return null;
    }
    if (now - this.startedAt < this.duration) return null;
    const action = this.action;
    this.cancel(true);
    return action;
  }
  cancel(requireRelease = true) {
    if (this.action && requireRelease) this.releaseRequired = true;
    this.action = null;
    this.origin = null;
    this.startedAt = null;
  }
}
const $ = (selector) => document.querySelector(selector);
const driveDashboard = $('#drive-dashboard');
const driveLocation = driveDashboard?.querySelector('.drive-location');
const driveAttitude = driveDashboard?.querySelector('.drive-secondary');
const adventureDashboard = $('#adventure-dashboard');

function addConditionsStrip(dashboard, mode) {
  if (!dashboard) return null;
  const strip = document.createElement('section');
  strip.className = `conditions-strip ${mode}-conditions panel`;
  strip.setAttribute('aria-label', 'Weather and road conditions');
  strip.innerHTML = '<div class="condition-item weather-condition"><span>WEATHER</span><strong class="weather-temperature"><i data-weather="temperature">—</i><small>°C</small></strong><small class="weather-summary" data-weather="summary">NO FEED</small><small data-weather="source">—</small></div><div class="condition-item nano-temperature"><span>CABIN TEMP · NANO</span><strong><b data-value="environment.temperature_c">—</b><small>°C</small></strong></div><div class="condition-item"><span>WIND / GUST</span><strong><b data-weather="wind">—</b></strong></div><div class="condition-item road-condition"><span>ROAD / 511 AB</span><strong data-road="condition">KEY REQUIRED</strong><small data-road="source">511 Alberta</small></div><section class="weather-detail" aria-label="Weather forecast details" hidden><header class="weather-detail-header"><div><span>OPEN-METEO · <b data-weather-detail="status">WAITING</b></span><strong data-weather-detail="headline">Conditions unavailable</strong></div><small data-weather-detail="location">—</small><small data-weather-detail="updated">—</small></header><div class="weather-current-grid"><div><span>FEELS LIKE</span><strong data-weather-detail="feels">—</strong></div><div><span>HUMIDITY</span><strong data-weather-detail="humidity">—</strong></div><div><span>CLOUD COVER</span><strong data-weather-detail="cloud">—</strong></div><div><span>PRESSURE</span><strong data-weather-detail="pressure">—</strong></div><div><span>VISIBILITY</span><strong data-weather-detail="visibility">—</strong></div><div><span>UV INDEX</span><strong data-weather-detail="uv">—</strong></div><div><span>PRECIP / RAIN / SHOWERS</span><strong data-weather-detail="precip">—</strong></div><div><span>SNOWFALL</span><strong data-weather-detail="snow">—</strong></div><div><span>WIND / GUST</span><strong data-weather-detail="wind">—</strong></div></div><div class="weather-forecast-block"><h3>2 DAY OUTLOOK</h3><div class="weather-daily-grid" data-weather-list="daily"></div></div><div class="weather-forecast-block"><h3>HOURLY · NEXT 12 HOURS</h3><div class="weather-hourly-list" data-weather-list="hourly"></div></div></section>';
  const outlook = document.createElement('small');
  outlook.dataset.weather = 'outlook';
  outlook.textContent = 'NEXT 3H · —';
  strip.querySelectorAll('.condition-item')[2].append(outlook);
  const roadDetail = document.createElement('section');
  roadDetail.className = 'road-detail';
  roadDetail.setAttribute('aria-label', 'Nearest road report details');
  roadDetail.hidden = true;
  roadDetail.innerHTML = '<h3>NEAREST 511 ROAD REPORT</h3><div class="road-detail-grid"><div><span>ROAD / AREA</span><strong data-road-detail="roadway">—</strong></div><div><span>LOCATION</span><strong data-road-detail="location">—</strong></div><div><span>CONDITION</span><strong data-road-detail="condition">—</strong></div><div><span>OTHER CONDITIONS</span><strong data-road-detail="secondary">—</strong></div><div><span>VISIBILITY</span><strong data-road-detail="visibility">—</strong></div><div><span>REPORT DISTANCE</span><strong data-road-detail="distance">—</strong></div><div><span>REPORTED</span><strong data-road-detail="reported">—</strong></div><div><span>FEED CHECKED</span><strong data-road-detail="checked">—</strong></div></div><p data-road-detail="note">No report available.</p>';
  strip.append(roadDetail);
  dashboard.prepend(strip);
  return strip;
}
const driveConditions = addConditionsStrip(driveDashboard, 'drive');
const adventureConditions = addConditionsStrip(adventureDashboard, 'adventure');

function addVehicleStrip(dashboard, mode) {
  const strip = document.createElement('section');
  strip.className = `vehicle-strip ${mode}-vehicle-strip panel`;
  strip.setAttribute('aria-label', 'OBD-II vehicle telemetry');
  strip.innerHTML = '<div class="vehicle-strip-title">OBD-II</div><div class="vehicle-strip-metric"><span>SPEED</span><strong><b data-value="vehicle.speed_mph">—</b><small>KM/H</small></strong></div><div class="vehicle-strip-metric"><span>RPM</span><strong><b data-value="vehicle.rpm">—</b></strong></div><div class="vehicle-strip-metric"><span>COOLANT</span><strong><b data-value="vehicle.coolant_c">—</b><small>°C</small></strong></div><div class="vehicle-strip-metric"><span>VOLTAGE</span><strong><b data-value="vehicle.voltage_v">—</b><small>V</small></strong></div><div class="vehicle-strip-metric"><span>ENGINE LOAD</span><strong><b data-value="vehicle.load_pct">—</b><small>%</small></strong></div><div class="vehicle-strip-metric"><span>DTC</span><strong><b data-value="vehicle.dtc_count">—</b></strong></div>';
  dashboard.append(strip);
  return strip;
}
const driveVehicleStrip = addVehicleStrip(driveDashboard, 'drive');
const adventureVehicleStrip = addVehicleStrip(adventureDashboard, 'adventure');

function addBearingReadout(container, source) {
  if (!container) return;
  const readout = document.createElement('div');
  readout.className = 'bearing-readout';
  readout.setAttribute('aria-label', 'GPS bearing, reported as course over ground');
  readout.innerHTML = `<span>BEARING</span><strong><b data-value="location.heading_deg">—</b><small>°</small></strong>`;
  container.append(readout);
  source?.classList.add('bearing-source');
}
addBearingReadout(driveAttitude?.querySelector('.compact-orientation'), driveLocation);
const trailAttitude = adventureDashboard?.querySelector('.trail-attitude');
const trailStatus = document.createElement('span');
trailStatus.className = 'imu-label';
trailStatus.textContent = 'IMU / —';
trailAttitude?.querySelector(':scope > .label')?.append(trailStatus);
addBearingReadout(trailAttitude, adventureDashboard?.querySelector('.trail-compass'));
const adventureInfo = adventureDashboard?.querySelector('.adventure-info');
const sundown = adventureInfo?.querySelector('.sundown');
if (sundown && adventureConditions) adventureConditions.append(sundown);
const driveSundown = document.createElement('div');
driveSundown.className = 'sundown drive-sundown';
driveSundown.innerHTML = '<span class="label">SUNSET</span><strong data-sundown-value>—</strong><small data-sundown-note>Waiting for location</small>';
driveConditions?.append(driveSundown);
const recordButton = $('#record');
const exportLogButton = $('#export-log');
const exportGpsTrackButton = $('#export-gps-track');
const exportAllRecordingsButton = $('#export-all-recordings');
const recordingIndicator = $('.brand');
const recordingSummary = document.createElement('div');
recordingSummary.className = 'recording-summary';
recordingSummary.setAttribute('aria-label', 'Latest trip summary');
recordingSummary.innerHTML = '<div><span>TRIP</span><strong data-trip="state">NO LOG</strong></div><div><span>ELAPSED</span><strong data-trip="elapsed">—</strong></div><div><span>DISTANCE</span><strong data-trip="distance">—</strong></div><div><span>MOVING</span><strong data-trip="moving">—</strong></div><div><span>GPS FIXES</span><strong data-trip="fixes">—</strong></div><div><span>LAST FIX</span><strong data-trip="last-fix">—</strong></div>';
$('.recording-tools .recording-actions')?.before(recordingSummary);
let recordingState = {recording: false, recording_id: null, latest_recording_id: null};
recordButton.addEventListener('click', toggleRecording);
exportLogButton.addEventListener('click', () => downloadRecording('log'));
exportGpsTrackButton.addEventListener('click', () => downloadRecording('gps-track.gpx'));
exportAllRecordingsButton.addEventListener('click', downloadAllRecordings);

const launchParameters = new URLSearchParams(window.location.search);
let eventHoldUntil = 0;
function showEvent(message, holdMilliseconds = 0) {
  $('#event').textContent = message;
  eventHoldUntil = holdMilliseconds ? Date.now() + holdMilliseconds : 0;
}
window.dashboardEvent = showEvent;

function updateRecordingControls(state) {
  recordingState = state;
  recordingIndicator.classList.toggle('recording-active', Boolean(state.recording));
  recordingIndicator.setAttribute('aria-label', state.recording
    ? 'OVRLand — recording active' : 'OVRLand — Operational Vehicle Readout');
  const recordNote = $('#record-note');
  $('#record-label').textContent = state.recording ? '■ STOP RECORDING' : '● RECORD';
  recordButton.setAttribute('aria-pressed', String(Boolean(state.recording)));
  recordButton.classList.toggle('recording-active', Boolean(state.recording));
  recordNote.textContent = state.error ? 'LOG WRITE ERROR'
    : state.summary?.recovery_warning ? `RECOVERY WARNING · ${state.summary.recovery_warning}`
    : state.recording ? `RECORDING SINCE ${new Date(state.started_at).toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'})}`
      : state.latest_recording_id ? 'LAST LOG READY · EXPORT AVAILABLE' : 'START FULL DATA LOG';
  const exportId = state.recording_id || state.latest_recording_id;
  exportLogButton.disabled = !exportId;
  exportGpsTrackButton.disabled = !exportId;
  exportAllRecordingsButton.disabled = !state.latest_recording_id;
  const recordTarget = moduleTargets.camp.find(([key]) => key === 'record');
  if (recordTarget) recordTarget[2] = state.recording ? 'STOP RECORDING' : 'START RECORDING';
  renderRecordingSummary();
}

function elapsedLabel(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) return '—';
  if (seconds < 60) return `${Math.floor(seconds)}s`;
  const minutes = Math.floor(seconds / 60);
  return `${Math.floor(minutes / 60)}h ${String(minutes % 60).padStart(2, '0')}m`;
}

function ageLabel(stamp, unixSeconds = false) {
  const time = unixSeconds ? Number(stamp) * 1000 : Date.parse(stamp);
  if (!Number.isFinite(time) || time <= 0) return 'TIME UNKNOWN';
  const minutes = Math.max(0, Math.floor((Date.now() - time) / 60000));
  return minutes < 1 ? 'JUST NOW' : minutes < 60 ? `${minutes}M AGO`
    : minutes < 1440 ? `${Math.floor(minutes / 60)}H AGO` : `${Math.floor(minutes / 1440)}D AGO`;
}

function renderRecordingSummary() {
  const summary = recordingState.summary;
  const set = (key, value) => { const node = recordingSummary.querySelector(`[data-trip="${key}"]`); if (node) node.textContent = value; };
  set('state', recordingState.recording ? 'RECORDING' : summary ? 'LAST LOG' : 'NO LOG');
  if (!summary) {
    for (const key of ['elapsed', 'distance', 'moving', 'fixes', 'last-fix']) set(key, '—');
    return;
  }
  const start = Date.parse(summary.started_at);
  const end = recordingState.recording ? Date.now() : Date.parse(summary.stopped_at);
  set('elapsed', elapsedLabel((end - start) / 1000));
  const hasTrack = Number.isFinite(summary.fix_count) && summary.fix_count >= 2;
  set('distance', hasTrack && Number.isFinite(summary.distance_km) ? `${summary.distance_km.toFixed(1)} km` : '—');
  set('moving', hasTrack ? elapsedLabel(summary.moving_seconds) : '—');
  set('fixes', Number.isFinite(summary.fix_count) ? String(summary.fix_count) : '—');
  set('last-fix', summary.last_fix_at ? ageLabel(summary.last_fix_at) : 'NO GPS FIX');
}

async function refreshRecordingStatus() {
  try {
    const response = await fetch('/api/recording/status', {cache: 'no-store'});
    if (!response.ok) throw new Error('Recorder status unavailable');
    updateRecordingControls(await response.json());
    recordButton.disabled = false;
  } catch {
    $('#record-note').textContent = 'RECORDER UNAVAILABLE';
  }
}

async function toggleRecording() {
  recordButton.disabled = true;
  const action = recordingState.recording ? 'stop' : 'start';
  try {
    const response = await fetch(`/api/recording/${action}`, {method: 'POST'});
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Recording action failed');
    updateRecordingControls(result);
    showEvent(action === 'start' ? 'RECORDING / FULL DATA LOG STARTED' : 'RECORDING / LOG SAVED', 4000);
  } catch (error) {
    showEvent(`RECORDING / ${error.message || 'ACTION FAILED'}`, 5000);
    await refreshRecordingStatus();
  } finally {
    recordButton.disabled = false;
  }
}

async function downloadRecording(kind) {
  const recordingId = recordingState.recording_id || recordingState.latest_recording_id;
  if (!recordingId) return;
  if (kind === 'log') {
    try {
      const check = await fetch(`/api/recordings/${encodeURIComponent(recordingId)}/log?check=1`);
      if (!check.ok) throw new Error(await check.text() || 'Log export unavailable');
    } catch (error) {
      showEvent(`RECORDING / EXPORT FAILED · ${(error.message || 'LOG UNAVAILABLE').toUpperCase()}`, 6000);
      return;
    }
  }
  const link = document.createElement('a');
  link.href = `/api/recordings/${encodeURIComponent(recordingId)}/${kind}`;
  link.download = '';
  document.body.append(link);
  link.click();
  link.remove();
  showEvent(kind === 'log' ? 'RECORDING / DOWNLOADING FULL LOG' : 'RECORDING / DOWNLOADING GPS TRACK', 3000);
}

async function downloadAllRecordings() {
  if (!recordingState.latest_recording_id) return;
  try {
    const check = await fetch('/api/recordings/export-all.zip?check=1');
    if (!check.ok) throw new Error(await check.text() || 'Export unavailable');
    const result = await check.json();
    if (!result.ready) throw new Error('No recording logs are available');
  } catch (error) {
    showEvent(`RECORDING / EXPORT FAILED · ${(error.message || 'CHECK STORAGE').toUpperCase()}`, 6000);
    return;
  }
  const link = document.createElement('a');
  link.href = '/api/recordings/export-all.zip';
  link.download = '';
  document.body.append(link);
  link.click();
  link.remove();
  showEvent('RECORDING / DOWNLOADING ALL SAVED LOGS', 4000);
}

refreshRecordingStatus();
window.setInterval(refreshRecordingStatus, 5000);
window.setInterval(renderRecordingSummary, 30000);

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
musicDashboard.innerHTML = '<section class="music-portal radio-portal"><span class="label" data-music="preset">OVRLAND RADIO</span><span class="music-station" data-music="station" hidden></span><strong data-music="title">Choose a station</strong><span data-music="artist">Internet radio</span><div class="music-spectrum" data-music="spectrum" aria-label="Radio playback indicator"></div><div class="music-progress"><span data-music="state">READY</span><span data-music="position">LIVE</span></div><div class="music-settings"><span>VOL <b data-music="volume">80%</b></span></div><small data-music="availability">BROWSER RADIO · READY</small></section><section class="music-portal spotify-portal"><span class="label">OPTIONAL SOURCE</span><strong>SPOTIFY</strong><span>Account-based streaming</span><small>PLAYER NOT CONFIGURED</small></section><div class="music-hint">DOWN: SOURCE · PRESS: OPEN<br><span>Radio stays idle until you choose a station.</span></div>';
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
  camp: ['SYSTEM / POWER CONTROLS', 'WINDOW MODE / STOP OR POWER OFF THE PI'],
};
let focusIndex = 0;
let moduleIndex = -1;
let navigationLayer = 'tabs';
let calibration = (() => {
  try {
    const saved = JSON.parse(localStorage.getItem('ovrland.attitudeCalibration') || 'null');
    return Number.isFinite(saved?.pitch) && Number.isFinite(saved?.roll)
      ? {pitch: saved.pitch, roll: saved.roll, active: true}
      : {pitch: 0, roll: 0, active: false};
  } catch { return {pitch: 0, roll: 0, active: false}; }
})();
const moduleTargets = {
  drive: [
    ['map', '.map-panel', 'MAP'], ['conditions', '.drive-conditions', 'WEATHER / ROAD / SUNSET'],
    ['attitude', '.drive-secondary', 'NAV BALL / PITCH / ROLL / COURSE'],
    ['obd', '.drive-vehicle-strip', 'OBD-II TELEMETRY'],
  ],
  adventure: [
    ['conditions', '.adventure-conditions', 'WEATHER / ROAD / SUNSET'],
    ['attitude', '.trail-attitude', 'NAV BALL / PITCH / ROLL / COURSE'],
    ['map', '.map-panel', 'MAP'], ['location', '.adventure-info', 'GPS / LOCATION'],
    ['obd', '.adventure-vehicle-strip', 'OBD-II TELEMETRY'],
  ],
  music: [
    ['radio', '.radio-portal', 'CURATED RADIO'],
    ['spotify', '.spotify-portal', 'SPOTIFY'],
  ],
  camp: [
    ['capture-day', '[data-ambient-capture="day"]', 'CAPTURE DAY'],
    ['capture-dusk', '[data-ambient-capture="dusk"]', 'CAPTURE DUSK'],
    ['capture-night', '[data-ambient-capture="night"]', 'CAPTURE NIGHT'],
    ['record', '#record', 'START RECORDING'],
    ['export-log', '#export-log', 'EXPORT LATEST LOG'],
    ['export-gps-track', '#export-gps-track', 'EXPORT LATEST GPS TRACK'],
    ['export-all-recordings', '#export-all-recordings', 'EXPORT ALL LOGS'],
    ['window-mode', '#window-mode-toggle', 'CAMP MODE / FULL SCREEN'],
    ['stop-app', '[data-system-action="stop-app"]', 'STOP APP'],
    ['poweroff-pi', '[data-system-action="poweroff-pi"]', 'POWER OFF PI'],
  ],
};
function activeModules() { return moduleTargets[$('body').dataset.mode] ?? []; }
function clearJoystickFocus() {
  modeButtons.forEach(button => button.classList.remove('joy-focus'));
  document.querySelectorAll('.joy-section-focus')
    .forEach(item => item.classList.remove('joy-section-focus'));
}
function setModuleFocus(index) {
  const next = activeModules()[index];
  if (systemHold.action && systemHold.origin !== `${$('body').dataset.mode}:${next?.[0]}:${joySession}`) cancelSystemHold();
  navigationLayer = 'modules';
  const targets = activeModules();
  const target = targets.length ? targets[(index + targets.length) % targets.length] : null;
  moduleIndex = target ? targets.indexOf(target) : -1;
  // The tab outline belongs only to the upper navigation layer. Clear it as
  // soon as DOWN enters module navigation so the visible focus follows the
  // joystick layer.
  clearJoystickFocus();
  const targetNode = target && $(target[1]);
  if (targetNode) {
    targetNode.classList.add('joy-section-focus');
    targetNode.scrollIntoView({block: 'nearest', inline: 'nearest'});
  }
  if (target) $('#event').textContent = $('body').dataset.mode === 'camp'
    ? `FOCUS / ${target[2]} — PRESS TO ACTIVATE`
    : `FOCUS / ${target[2]} — PRESS TO OPEN DETAIL`;
}
function moveModuleFocus(direction) {
  const targets = activeModules();
  if (!targets.length) return;
  const current = targets[moduleIndex];
  const currentNode = current && $(current[1]);
  if (!currentNode) return setModuleFocus(0);
  const rect = currentNode.getBoundingClientRect();
  const cx = rect.left + rect.width / 2;
  const cy = rect.top + rect.height / 2;
  const vector = {left: [-1, 0], right: [1, 0], up: [0, -1], down: [0, 1]}[direction];
  if (!vector) return;
  const candidates = targets.map((target, index) => {
    const node = $(target[1]);
    if (!node || node === currentNode) return null;
    const bounds = node.getBoundingClientRect();
    if (!bounds.width || !bounds.height || node.closest('[hidden]')) return null;
    const dx = bounds.left + bounds.width / 2 - cx;
    const dy = bounds.top + bounds.height / 2 - cy;
    const along = dx * vector[0] + dy * vector[1];
    const across = Math.abs(dx * vector[1] - dy * vector[0]);
    return {index, along, across, score: along + across * 1.35};
  }).filter(Boolean);
  const ahead = candidates.filter(candidate => candidate.along > 2).sort((a, b) => a.score - b.score);
  if (ahead.length) return setModuleFocus(ahead[0].index);
  if (direction === 'up') {
    focusMode(focusIndex);
    showEvent('TAB FOCUS — PRESS TO SELECT OR DOWN TO RETURN TO MODULES', 3000);
  }
  else {
    // Wrap sideways to the opposite edge, favoring the closest row.
    const wrapped = candidates.sort((a, b) => a.along - b.along || a.across - b.across);
    if (wrapped.length) setModuleFocus(wrapped[0].index);
  }
}
function focusMode(index) {
  navigationLayer = 'tabs';
  focusIndex = (index + modeButtons.length) % modeButtons.length;
  clearJoystickFocus();
  modeButtons.forEach((button, i) => button.classList.toggle('joy-focus', i === focusIndex));
  modeButtons[focusIndex].scrollIntoView({block: 'nearest', inline: 'nearest'});
}

function enableTouchModules() {
  for (const [key, selector] of activeModulesForTouch()) {
    const node = $(selector);
    if (!node || node.dataset.touchModule === 'true') continue;
    node.dataset.touchModule = 'true';
    node.classList.add('touch-module');
    if (!node.matches('button, a, input')) {
      node.tabIndex = 0;
      node.setAttribute('role', node.querySelector('button, a, input') ? 'group' : 'button');
      node.setAttribute('aria-label', `${key.toUpperCase()} module. Tap or press Enter to open details.`);
    }
    const activate = event => {
      if (event.type === 'click' && event.target.closest('button, a, input, .leaflet-container, .leaflet-control')) return;
      const index = activeModules().findIndex(target => target[0] === key);
      if (index < 0 || $('body').dataset.mode === 'camp') return;
      setModuleFocus(index);
      openDetail(key);
    };
    node.addEventListener('click', activate);
    node.addEventListener('keydown', event => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        activate(event);
      }
    });
  }
}
function activeModulesForTouch() {
  return Object.values(moduleTargets).flat().map(target => [target[0], target[1]]);
}
enableTouchModules();
for (const [i, button] of modeButtons.entries()) {
  button.addEventListener('click', () => {
    cancelSystemHold();
    document.body.dataset.mode = button.dataset.mode;
    focusMode(i);
    for (const item of modeButtons) {
      item.classList.toggle('active', item === button);
      item.setAttribute('aria-pressed', String(item === button));
    }
    ['#screen-title', '#mode-caption'].forEach((id, j) => $(id).textContent = modes[button.dataset.mode][j]);
    for (const mode of Object.keys(modes)) $(`#${mode}-dashboard`).hidden = mode !== button.dataset.mode;
    $('#workspace').hidden = ['camp', 'music'].includes(button.dataset.mode);
    document.querySelectorAll('.joy-section-focus')
      .forEach(item => item.classList.remove('joy-section-focus'));
    window.dashboardMap?.resize();
    window.navball?.refresh();
  });
}
let launchedWindowMode = launchParameters.get('window');
const windowModeButton = $('#window-mode-toggle');
if (launchedWindowMode === 'camp') windowModeButton.textContent = '⛶ FULL SCREEN';
async function toggleWindowMode() {
  const requestedMode = launchedWindowMode === 'camp' ? 'fullscreen' : 'camp';
  try {
    const response = await fetch(`/api/window-mode/${requestedMode}`, {method: 'POST'});
    if (!response.ok) throw new Error('Window mode unavailable');
    windowModeButton.disabled = true;
    launchedWindowMode = requestedMode;
    windowModeButton.textContent = requestedMode === 'camp' ? '⛶ FULL SCREEN' : 'CAMP MODE';
    window.setTimeout(() => { windowModeButton.disabled = false; }, 1600);
    showEvent(requestedMode === 'camp'
      ? 'OPENING CAMP MODE — returning OVRLand to the desktop…'
      : 'RETURNING TO FULL SCREEN…', 5000);
  } catch { showEvent('Window mode unavailable. Press Alt+F4 to return to the desktop.', 5000); }
}
windowModeButton.addEventListener('click', toggleWindowMode);
let lastReceived = 0;
let joySession = null;
let lastEvent = 0;
let movedDetailNode = null;
let detailRestore = null;
let detailNavballCleanup = null;
let detailModuleKey = null;
const systemHold = new SystemHoldGuard(2000);
let detailControlIndex = 0;
let musicStreams = [];
let musicStreamsLoading = false;
let musicStreamsError = '';
// Keep the panel reference when openDetail moves it out of the dashboard.
const radioPanel = musicDashboard.querySelector('.radio-portal');
const radioAudio = new Audio();
radioAudio.preload = 'none';
radioAudio.volume = 0.9;
let activeRadioStream = null;
let radioFailure = null;
let currentRadioTrack = null;
let trackMetadataUnavailable = false;
let nowPlayingRequest = 0;
function renderBrowserRadio(state) {
  const station = activeRadioStream;
  const stationNode = radioPanel.querySelector('[data-music="station"]');
  radioPanel.querySelector('[data-music="preset"]').textContent = 'OVRLAND RADIO';
  stationNode.textContent = station ? `${station.station_name} · ${station.provider}` : '';
  stationNode.hidden = !station;
  radioPanel.querySelector('[data-music="title"]').textContent =
    currentRadioTrack?.title || station?.display_name || 'Choose a station';
  const stationLabel = station ? `${station.station_name} · ${station.provider}` : 'Internet radio';
  radioPanel.querySelector('[data-music="artist"]').textContent = currentRadioTrack?.artist
    || (trackMetadataUnavailable ? `TRACK INFO UNAVAILABLE · ${stationLabel}`
      : (currentRadioTrack ? stationLabel : (station ? 'LOADING TRACK INFO…' : stationLabel)));
  radioPanel.querySelector('[data-music="state"]').textContent = state;
  radioPanel.querySelector('[data-music="position"]').textContent = radioFailure
    ? `ERROR ${radioAudio.error?.code ?? ''}` : (radioAudio.paused ? '—' : 'LIVE');
  radioPanel.querySelector('[data-music="volume"]').textContent = `${Math.round(radioAudio.volume * 100)}%`;
  radioPanel.querySelector('[data-music="availability"]').textContent =
    radioFailure || (state === 'UNAVAILABLE' ? 'RADIO STREAM UNAVAILABLE' : 'BROWSER RADIO · READY');
}
radioAudio.addEventListener('playing', () => {
  radioFailure = null;
  renderBrowserRadio('PLAYING');
});
radioAudio.addEventListener('pause', () => renderBrowserRadio(radioFailure ? 'UNAVAILABLE' : 'PAUSED'));
radioAudio.addEventListener('error', () => {
  const reasons = {2: 'NETWORK ERROR', 3: 'DECODE ERROR', 4: 'SOURCE REJECTED'};
  const code = radioAudio.error?.code;
  const reason = reasons[code] || 'MEDIA ERROR';
  let source = '';
  try {
    const url = new URL(radioAudio.currentSrc);
    source = `${url.host}${url.pathname}`;
  } catch {}
  const mp3Support = radioAudio.canPlayType('audio/mpeg') || 'unsupported';
  const detail = radioAudio.error?.message;
  radioFailure = `${reason} (${code ?? '?'}) · MP3 ${mp3Support}`
    + `${source ? ` · ${source}` : ''}${detail ? ` · ${detail}` : ''}`;
  renderBrowserRadio('UNAVAILABLE');
  showEvent(`RADIO / ${radioFailure}`, 5000);
});
async function ensureMusicStreams() {
  if (musicStreams.length) return musicStreams;
  const response = await fetch('/api/music/streams');
  const result = await response.json();
  if (!response.ok || !result.ok || !Array.isArray(result.streams)) {
    throw new Error(result.error || 'Curated stations unavailable');
  }
  musicStreams = result.streams;
  return musicStreams;
}
async function refreshNowPlaying(streamId) {
  const requestId = ++nowPlayingRequest;
  const unavailable = () => {
    if (requestId !== nowPlayingRequest || activeRadioStream?.id !== streamId) return;
    currentRadioTrack = null;
    trackMetadataUnavailable = true;
    renderBrowserRadio(radioAudio.paused ? 'PAUSED' : 'PLAYING');
  };
  try {
    const response = await fetch(`/api/music/now-playing/${encodeURIComponent(streamId)}`);
    if (!response.ok) return unavailable();
    const result = await response.json();
    if (requestId !== nowPlayingRequest || activeRadioStream?.id !== streamId) return;
    if (!result.ok || !result.title) return unavailable();
    currentRadioTrack = result;
    trackMetadataUnavailable = false;
    renderBrowserRadio(radioAudio.paused ? 'PAUSED' : 'PLAYING');
  } catch {
    unavailable();
  }
}
async function startBrowserRadio(stream = null) {
  try {
    const streams = musicStreams.length ? musicStreams : await ensureMusicStreams();
    const chosen = stream || activeRadioStream || streams[0];
    if (!chosen) throw new Error('No curated stations available');
    if (activeRadioStream?.id !== chosen.id || !radioAudio.src) {
      activeRadioStream = chosen;
      currentRadioTrack = null;
      trackMetadataUnavailable = false;
      radioAudio.src = chosen.playback_url;
      radioAudio.load();
    }
    radioFailure = null;
    // Start directly from the tab or station selection gesture; no player
    // daemon or separate command line utility is required.
    await radioAudio.play();
    renderBrowserRadio('PLAYING');
    refreshNowPlaying(chosen.id);
  } catch (error) {
    radioFailure = error.name === 'NotAllowedError'
      ? 'PLAY BLOCKED · BROWSER REQUIRES USER ACTIVATION'
      : `${error.name || 'PLAY ERROR'}${error.message ? ` · ${error.message}` : ''}`;
    renderBrowserRadio('UNAVAILABLE');
    showEvent(`RADIO / ${radioFailure.toUpperCase()}`, 5000);
  }
}
function moveRadioStation(delta) {
  if (!musicStreams.length) return startBrowserRadio();
  const index = musicStreams.findIndex(stream => stream.id === activeRadioStream?.id);
  return startBrowserRadio(musicStreams[(index + delta + musicStreams.length) % musicStreams.length]);
}
function changeRadioVolume(delta) {
  radioAudio.volume = Math.max(0, Math.min(1, radioAudio.volume + delta));
  renderBrowserRadio(radioAudio.paused ? 'PAUSED' : 'PLAYING');
}
window.setInterval(() => {
  if (!radioAudio.paused && activeRadioStream) refreshNowPlaying(activeRadioStream.id);
}, 15000);
// Load the catalog while the dashboard is idle so opening Radio can play at once.
ensureMusicStreams().catch(error => {
  musicStreamsError = error.message || 'Curated stations unavailable';
});
function cancelSystemHold() {
  systemHold.cancel(true);
  if ($('#system-status')) $('#system-status').textContent = 'SYSTEM STANDBY';
}
function joystick(data) {
  const meta = data.nano;
  const joy = data.joystick;
  $('#joy-status').textContent = meta?.status?.toUpperCase() ?? 'DEMO';
  $('#joy-button').textContent = joy ? (joy.pressed ? 'PRESSED' : 'RELEASED') : '—';
  if (!joy || meta?.status !== 'live' || document.hidden) {
    cancelSystemHold();
    joySession = null;
    return;
  }
  const now = performance.now();
  if (meta.session !== joySession) {
    cancelSystemHold();
    joySession = meta.session;
    lastEvent = meta.event_id;
    focusMode(modeButtons.findIndex(button => button.classList.contains('active')));
    return;
  }
  const holdOrigin = `${$('body').dataset.mode}:${activeModules()[moduleIndex]?.[0]}:${joySession}`;
  const pendingEvents = meta.events.filter(event => event.id > lastEvent);
  const joystickHoldPending = Boolean(systemHold.action);
  const confirmedAction = systemHold.update({origin: holdOrigin, events: pendingEvents,
    pressed: joy.pressed, now});
  if (confirmedAction) runSystemAction(confirmedAction);
  else if (joystickHoldPending && !systemHold.action) {
    $('#system-status').textContent = joy.pressed ? 'SYSTEM STANDBY — RELEASE TO REARM' : 'SYSTEM STANDBY';
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
    } else if (!detailOpen && ['left', 'right', 'up', 'down'].includes(event.action)) {
      if (navigationLayer === 'tabs' && (event.action === 'left' || event.action === 'right')) {
        focusMode(focusIndex + (event.action === 'left' ? -1 : 1));
      } else if (navigationLayer === 'modules') moveModuleFocus(event.action);
    }
    if (!detailOpen && event.action === 'down' && navigationLayer === 'tabs') setModuleFocus(0);
    if (event.action === 'select') {
      if (detailOpen) activateDetailControl();
      else if (navigationLayer === 'tabs') modeButtons[focusIndex].click();
      else if ($('body').dataset.mode === 'camp') {
        const target = activeModules()[moduleIndex];
        const action = target?.[0] ?? null;
        if (action === 'window-mode') windowModeButton.click();
        else if (action?.startsWith('capture-') ||
                 ['record', 'export-log', 'export-gps-track', 'export-all-recordings'].includes(action)) {
          $(target[1])?.click();
        }
        else if (['stop-app', 'poweroff-pi'].includes(action)) {
          if (systemHold.arm(action, holdOrigin, now)) {
            $('#system-status').textContent = 'HOLD BUTTON FOR 2 SECONDS TO CONFIRM';
          }
        }
      } else openDetail(activeModules()[moduleIndex]?.[0]);
    }
  }
}
function focusedModule() {
  const target = activeModules()[moduleIndex];
  return target ? {key: target[0], selector: target[1], title: target[2]} : null;
}
function activeDetailControls() {
  if (detailModuleKey === 'radio') return [
    {key: 'music-prev', label: 'PREVIOUS STATION'},
    {key: 'music-toggle', label: 'PLAY / PAUSE'},
    {key: 'music-next', label: 'NEXT STATION'},
    {key: 'music-streams', label: 'CURATED RADIO'},
    {key: 'music-volume-down', label: 'VOLUME −'},
    {key: 'music-volume-up', label: 'VOLUME +'},
    {key: 'music-stop', label: 'STOP'},
    {key: 'back', label: 'BACK TO DASHBOARD'},
  ];
  if (detailModuleKey === 'radio-streams') {
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
  button?.scrollIntoView({block: 'nearest', inline: 'nearest'});
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
    detailModuleKey = 'radio';
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
  if (document.body.classList.contains('stale')
      || window.latestTelemetry?.source !== 'live'
      || window.latestTelemetry?.sources?.nano !== 'live') return false;
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
  cancelSystemHold();
  const module = focusedModule();
  if (!module || module.key !== key) return;
  const dashboard = $(`#${$('body').dataset.mode}-dashboard`);
  const panel = module.key === 'map' ? $('.map-panel')
    : $('body').dataset.mode === 'camp' ? $(module.selector) : dashboard?.querySelector(module.selector);
  if (!panel) return;
  if (key === 'location') $('#gps-detail').hidden = false;
  if (key === 'conditions') {
    panel.querySelector('.weather-detail').hidden = false;
    panel.querySelector('.road-detail').hidden = false;
  }
  // The detail control replaces the originating module as the sole visible
  // focus target. closeDetail restores the outline to this module.
  clearJoystickFocus();
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
    : key === 'attitude' ? 'calibrate' : key === 'radio' ? 'music-toggle' : 'back');
  requestAnimationFrame(() => {
    window.dashboardMap?.resize();
    window.navball?.refresh();
  });
}
function closeDetail() {
  cancelSystemHold();
  detailNavballCleanup?.();
  if (movedDetailNode && detailRestore) {
    const gpsDetail = movedDetailNode.querySelector('#gps-detail');
    if (gpsDetail) gpsDetail.hidden = true;
    const weatherDetail = movedDetailNode.querySelector('.weather-detail');
    if (weatherDetail) weatherDetail.hidden = true;
    const roadDetail = movedDetailNode.querySelector('.road-detail');
    if (roadDetail) roadDetail.hidden = true;
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
  if (navigationLayer === 'modules' && moduleIndex >= 0) setModuleFocus(moduleIndex);
}
function openCalibration() {
  const rawPitch = wholeDegree(window.latestTelemetry?.attitude?.pitch_deg);
  const rawRoll = wholeDegree(window.latestTelemetry?.attitude?.roll_deg);
  const pitch = rawPitch === null ? null : signedAngleDifference(rawPitch, calibration.pitch);
  const roll = rawRoll === null ? null : signedAngleDifference(rawRoll, calibration.roll);
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
function bindSystemHold(button) {
  let holdTimer = null;
  let activePointer = null;
  const status = $('#system-status');
  const clearHold = (resetStatus = true) => {
    const pointer = activePointer;
    if (pointer === null) return;
    if (holdTimer !== null) window.clearTimeout(holdTimer);
    holdTimer = null;
    activePointer = null;
    if (button.hasPointerCapture(pointer)) button.releasePointerCapture(pointer);
    if (resetStatus && !button.disabled) status.textContent = 'SYSTEM STANDBY';
  };
  button.addEventListener('pointerdown', event => {
    if (button.disabled || event.isPrimary === false || event.button !== 0 || activePointer !== null) return;
    event.preventDefault();
    activePointer = event.pointerId;
    button.setPointerCapture(activePointer);
    status.textContent = 'HOLDING — KEEP PRESSED FOR 2 SECONDS';
    holdTimer = window.setTimeout(() => {
      clearHold(false);
      runSystemAction(button.dataset.systemAction);
    }, 2000);
  });
  const cancelPointer = event => {
    if (event.pointerId === activePointer) clearHold();
  };
  button.addEventListener('pointerup', cancelPointer);
  button.addEventListener('pointercancel', cancelPointer);
  button.addEventListener('lostpointercapture', cancelPointer);
  button.addEventListener('pointermove', event => {
    if (event.pointerId !== activePointer) return;
    const bounds = button.getBoundingClientRect();
    if (event.clientX < bounds.left || event.clientX > bounds.right ||
        event.clientY < bounds.top || event.clientY > bounds.bottom) clearHold();
  });
  button.addEventListener('contextmenu', event => event.preventDefault());
  window.addEventListener('blur', () => clearHold());
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) clearHold();
  });
}
for (const button of document.querySelectorAll('[data-system-action]')) bindSystemHold(button);
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
  else if (navigationLayer === 'modules') focusMode(focusIndex);
});
window.openDetail = openDetail;
window.openCalibration = openCalibration;
async function openMusicStreams() {
  detailModuleKey = 'radio-streams';
  musicStreams = [];
  musicStreamsError = '';
  musicStreamsLoading = true;
  $('#detail-title').textContent = 'CURATED RADIO';
  renderDetailControls('music-player-back');
  showEvent('RADIO / LOADING CURATED STATIONS…');
  try {
    await ensureMusicStreams();
    showEvent(musicStreams.length
      ? 'RADIO / CHOOSE A CURATED STATION AND PRESS TO PLAY'
      : 'RADIO / NO CURATED STATIONS RETURNED', 4000);
  } catch (error) {
    musicStreamsError = error.message || 'Curated stations unavailable';
    showEvent(`RADIO / ${musicStreamsError.toUpperCase()}`, 5000);
  } finally {
    musicStreamsLoading = false;
    if (detailModuleKey === 'radio-streams') renderDetailControls(musicStreams.length ? 'music-stream-0' : 'music-streams-refresh');
  }
}
async function selectMusicStream(stream) {
  detailModuleKey = 'radio';
  $('#detail-title').textContent = 'CURATED RADIO';
  renderDetailControls('music-toggle');
  await startBrowserRadio(stream);
  if (!radioAudio.paused) showEvent(`RADIO / PLAYING ${stream.display_name.toUpperCase()}`, 4000);
}
async function runMusicAction(action) {
  const labels = {prev: 'PREVIOUS STATION', toggle: 'PLAY / PAUSE', next: 'NEXT STATION',
    'volume-down': 'VOLUME −', 'volume-up': 'VOLUME +', stop: 'STOP'};
  if (action === 'prev') await moveRadioStation(-1);
  else if (action === 'next') await moveRadioStation(1);
  else if (action === 'toggle') {
    if (radioAudio.paused) await startBrowserRadio();
    else radioAudio.pause();
  } else if (action === 'stop') radioAudio.pause();
  else if (action === 'volume-down') changeRadioVolume(-0.05);
  else if (action === 'volume-up') changeRadioVolume(0.05);
  showEvent(`RADIO / ${labels[action] || action.toUpperCase()}`, 2000);
}
refreshAmbientLightCalibration();
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
  const setSunset = (value, note) => {
    document.querySelectorAll('#sundown, [data-sundown-value]').forEach(node => { node.textContent = value; });
    document.querySelectorAll('#sundown-note, [data-sundown-note]').forEach(node => { node.textContent = note; });
  };
  const {latitude, longitude} = data.location;
  if (!Number.isFinite(latitude) || !Number.isFinite(longitude) || Math.abs(latitude) > 90 || Math.abs(longitude) > 180) {
    setSunset('—', 'GPS location unavailable');
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
    setSunset('NO SUNSET', 'No sunset on this solar day');
    return;
  }
  const minutes = Math.max(0, Math.ceil((sunset - now) / 60000));
  setSunset(`${Math.floor(minutes / 60)}h ${String(minutes % 60).padStart(2, '0')}m`,
    `${data.source === 'mock' ? 'Demo location · ' : ''}${next ? 'Next sunset' : 'Sunset'} estimate · terrain excluded`);
}
// Quantize the dashboard only; retain the sensor's original telemetry precision.
function wholeDegree(value) {
  return Number.isFinite(value) ? Math.round(value) : null;
}
// Attitude angles wrap at the +/-180 degree boundary. Calibration must use
// the shortest signed difference so crossing that boundary cannot display
// jumps such as -359 degrees instead of +1 degree.
function signedAngleDifference(value, reference) {
  if (!Number.isFinite(value) || !Number.isFinite(reference)) return null;
  const difference = ((value - reference + 180) % 360 + 360) % 360 - 180;
  return wholeDegree(difference);
}
function tiltAlertLevel(pitch, roll) {
  if (!Number.isFinite(pitch) || !Number.isFinite(roll)) return 'normal';
  const degrees = Math.max(Math.abs(pitch), Math.abs(roll));
  return degrees >= 30 ? 'alarm' : degrees >= 20 ? 'caution' : 'normal';
}
function renderGpsDetail(data) {
  const gps = data.gps || {};
  const set = (key, value) => {
    document.querySelectorAll(`[data-gps-value="${key}"]`).forEach(node => {
      node.textContent = value ?? '—';
    });
  };
  const status = data.sources?.gps || gps.status;
  const statusLabels = {live: 'LIVE', connected: 'GPSD LINK', no_fix: 'NO FIX',
    stale: 'STALE', disconnected: 'OFFLINE', unavailable: 'UNAVAILABLE', mock: 'DEMO'};
  set('link', statusLabels[status] || '—');
  set('fix', data.source === 'mock' ? 'DEMO FIX'
    : gps.mode === 3 ? '3D FIX' : gps.mode === 2 ? '2D FIX' : 'NO FIX');
  const used = Number.isFinite(gps.satellites_used) ? gps.satellites_used : null;
  const visible = Number.isFinite(gps.satellites_seen) ? gps.satellites_seen : null;
  set('satellites', used === null && visible === null ? '—'
    : `${used ?? '—'} used · ${visible ?? '—'} visible`);
  const metres = value => Number.isFinite(value) ? `${value.toFixed(1)} m` : '—';
  set('position-error', metres(gps.horizontal_accuracy_m));
  set('latitude-error', metres(gps.latitude_error_m));
  set('longitude-error', metres(gps.longitude_error_m));
  set('vertical-error', metres(gps.vertical_accuracy_m));
  set('hdop', Number.isFinite(gps.dop?.hdop) ? gps.dop.hdop.toFixed(1) : '—');
  set('vdop', Number.isFinite(gps.dop?.vdop) ? gps.dop.vdop.toFixed(1) : '—');
  set('pdop', Number.isFinite(gps.dop?.pdop) ? gps.dop.pdop.toFixed(1) : '—');
  set('speed', Number.isFinite(gps.speed_mps)
    ? `${(gps.speed_mps * 3.6).toFixed(1)} km/h` : '—');
  set('speed-error', Number.isFinite(gps.speed_accuracy_mps)
    ? `${(gps.speed_accuracy_mps * 3.6).toFixed(1)} km/h` : '—');
  set('climb', Number.isFinite(gps.climb_mps)
    ? `${gps.climb_mps >= 0 ? '+' : ''}${gps.climb_mps.toFixed(2)} m/s` : '—');
  set('fix-age', Number.isFinite(gps.age_ms) ? `${(gps.age_ms / 1000).toFixed(1)} s` : '—');
  const gpsTime = typeof gps.gps_time === 'string' ? new Date(gps.gps_time) : null;
  set('gps-time', gpsTime && Number.isFinite(gpsTime.getTime())
    ? `${gpsTime.toISOString().slice(0, 19).replace('T', ' ')} UTC` : '—');
}
const weatherSummaries = {0: 'CLEAR', 1: 'MOSTLY CLEAR', 2: 'PARTLY CLOUDY', 3: 'CLOUDY', 45: 'FOG', 48: 'RIME FOG', 51: 'LIGHT DRIZZLE', 53: 'DRIZZLE', 55: 'HEAVY DRIZZLE', 56: 'FREEZING DRIZZLE', 57: 'FREEZING DRIZZLE', 61: 'LIGHT RAIN', 63: 'RAIN', 65: 'HEAVY RAIN', 66: 'FREEZING RAIN', 67: 'FREEZING RAIN', 71: 'LIGHT SNOW', 73: 'SNOW', 75: 'HEAVY SNOW', 77: 'SNOW GRAINS', 80: 'RAIN SHOWERS', 81: 'RAIN SHOWERS', 82: 'HEAVY RAIN SHOWERS', 85: 'SNOW SHOWERS', 86: 'HEAVY SNOW SHOWERS', 95: 'THUNDERSTORM', 96: 'THUNDERSTORM / HAIL', 99: 'THUNDERSTORM / HAIL'};
let weatherForecastSignature = null;
function renderWeatherDetail(weather) {
  const number = (value, digits = 0) => Number.isFinite(value) ? value.toFixed(digits) : '—';
  const metric = (key, value) => document.querySelectorAll(`[data-weather-detail="${key}"]`).forEach(node => { node.textContent = value; });
  const cardinal = (degrees) => Number.isFinite(degrees)
    ? ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'][Math.round(degrees / 45) % 8] : '—';
  const time = (stamp) => typeof stamp === 'string' ? stamp.slice(11, 16) : '—';
  const dayName = (stamp, index) => {
    if (index === 0) return 'TODAY';
    if (index === 1) return 'TOMORROW';
    const date = typeof stamp === 'string' ? new Date(`${stamp}T12:00:00`) : null;
    return date && Number.isFinite(date.getTime()) ? date.toLocaleDateString([], {weekday: 'long'}).toUpperCase() : 'FORECAST';
  };
  const status = weather.status === 'live' ? 'LIVE' : weather.status === 'mock' ? 'DEMO'
    : weather.status === 'stale' ? 'STALE' : weather.status === 'waiting_location' ? 'WAITING FOR GPS' : 'UNAVAILABLE';
  metric('status', status);
  metric('headline', weather.summary || 'Conditions unavailable');
  metric('location', weather.location_source === 'gps' ? 'GPS LOCATION'
    : weather.location_source === 'last_gps' ? 'LAST GPS LOCATION'
    : weather.location_source === 'default' ? 'CONFIGURED DEFAULT' : 'SIMULATED LOCATION');
  metric('updated', weather.updated_at ? `FEED CHECKED ${ageLabel(weather.updated_at)} · MODEL TIME ${time(weather.observed_at)}` : 'NO FEED TIME');
  metric('feels', `${number(weather.apparent_temperature_c)} °C`);
  metric('humidity', `${number(weather.humidity_pct)}%`);
  metric('cloud', `${number(weather.cloud_cover_pct)}%`);
  metric('pressure', Number.isFinite(weather.pressure_hpa) ? `${number(weather.pressure_hpa, 1)} hPa` : '—');
  metric('visibility', Number.isFinite(weather.visibility_m) ? `${number(weather.visibility_m / 1000, 1)} km` : '—');
  metric('uv', number(weather.uv_index, 1));
  metric('precip', `${number(weather.precipitation_mm, 1)} / ${number(weather.rain_mm, 1)} / ${number(weather.showers_mm, 1)} mm`);
  metric('snow', `${number(weather.snowfall_cm, 1)} cm`);
  metric('wind', `${number(weather.wind_speed_kmh)} km/h ${cardinal(weather.wind_direction_deg)} · G ${number(weather.wind_gust_kmh)} km/h`);

  const forecastSignature = JSON.stringify([weather.daily_forecast, weather.hourly_forecast]);
  const renderForecast = forecastSignature !== weatherForecastSignature;
  if (renderForecast) weatherForecastSignature = forecastSignature;
  if (renderForecast) document.querySelectorAll('[data-weather-list="daily"]').forEach(container => {
    container.replaceChildren();
    (Array.isArray(weather.daily_forecast) ? weather.daily_forecast : []).forEach((day, index) => {
      const card = document.createElement('article');
      card.className = 'weather-day-card';
      const heading = document.createElement('h4'); heading.textContent = dayName(day.date, index); card.append(heading);
      const condition = document.createElement('p'); condition.textContent = weatherSummaries[day.weather_code] || 'CONDITIONS'; card.append(condition);
      const range = document.createElement('strong'); range.textContent = `${number(day.high_c)}° / ${number(day.low_c)}°C`; card.append(range);
      const details = document.createElement('small');
      details.textContent = `FEELS ${number(day.feels_like_high_c)}° / ${number(day.feels_like_low_c)}° · RAIN ${number(day.precipitation_probability_pct)}% · ${number(day.precipitation_mm, 1)} mm · SNOW ${number(day.snowfall_cm, 1)} cm`;
      card.append(details);
      const sun = document.createElement('small'); sun.textContent = `SUN ${time(day.sunrise)} – ${time(day.sunset)} · UV ${number(day.uv_index_max, 1)} · GUST ${number(day.wind_gust_max_kmh)} km/h`;
      card.append(sun); container.append(card);
    });
    if (!container.childElementCount) { const empty = document.createElement('p'); empty.className = 'weather-empty'; empty.textContent = 'Forecast data unavailable'; container.append(empty); }
  });
  if (renderForecast) document.querySelectorAll('[data-weather-list="hourly"]').forEach(container => {
    container.replaceChildren();
    (Array.isArray(weather.hourly_forecast) ? weather.hourly_forecast : []).forEach(hour => {
      const card = document.createElement('article'); card.className = 'weather-hour-card';
      const heading = document.createElement('h4'); heading.textContent = time(hour.time); card.append(heading);
      const condition = document.createElement('span'); condition.textContent = weatherSummaries[hour.weather_code] || '—'; card.append(condition);
      const temperature = document.createElement('strong'); temperature.textContent = `${number(hour.temperature_c)}°`; card.append(temperature);
      const details = document.createElement('small'); details.textContent = `${number(hour.precipitation_probability_pct)}% · ${number(hour.wind_speed_kmh)} km/h ${cardinal(hour.wind_direction_deg)}`; card.append(details);
      const visibility = document.createElement('small'); visibility.textContent = `VIS ${Number.isFinite(hour.visibility_m) ? `${number(hour.visibility_m / 1000, 1)} km` : '—'} · UV ${number(hour.uv_index, 1)}`; card.append(visibility);
      container.append(card);
    });
    if (!container.childElementCount) { const empty = document.createElement('p'); empty.className = 'weather-empty'; empty.textContent = 'Hourly forecast data unavailable'; container.append(empty); }
  });
}
function render(data) {
  if (data.schema_version !== 1 || !['mock', 'live'].includes(data.source)) throw new Error('Unknown telemetry contract');
  const live = data.source === 'live';
  window.latestTelemetry = data;
  renderGpsDetail(data);
  const weather = data.weather || {};
  renderWeatherDetail(weather);
  const road = data.road_conditions || {};
  const weatherStatus = weather.status === 'live' || weather.status === 'mock';
  const setWeather = (key, value) => document.querySelectorAll(`[data-weather="${key}"]`).forEach(node => { node.textContent = value; });
  const temperature = Number.isFinite(weather.temperature_c) ? `${Math.round(weather.temperature_c)}` : '—';
  const wind = Number.isFinite(weather.wind_speed_kmh)
    ? `${Math.round(weather.wind_speed_kmh)} km/h · G ${Number.isFinite(weather.wind_gust_kmh) ? Math.round(weather.wind_gust_kmh) : '—'}` : '—';
  setWeather('summary', weather.status === 'stale' ? `STALE · ${weather.summary || 'CONDITIONS'}`
    : weatherStatus ? (weather.summary || 'CONDITIONS') : 'NO FEED');
  setWeather('temperature', temperature);
  setWeather('wind', wind);
  setWeather('source', weather.location_source === 'default' ? 'CONFIGURED DEFAULT · OPEN-METEO'
    : weather.location_source === 'gps' ? 'GPS LOCATION · OPEN-METEO'
      : weather.location_source === 'last_gps' ? 'LAST GPS LOCATION · OPEN-METEO'
        : weatherStatus ? 'SIMULATED' : 'WAITING FOR DATA');
  if (weather.updated_at) document.querySelectorAll('[data-weather="source"]').forEach(node => {
    node.textContent += ` · CHECKED ${ageLabel(weather.updated_at)}`;
  });
  const upcoming = Array.isArray(weather.hourly_forecast) ? weather.hourly_forecast.slice(0, 3) : [];
  const chances = upcoming.map(hour => hour.precipitation_probability_pct).filter(Number.isFinite);
  const gusts = upcoming.map(hour => hour.wind_gust_kmh).filter(Number.isFinite);
  const maxChance = chances.length ? `${Math.round(Math.max(...chances))}%` : '—';
  const maxGust = gusts.length ? `${Math.round(Math.max(...gusts))} KM/H` : '—';
  const lowVisibility = upcoming.some(hour => Number.isFinite(hour.visibility_m) && hour.visibility_m < 1000);
  const outlook = upcoming.length ? `${weather.status === 'stale' ? 'STALE · ' : ''}NEXT 3H · PRECIP ${maxChance} · GUST ${maxGust}${lowVisibility ? ' · LOW VIS' : ''}` : 'NEXT 3H · NO FORECAST';
  document.querySelectorAll('[data-weather="outlook"]').forEach(node => { node.textContent = outlook; });
  const roadCondition = road.status === 'not_configured' ? 'KEY REQUIRED'
    : road.status === 'stale' ? `STALE · ${road.condition || 'NO REPORT'}`
      : road.status === 'unavailable' ? 'FEED UNAVAILABLE'
      : road.status === 'waiting_location' ? 'WAITING FOR LOCATION'
      : road.report_status === 'no_report_nearby' ? 'NO REPORT NEARBY'
        : road.status === 'mock' ? (road.condition || 'SIMULATED')
          : road.status === 'live' ? (road.condition || 'NO REPORT')
            : road.diagnostics?.phase === 'fetching' ? 'FETCHING' : 'WAITING';
  document.querySelectorAll('[data-road="condition"]').forEach(node => { node.textContent = roadCondition; });
  const roadSource = road.status === 'not_configured' ? 'ADD OVRLAND_511_API_KEY'
    : ['unavailable', 'stale'].includes(road.status) && road.diagnostics?.last_error
      ? `${road.diagnostics.last_error.message} · RETRYING`
    : road.location_source === 'default' ? `${road.location_name || 'CONFIGURED LOCATION'} · 511 ALBERTA`
    : road.location_source === 'gps' ? 'GPS LOCATION · 511 ALBERTA'
      : road.location_source === 'last_gps' ? 'LAST GPS LOCATION · 511 ALBERTA'
        : road.status === 'mock' ? 'SIMULATED' : '511 ALBERTA';
  document.querySelectorAll('[data-road="source"]').forEach(node => { node.textContent = roadSource; });
  if (road.last_updated || road.updated_at) document.querySelectorAll('[data-road="source"]').forEach(node => {
    node.textContent += road.last_updated ? ` · REPORT ${ageLabel(road.last_updated, true)}` : '';
    if (road.status === 'stale' && road.updated_at) node.textContent += ` · CHECKED ${ageLabel(road.updated_at)}`;
  });
  const roadDetail = (key, value) => document.querySelectorAll(`[data-road-detail="${key}"]`).forEach(node => { node.textContent = value; });
  const list = value => Array.isArray(value) ? value.filter(Boolean).join(', ') : typeof value === 'string' ? value : '';
  roadDetail('roadway', [road.roadway, road.area].filter(Boolean).join(' · ') || '—');
  roadDetail('location', road.location_description || '—');
  roadDetail('condition', road.condition || '—');
  roadDetail('secondary', list(road.secondary_conditions) || '—');
  roadDetail('visibility', road.visibility || '—');
  roadDetail('distance', Number.isFinite(road.distance_km) ? `${road.distance_km.toFixed(1)} km` : '—');
  roadDetail('reported', road.last_updated ? ageLabel(road.last_updated, true) : 'TIME UNKNOWN');
  roadDetail('checked', road.updated_at ? ageLabel(road.updated_at) : 'TIME UNKNOWN');
  roadDetail('note', road.status === 'stale' ? 'Cached report; the latest feed check failed.'
    : road.report_status === 'no_report_nearby' ? 'No 511 road report within the configured 35 km radius.'
      : road.status === 'not_configured' ? 'Add a 511 Alberta developer key to enable reports.'
        : road.status === 'mock' ? 'Simulated demonstration report.'
        : road.report_status === 'reported' ? 'Nearest reported segment, not necessarily your current road.' : 'No current road report available.');
  renderSundown(data);
  const rawPitch = wholeDegree(data.attitude.pitch_deg);
  const rawRoll = wholeDegree(data.attitude.roll_deg);
  const pitch = rawPitch === null ? null : signedAngleDifference(rawPitch, calibration.pitch);
  const roll = rawRoll === null ? null : signedAngleDifference(rawRoll, calibration.roll);
  const tiltAlert = tiltAlertLevel(pitch, roll);
  for (const field of document.querySelectorAll('[data-value]')) {
    const value = field.dataset.value.split('.').reduce((item, key) => item?.[key], data);
    if (field.dataset.value === 'attitude.pitch_deg') field.textContent = pitch === null ? '—' : String(pitch);
    else if (field.dataset.value === 'attitude.roll_deg') field.textContent = roll === null ? '—' : String(roll);
    else if (field.dataset.value === 'location.altitude_m') field.textContent = Number.isFinite(value) ? String(Math.round(value)) : '—';
    else if (field.dataset.value === 'location.heading_deg') field.textContent = Number.isFinite(value)
      ? String(((Math.round(value) % 360) + 360) % 360) : '—';
    else if (field.dataset.value === 'vehicle.speed_mph') field.textContent = Number.isFinite(value)
      ? String(Math.round(value * 1.60934)) : '—';
    else field.textContent = value ?? '—';
  }
  $('#data-mode-label').hidden = live;
  $('#data-mode-label').textContent = live ? '' : 'SIMULATED DATA';
  $('#obd-label').textContent = live ? 'OBD / UNAVAILABLE' : 'OBD / DEMO';
  const gpsStatusLabels = {live: 'FIX LIVE', connected: 'GPSD LINK', no_fix: 'NO FIX', stale: 'FIX STALE', disconnected: 'OFFLINE', unavailable: 'UNAVAILABLE'};
  $('#gps-label').textContent = live
    ? (data.sources.gps === 'connected' ? 'GPSD LINK / WAITING FOR FIX'
      : `GPS / ${gpsStatusLabels[data.sources.gps] || data.sources.gps.toUpperCase().replaceAll('_', ' ')}`)
    : 'GPS / DEMO';
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
    field.textContent = source === 'gps'
      ? (gpsStatusLabels[status] || status.toUpperCase().replaceAll('_', ' '))
      : status.toUpperCase().replace('_', ' ');
    field.classList.toggle('source-connected', source === 'gps' ? status === 'live' : ['live', 'connected'].includes(status));
  }
  document.querySelectorAll('[data-gauge]').forEach(gauge => {
    const rawValue = gauge.dataset.gauge.split('.').reduce((item, key) => item?.[key], data);
    const value = gauge.dataset.gauge === 'vehicle.speed_mph' && Number.isFinite(rawValue)
      ? rawValue * 1.60934 : rawValue;
    const percent = Number.isFinite(value) ? Math.max(0, Math.min(100, value / Number(gauge.dataset.max) * 100)) : 0;
    gauge.querySelector('.gauge-fill').style.strokeDasharray = `${percent} 100`;
  });
  window.dashboardMap?.telemetry(data);
  window.navball?.update(pitch, roll);
  $('#dtc').textContent = data.vehicle.dtc_count == null ? 'DTC UNAVAILABLE' : `${data.vehicle.dtc_count} DTC / SIMULATED`;
  if (navigationLayer === 'tabs' && $('#detail-overlay').hidden && Date.now() >= eventHoldUntil) {
    $('#event').textContent = '';
  }
  joystick(data);
  lastReceived = Date.now();
  document.body.classList.remove('stale');
  $('#connection').textContent = 'DATA FEED CONNECTED';
}
function stale() {
  document.body.classList.add('stale');
  window.latestTelemetry = null;
  cancelSystemHold();
  $('#connection').textContent = 'FEED LOST / RECONNECTING';
  document.querySelectorAll('[data-road="source"]').forEach(node => {
    node.textContent = 'FEED LOST · LAST 511 REPORT MAY BE STALE';
  });
  document.querySelectorAll('[data-road-detail="note"]').forEach(node => {
    node.textContent = 'FEED LOST — cached values below are not current. Waiting for a fresh telemetry update.';
  });
  for (const field of document.querySelectorAll('[data-value]')) field.textContent = '—';
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
  document.querySelectorAll('#sundown, [data-sundown-value]').forEach(node => { node.textContent = '—'; });
  document.querySelectorAll('#sundown-note, [data-sundown-note]').forEach(node => { node.textContent = 'Location feed disconnected'; });
  $('#joy-status').textContent = 'DISCONNECTED';
  $('#joy-button').textContent = '—';
  joySession = null;
  renderGpsDetail({gps: {}, sources: {gps: 'unavailable'}, source: 'live'});
  renderWeatherDetail({status: 'stale'});
  document.querySelectorAll('[data-weather]').forEach(node => { node.textContent = '—'; });
  document.querySelectorAll('[data-road="condition"]').forEach(node => { node.textContent = 'FEED LOST'; });
  document.querySelectorAll('[data-road="source"]').forEach(node => { node.textContent = 'RECONNECTING'; });
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
document.addEventListener('visibilitychange', () => { joySession = null; cancelSystemHold(); });
