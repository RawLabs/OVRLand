'use strict';
// A shaded sphere, with pitch/roll applied to its surface coordinates before projection.
// No heading/yaw is invented: the meridians are attitude reference marks only.
(() => {
  const size = 320;
  const center = size / 2;
  const radius = 124;
  const rad = Math.PI / 180;
  const cautionThreshold = 20;
  const alarmThreshold = 30;
  const geometry = [];
  const buffer = document.createElement('canvas');
  buffer.width = buffer.height = size;
  const bufferContext = buffer.getContext('2d');
  const pixels = bufferContext.createImageData(size, size);
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const nx = (x - center) / radius;
      const ny = (center - y) / radius;
      const depth = 1 - nx * nx - ny * ny;
      if (depth < 0) continue;
      const nz = Math.sqrt(depth);
      const light = Math.max(0, -.32 * nx + .42 * ny + .85 * nz);
      const shade = (.33 + .67 * light) * (.55 + .45 * Math.sqrt(nz));
      const gloss = Math.pow(Math.max(0, -.3 * nx + .38 * ny + .875 * nz), 36) * 24;
      geometry.push({index: (y * size + x) * 4, x: nx, y: ny, z: nz, shade, gloss});
    }
  }
  function project(latitude, longitude, cp, sp, cr, sr) {
    const cosLat = Math.cos(latitude * rad);
    const wx = cosLat * Math.sin(longitude * rad);
    const wy = Math.sin(latitude * rad);
    const wz = cosLat * Math.cos(longitude * rad);
    const y = wy * cp - wz * sp;
    return {x: center + radius * (wx * cr + y * sr),
      y: center - radius * (-wx * sr + y * cr), z: wy * sp + wz * cp};
  }
  function draw(canvas, pitch, roll, valid) {
    const ctx = canvas.getContext('2d');
    const tilt = valid ? Math.max(Math.abs(pitch), Math.abs(roll)) : 0;
    const alert = tilt >= alarmThreshold ? 'alarm' : (tilt >= cautionThreshold ? 'caution' : 'normal');
    canvas.dataset.tiltAlert = alert;
    ctx.clearRect(0, 0, size, size);
    const metal = ctx.createLinearGradient(40, 20, 280, 300);
    metal.addColorStop(0, '#85908a');
    metal.addColorStop(.3, '#2b3330');
    metal.addColorStop(.7, '#111715');
    metal.addColorStop(1, '#59625b');
    ctx.beginPath(); ctx.arc(center, center, 137, 0, Math.PI * 2);
    ctx.fillStyle = '#080c0a'; ctx.fill();
    ctx.lineWidth = 11; ctx.strokeStyle = metal; ctx.stroke();
    if (alert !== 'normal') {
      ctx.beginPath(); ctx.arc(center, center, 143, 0, Math.PI * 2);
      ctx.lineWidth = 4;
      ctx.strokeStyle = alert === 'alarm' ? '#ef554d' : '#f4c34e';
      ctx.stroke();
    }
    const p = pitch * rad;
    const r = -roll * rad;
    const cp = Math.cos(p), sp = Math.sin(p), cr = Math.cos(r), sr = Math.sin(r);
    for (const point of geometry) {
      const viewY = point.x * sr + point.y * cr;
      const worldX = point.x * cr - point.y * sr;
      const up = viewY * cp + point.z * sp;
      const forward = -viewY * sp + point.z * cp;
      const latitude = Math.asin(Math.max(-1, Math.min(1, up))) / rad;
      const longitude = Math.atan2(worldX, forward) / rad;
      const latitudeGrid = Math.abs(latitude - Math.round(latitude / 10) * 10);
      const longitudeGrid = Math.abs(longitude - Math.round(longitude / 30) * 30);
      let color = up >= 0 ? [45, 117, 159] : [143, 88, 46];
      if (Math.abs(latitude) < .55) color = [237, 230, 206];
      else if (latitudeGrid < .32 || longitudeGrid < .3) color = up >= 0 ? [141, 180, 191] : [193, 159, 115];
      if (!valid) color = [43, 51, 47];
      const i = point.index;
      pixels.data[i] = color[0] * point.shade + point.gloss;
      pixels.data[i + 1] = color[1] * point.shade + point.gloss;
      pixels.data[i + 2] = color[2] * point.shade + point.gloss;
      pixels.data[i + 3] = 255;
    }
    bufferContext.putImageData(pixels, 0, 0);
    ctx.drawImage(buffer, 0, 0);
    if (valid) {
      // Labels follow the projected latitude rings around the ball.
      ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
      for (const latitude of [-60, -30, 30, 60]) {
        for (const longitude of [-30, 30]) {
          const point = project(latitude, longitude, cp, sp, cr, sr);
          if (point.z < .3) continue;
          const tangent = project(latitude, longitude + .5, cp, sp, cr, sr);
          ctx.save(); ctx.translate(point.x, point.y);
          ctx.rotate(Math.atan2(tangent.y - point.y, tangent.x - point.x));
          ctx.font = `bold ${14 + point.z * 5}px monospace`;
          ctx.lineWidth = 3; ctx.strokeStyle = '#14201bd9'; ctx.fillStyle = '#eee5ce';
          const label = latitude > 0 ? `+${latitude}` : String(latitude);
          ctx.strokeText(label, 0, 0); ctx.fillText(label, 0, 0); ctx.restore();
        }
      }
    }
    // Fixed bank scale and vehicle reference remain in front of the moving ball.
    ctx.save(); ctx.translate(center, center);
    for (const angle of [-60, -45, -30, -20, -10, 0, 10, 20, 30, 45, 60]) {
      ctx.save(); ctx.rotate(angle * rad);
      ctx.beginPath(); ctx.moveTo(0, -143); ctx.lineTo(0, angle % 30 === 0 ? -156 : -150);
      const magnitude = Math.abs(angle);
      ctx.strokeStyle = angle === 0 ? '#f2993a'
        : magnitude === alarmThreshold ? '#ef554d'
          : magnitude === cautionThreshold ? '#f4c34e' : '#bbb9a6';
      ctx.lineWidth = magnitude === alarmThreshold ? 4 : magnitude === cautionThreshold ? 3
        : angle === 0 ? 3 : 1.5;
      ctx.stroke(); ctx.restore();
    }
    if (valid) {
      ctx.save(); ctx.rotate(r);
      ctx.beginPath(); ctx.moveTo(0, -131); ctx.lineTo(-6, -120); ctx.lineTo(6, -120); ctx.closePath();
      ctx.fillStyle = '#f5e6c4'; ctx.fill(); ctx.restore();
      ctx.beginPath(); ctx.moveTo(-58, 0); ctx.lineTo(-18, 0); ctx.lineTo(-9, 9);
      ctx.moveTo(58, 0); ctx.lineTo(18, 0); ctx.lineTo(9, 9);
      ctx.strokeStyle = '#16180f'; ctx.lineWidth = 8; ctx.stroke();
      ctx.strokeStyle = '#ffb34d'; ctx.lineWidth = 4; ctx.stroke();
      ctx.beginPath(); ctx.arc(0, 0, 4, 0, Math.PI * 2); ctx.fillStyle = '#ffb34d'; ctx.fill();
    } else {
      ctx.fillStyle = '#a8afa4'; ctx.font = 'bold 20px monospace'; ctx.textAlign = 'center';
      ctx.fillText('NO ATTITUDE', 0, 5);
    }
    if (alert !== 'normal') {
      const alarm = alert === 'alarm';
      ctx.fillStyle = alarm ? '#5c1818e8' : '#584818e8';
      ctx.fillRect(-72, 103, 144, 20);
      ctx.fillStyle = alarm ? '#ff756d' : '#ffd766';
      ctx.font = 'bold 16px monospace'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
      ctx.fillText(alarm ? 'TILT ALARM 30°+' : 'TILT CAUTION 20°+', 0, 113);
    }
    ctx.restore();
    const alertText = alert === 'alarm' ? ' Red tilt alarm at 30 degrees or more.'
      : alert === 'caution' ? ' Amber tilt caution at 20 degrees or more.' : '';
    canvas.setAttribute('aria-label', valid ? `Tilt-Oh-Shit meter: pitch ${pitch} degrees, roll ${roll} degrees.${alertText} See source label for calibration status.` : 'Tilt-Oh-Shit meter: attitude unavailable');
  }
  const balls = [...document.querySelectorAll('canvas.navball')];
  let attitude = {pitch: 0, roll: 0, valid: false};
  function refresh() {
    for (const ball of balls) {
      if (!ball.closest('[hidden]')) draw(ball, attitude.pitch, attitude.roll, attitude.valid);
    }
  }
  window.navball = {
    update(pitch, roll) {
      const valid = Number.isFinite(pitch) && Number.isFinite(roll);
      if (valid === attitude.valid && (!valid || (pitch === attitude.pitch && roll === attitude.roll))) return;
      attitude = {pitch: valid ? pitch : 0, roll: valid ? roll : 0, valid};
      refresh();
    },
    refresh,
    clear() {this.update(null, null);}
  };
  refresh();
})();
