"""OVRLand: independent adapters -> telemetry snapshot -> HTTP/WebSocket UI."""
import asyncio
import copy
import json
import ipaddress
import os
import signal
import shutil
import subprocess
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask
from adapters.nano import Nano
from adapters.nano_ble import NanoBLE
from adapters.maps import OfflineMap
from adapters.gpsd import GPSD
from adapters.weather import Weather
from adapters.alberta_511 import Alberta511
from adapters.radio_catalog import RadioCatalog
from adapters.radio_metadata import RadioMetadata
from adapters.ambient_light import AmbientLightCalibration, CONDITIONS, brightness
from adapters.network import Network
from adapters.recording import Recording

ROOT = Path(__file__).resolve().parent
FIXTURE = json.loads((ROOT / 'static/mock.json').read_text())
ambient_light_calibration = AmbientLightCalibration(ROOT / 'config' / 'ambient_light_calibration.json')
offline_map = OfflineMap(os.environ.get('OVRLAND_MAP_FILE', str(ROOT / 'maps/offline.mbtiles')))
gps = GPSD(os.environ.get('OVRLAND_GPSD_HOST', '127.0.0.1'),
           int(os.environ.get('OVRLAND_GPSD_PORT', '2947')))
WEATHER_LATITUDE = float(os.environ.get('OVRLAND_WEATHER_LATITUDE', '51.04'))
WEATHER_LONGITUDE = float(os.environ.get('OVRLAND_WEATHER_LONGITUDE', '-114.07'))
weather = Weather(WEATHER_LATITUDE, WEATHER_LONGITUDE)
road_conditions = Alberta511(os.environ.get('OVRLAND_511_API_KEY', '').strip(),
                             WEATHER_LATITUDE, WEATHER_LONGITUDE)
network = Network(
    host=os.environ.get('OVRLAND_NETWORK_CHECK_HOST', '1.1.1.1'),
    port=int(os.environ.get('OVRLAND_NETWORK_CHECK_PORT', '443')),
)
radio_presets = json.loads((ROOT / 'config' / 'radio_presets.json').read_text())
radio_catalog = RadioCatalog(radio_presets)
radio_metadata = RadioMetadata(radio_presets)
recordings = Recording(os.environ.get(
    'OVRLAND_RECORDING_DIR', str(Path.home() / '.local/state/ovrland/recordings')))
MODE = os.environ.get('OVRLAND_MODE', 'live')
if MODE not in ('mock', 'live'):
    raise ValueError('OVRLAND_MODE must be mock or live')
NANO_TRANSPORT = os.environ.get('OVRLAND_NANO_TRANSPORT', 'usb')
if NANO_TRANSPORT == 'usb':
    nano = Nano(os.environ.get('OVRLAND_NANO_DEVICE',
                               '/dev/serial/by-id/usb-Arduino_Nano_33_BLE_6645321B7A5D0D0F-if00'))
elif NANO_TRANSPORT == 'ble':
    nano = NanoBLE(os.environ.get('OVRLAND_NANO_BLE_ADDRESS'))
else:
    raise ValueError('OVRLAND_NANO_TRANSPORT must be usb or ble')

# The desktop launcher polls this value.  Keeping the browser-window mode here
# lets the dashboard request a real Chromium kiosk/window transition instead of
# confusing Chromium kiosk mode with the webpage Fullscreen API.
window_mode = 'fullscreen'


def power_off_pi():
    command = shutil.which('systemctl') or shutil.which('shutdown')
    if not command:
        return False
    args = [command, 'poweroff'] if command.endswith('systemctl') else [command, '-h', 'now']
    try:
        process = subprocess.Popen(args, start_new_session=True, close_fds=True)
    except OSError:
        return False
    # A poweroff command normally remains running briefly while the host shuts
    # down. Detect immediate command failures without waiting on the shutdown.
    return process.poll() in (None, 0)


def stop_app():
    threading.Timer(.25, lambda: os.kill(os.getpid(), signal.SIGTERM)).start()


def local_dashboard_request(request):
    """Accept state-changing controls only from the browser running on this Pi."""
    try:
        peer = ipaddress.ip_address(request.client.host) if request.client else None
    except ValueError:
        peer = None
    return (peer is not None and peer.is_loopback
            and request.url.hostname in ('localhost', '127.0.0.1', '::1')
            and request.headers.getlist('origin') == [str(request.base_url).rstrip('/')])


def ambient_light_reading():
    """Return the newest complete APDS9960 RGB sample without creating a log entry."""
    reading = nano.snapshot()
    sample = reading.get('data')
    environment = sample.get('environment') if isinstance(sample, dict) else None
    rgb = ([environment.get('light_r_raw'), environment.get('light_g_raw'),
            environment.get('light_b_raw')]
           if isinstance(environment, dict) else None)
    brightness_raw = brightness(rgb)
    if brightness_raw is None:
        return {'available': False, 'nano_status': reading.get('status', 'unavailable')}
    return {'available': True, 'nano_status': reading['status'], 'rgb': rgb,
            'brightness_raw': brightness_raw}


@asynccontextmanager
async def lifespan(app):
    recording_task = None
    try:
        if MODE == 'live':
            nano.start()
            gps.start()
            network.start()
            weather.start()
            road_conditions.start()
        recording_task = asyncio.create_task(recording_sampler())
        yield
    finally:
        if recording_task is not None:
            recording_task.cancel()
            try:
                await recording_task
            except asyncio.CancelledError:
                pass
        await asyncio.to_thread(recordings.stop, 'app_shutdown')
        if MODE == 'live':
            network.stop()
            gps.stop()
            nano.stop()
            road_conditions.stop()
            weather.stop()


app = FastAPI(title='OVRLand', docs_url=None, redoc_url=None, lifespan=lifespan)


def snapshot():
    data = copy.deepcopy(FIXTURE)
    data['timestamp'] = datetime.now(timezone.utc).isoformat()
    if MODE == 'mock':
        return data
    data['source'] = 'live'
    for group in ('vehicle', 'location', 'attitude', 'environment', 'route'):
        data[group] = dict.fromkeys(data[group])
    data['location']['altitude_source'] = None
    reading = nano.snapshot()
    gps_reading = gps.snapshot()
    network_reading = network.snapshot()
    data['sources'] = {'gps': gps_reading['status'], 'nano': reading['status'], 'obd': 'unavailable',
                       'network': network_reading['status']}
    data['gps'] = {key: value for key, value in gps_reading.items() if key != 'data'}
    data['nano'] = {key: value for key, value in reading.items() if key != 'data'}
    data['joystick'] = None
    data['route']['name'] = 'NO ACTIVE ROUTE'
    if reading['data']:
        sample = reading['data']
        data['environment'] = sample['environment']
        data['attitude'] = sample['attitude']
        data['imu'] = sample['imu']
        data['joystick'] = sample['joystick']
        data['nano']['received_at'] = sample['received_at']
        # Barometric estimate, not a GPS altitude; the UI labels its source.
        data['location']['altitude_m'] = sample['environment']['altitude_m']
        if data['location']['altitude_m'] is not None:
            data['location']['altitude_source'] = 'barometric'
    if gps_reading['data']:
        fix = gps_reading['data']
        # Keep the Nano barometric estimate when a 2D GPS fix has no altitude.
        data['location'].update({key: fix[key] for key in data['location']
                                 if fix.get(key) is not None})
        if fix.get('altitude_m') is not None:
            data['location']['altitude_source'] = 'gps'
        data['gps'].update({key: value for key, value in fix.items()
                            if key not in data['location']})
        weather.set_location(fix['latitude'], fix['longitude'], 'gps')
        road_conditions.set_location(fix['latitude'], fix['longitude'], 'gps')
    else:
        weather.set_location(WEATHER_LATITUDE, WEATHER_LONGITUDE, 'default')
        road_conditions.set_location(WEATHER_LATITUDE, WEATHER_LONGITUDE, 'default')
    data['weather'] = weather.snapshot()
    data['road_conditions'] = road_conditions.snapshot()
    data['sources'].update({'weather': data['weather']['status'],
                            'road_conditions': data['road_conditions']['status']})
    return data


async def recording_sampler():
    """Sample independently of browser connections while recording is active."""
    while True:
        if await asyncio.to_thread(recordings.is_recording):
            try:
                telemetry = snapshot()
                await asyncio.to_thread(recordings.append, telemetry)
            except Exception as error:
                await asyncio.to_thread(recordings.fail, error)
        await asyncio.sleep(.2)


@app.get('/')
async def index():
    return FileResponse(ROOT / 'static/index.html', headers={'Cache-Control': 'no-cache'})


@app.get('/api/telemetry')
async def telemetry():
    return snapshot()


@app.get('/api/window-mode')
def get_window_mode():
    return Response(content=window_mode, media_type='text/plain')


@app.post('/api/window-mode/{requested_mode}')
def set_window_mode(requested_mode: str, request: Request):
    global window_mode
    if requested_mode not in ('fullscreen', 'camp'):
        return Response(status_code=404)
    if not local_dashboard_request(request):
        return Response(status_code=403)
    window_mode = requested_mode
    return {'status': 'switching', 'mode': requested_mode}


@app.get('/api/recording/status')
def recording_status():
    return recordings.status()


@app.post('/api/recording/start')
def recording_start(request: Request):
    if not local_dashboard_request(request):
        return Response(status_code=403)
    try:
        return recordings.start()
    except OSError as error:
        return Response(content=json.dumps({'error': f'Unable to start recording: {error}'}),
                        media_type='application/json', status_code=503)


@app.post('/api/recording/stop')
def recording_stop(request: Request):
    if not local_dashboard_request(request):
        return Response(status_code=403)
    return recordings.stop('user')


@app.get('/api/recordings/{recording_id}/log')
def recording_log(recording_id: str):
    path = recordings.log_path(recording_id)
    if path is None:
        return Response(status_code=404)
    return FileResponse(path, media_type='application/x-ndjson',
                        filename=f'ovrland-{recording_id}.jsonl')


@app.get('/api/recordings/{recording_id}/gps-track.gpx')
def recording_gps_track(recording_id: str):
    try:
        content = recordings.gps_track(recording_id)
    except OSError:
        return Response(content='Unable to export recording', status_code=503)
    if content is None:
        return Response(status_code=404)

    def chunks():
        try:
            while chunk := content.read(64 * 1024):
                yield chunk
        finally:
            content.close()

    return StreamingResponse(chunks(), background=BackgroundTask(content.close),
                             media_type='application/gpx+xml', headers={
        'Content-Disposition': f'attachment; filename="ovrland-{recording_id}-gps-track.gpx"',
    })


@app.get('/api/maps/offline')
def offline_map_info():
    return offline_map.info()


@app.get('/api/music/streams')
def music_streams():
    return radio_catalog.streams()


@app.get('/api/music/now-playing/{stream_id}')
def music_now_playing(stream_id: str):
    result = radio_metadata.current(stream_id)
    return result if result.get('ok') else Response(
        content=json.dumps(result), media_type='application/json', status_code=503)


@app.post('/api/system/{action}')
async def system_action(action: str, request: Request):
    """Explicit local controls used by the System tab."""
    if action not in ('stop-app', 'poweroff-pi'):
        return Response(status_code=404)
    # Local browser controls only. The Host check also prevents DNS rebinding;
    # requiring Origin rejects cross-site forms and requests without provenance.
    if not local_dashboard_request(request):
        return Response(status_code=403)
    if MODE != 'live':
        return {'status': 'simulated', 'action': action}
    if action == 'stop-app':
        stop_app()
        return {'status': 'stopping', 'action': action}
    return ({'status': 'powering-off', 'action': action} if power_off_pi()
            else Response(status_code=503))


@app.get('/api/ambient-light/calibration')
def ambient_light_calibration_status():
    return {'current': ambient_light_reading(), 'entries': ambient_light_calibration.entries()}


@app.post('/api/ambient-light/calibration/{condition}')
def capture_ambient_light_calibration(condition: str, request: Request):
    if condition not in CONDITIONS:
        return Response(status_code=404)
    if not local_dashboard_request(request):
        return Response(status_code=403)
    current = ambient_light_reading()
    if not current['available']:
        return Response(content=json.dumps({
            'error': 'A live APDS9960 RGB reading is required before capture.',
            'current': current,
        }), media_type='application/json', status_code=409)
    entry = ambient_light_calibration.capture(condition, current['rgb'])
    return {'entry': entry, 'current': current, 'entries': ambient_light_calibration.entries()}


@app.get('/api/maps/tiles/{z}/{x}/{y}')
def offline_map_tile(z: int, x: int, y: int):
    tile = offline_map.tile(z, x, y)
    if tile is None:
        return Response(status_code=404)
    content, media_type = tile
    return Response(content, media_type=media_type, headers={'Cache-Control': 'public, max-age=86400'})


@app.websocket('/ws/telemetry')
async def stream(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            await ws.send_json(snapshot())
            await asyncio.sleep(.2)
    except (WebSocketDisconnect, OSError):
        pass


app.mount('/static', StaticFiles(directory=ROOT / 'static'), name='static')
app.mount('/media', StaticFiles(directory=ROOT / 'media'), name='media')
