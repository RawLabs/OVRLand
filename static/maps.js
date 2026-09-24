'use strict';
(() => {
  const $ = selector => document.querySelector(selector);
  const gaiaURL = 'https://www.gaiagps.com/map/?loc=7.5/-114.7699/49.9266';
  const earthURL = 'https://earth.google.com/web/';
  let source = 'osm';
  let offlineInfo = null;
  let offlineLayer = null;
  let position = null;
  let marker = null;
  let hasCentered = false;
  let sampleSource = null;
  let tileError = false;
  let map;
  let osm;
  let earthWindow = null;
  let earthWindowWatch = null;
  if (typeof L !== 'undefined') {
    map = L.map('street-map', {zoomControl: true}).setView([49.9266, -114.7699], 8);
    osm = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19, updateWhenIdle: true, keepBuffer: 1,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
    });
    osm.on('tileerror', () => {
      if (source === 'osm') {tileError = true; $('#map-location').textContent = 'Map tiles unavailable · check internet or use Offline';}
    });
    map.on('moveend', () => {
      if (source === 'osm') {
        const c = map.getCenter();
        $('#map-open').href = `https://www.openstreetmap.org/#map=${map.getZoom()}/${c.lat}/${c.lng}`;
      }
    });
  }
  function updateStatus() {
    if (source === 'gaia') {
      $('#map-location').textContent = 'Gaia website · internet required';
      return;
    }
    if (source === 'earth') {
      $('#map-location').textContent = 'Google Earth discovery window · internet required';
      return;
    }
    const prefix = source === 'offline' ? 'Offline' : 'Online';
    $('#map-location').textContent = `${prefix} · ${position ? (sampleSource === 'mock' ? 'demo location' : 'GPS position') : 'browse map / GPS unavailable'}`;
  }
  function resize() {
    requestAnimationFrame(() => map?.invalidateSize({pan: false}));
  }
  function closeEarth() {
    if (earthWindow && !earthWindow.closed) earthWindow.close();
    earthWindow = null;
    if (earthWindowWatch) window.clearInterval(earthWindowWatch);
    earthWindowWatch = null;
  }
  function openEarth() {
    closeEarth();
    const bounds = $('#street-map').getBoundingClientRect();
    const features = [
      'popup=yes',
      `width=${Math.round(bounds.width)}`,
      `height=${Math.round(bounds.height)}`,
      `left=${Math.round(window.screenX + bounds.left)}`,
      `top=${Math.round(window.screenY + bounds.top)}`,
    ].join(',');
    earthWindow = window.open(earthURL, 'ovrland-earth-discovery', features);
    if (!earthWindow) {
      choose('osm');
      window.dashboardEvent?.('Google Earth was blocked. Allow popups for OVRLand, then try again.', 5000);
      return;
    }
    earthWindowWatch = window.setInterval(() => {
      if (earthWindow?.closed) {
        earthWindow = null;
        window.clearInterval(earthWindowWatch);
        earthWindowWatch = null;
        if (source === 'earth') choose('osm');
      }
    }, 500);
  }
  function choose(next) {
    if (next !== 'earth') closeEarth();
    source = next;
    tileError = false;
    document.querySelectorAll('[data-map]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.map === next)));
    $('#gaia-panel').hidden = next !== 'gaia';
    $('#offline-panel').hidden = next !== 'offline' || Boolean(offlineInfo?.available && map);
    $('#street-map').hidden = next === 'gaia' || (next === 'offline' && !offlineInfo?.available);
    $('#offline-attribution').hidden = next !== 'offline' || !offlineInfo?.available;
    $('#map-center').disabled = !position || next === 'gaia' || next === 'earth' || !map || (next === 'offline' && !offlineInfo?.available);
    $('#map-open').hidden = next === 'offline';
    $('#map-open').href = next === 'gaia' ? gaiaURL : next === 'earth' ? earthURL : 'https://www.openstreetmap.org/';
    $('#map-open').textContent = next === 'gaia' ? 'OPEN GAIA ↗' : next === 'earth' ? 'OPEN EARTH ↗' : 'OPEN MAP ↗';
    if (map) {
      // Hidden sources make no tile requests; offline mode never falls back to the internet.
      if (map.hasLayer(osm)) map.removeLayer(osm);
      if (offlineLayer && map.hasLayer(offlineLayer)) map.removeLayer(offlineLayer);
      map.setMaxBounds(null);
      if (next !== 'gaia') map.invalidateSize({pan: false});
      map.setMinZoom(0);
      map.setMaxZoom(19);
      if (next === 'osm') osm.addTo(map);
      if (next === 'offline' && offlineInfo?.available) {
        const [west, south, east, north] = offlineInfo.bounds;
        const bounds = L.latLngBounds([south, west], [north, east]);
        map.setMinZoom(offlineInfo.minzoom);
        map.setMaxZoom(offlineInfo.maxzoom);
        map.setMaxBounds(bounds);
        map.fitBounds(bounds, {animate: false});
        offlineLayer.addTo(map);
      }
    }
    updateStatus();
    resize();
    if (next === 'earth') openEarth();
  }
  async function checkOffline() {
    try {
      const response = await fetch('/api/maps/offline');
      if (!response.ok) throw new Error('Map configuration unavailable');
      offlineInfo = await response.json();
      $('#offline-note').textContent = offlineInfo.available ? `Stored on this Pi: ${offlineInfo.name}` : offlineInfo.message;
      if (offlineInfo.available && map) {
        if (offlineLayer && map.hasLayer(offlineLayer)) map.removeLayer(offlineLayer);
        offlineLayer = L.tileLayer('/api/maps/tiles/{z}/{x}/{y}', {
          minZoom: offlineInfo.minzoom, maxZoom: offlineInfo.maxzoom,
          noWrap: true, updateWhenIdle: true, keepBuffer: 1
        });
        offlineLayer.on('tileerror', () => {
          if (source === 'offline') {tileError = true; $('#map-location').textContent = 'No saved tile at this location / zoom';}
        });
        // Treat package metadata as text, never inject its attribution as HTML.
        $('#offline-attribution').textContent = offlineInfo.attribution;
      }
    } catch {
      offlineInfo = {available: false};
      $('#offline-note').textContent = 'Cannot check maps stored on the Pi. Check the local app connection.';
    }
    if (source === 'offline' || (source === 'osm' && !navigator.onLine && offlineInfo?.available)) choose('offline');
  }
  document.querySelectorAll('[data-map]').forEach(button => button.addEventListener('click', () => choose(button.dataset.map)));
  $('#offline-retry').addEventListener('click', checkOffline);
  $('#map-center').addEventListener('click', () => {
    window.dashboardMap?.center();
  });
  window.addEventListener('offline', () => {
    if (source === 'osm' && offlineInfo?.available) choose('offline');
    else if (source === 'osm') $('#map-location').textContent = 'Internet unavailable · no offline map installed';
  });
  window.dashboardMap = {
    resize,
    source: () => source,
    choose,
    canCenter: () => Boolean(position && map && source !== 'gaia' && source !== 'earth'
      && (source !== 'offline' || offlineInfo?.available)),
    center() {
      if (!this.canCenter()) return false;
      map.setView(position, Math.min(source === 'offline' ? offlineInfo.maxzoom : 19, 13));
      return true;
    },
    restoreDashboard() { resize(); },
    telemetry(data) {
      const {latitude, longitude} = data.location;
      if (!Number.isFinite(latitude) || !Number.isFinite(longitude) || Math.abs(latitude) > 90 || Math.abs(longitude) > 180) {
        this.clearLocation();
        return;
      }
      const moved = !position || position[0] !== latitude || position[1] !== longitude;
      position = [latitude, longitude];
      sampleSource = data.source;
      $('#map-center').disabled = source === 'gaia' || source === 'earth' || !map || (source === 'offline' && !offlineInfo?.available);
      if (map) {
        if (!marker) marker = L.circleMarker(position, {radius: 6, color: '#f2993a', fillColor: '#0b0d0c', fillOpacity: 1, weight: 3}).addTo(map);
        else if (moved) marker.setLatLng(position);
        if (!hasCentered && source === 'osm') {map.setView(position, 12); hasCentered = true;}
      }
      // Preserve tile-error status during the high-frequency telemetry stream.
      if (!tileError) updateStatus();
    },
    clearLocation() {
      position = null;
      $('#map-center').disabled = true;
      if (marker && map) {map.removeLayer(marker); marker = null;}
      if (!tileError) updateStatus();
    }
  };
  if (!map) {
    $('#street-map').textContent = 'Map controls could not load. Refresh the dashboard.';
  }
  choose('osm');
  checkOffline();
})();
