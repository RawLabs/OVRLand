"""Bounded service and Chromium smoke check for an already running OVRLand."""
import asyncio
import base64
import json
import sys
import urllib.request
from pathlib import Path

from websockets.asyncio.client import connect


ROOT = 'http://127.0.0.1:8000'
ORIGIN = ROOT
LAST_COMMAND = 'startup'


async def main():
    require_live = '--browser-only' not in sys.argv[1:]
    for path in ('/healthz', '/', '/static/app.js', '/static/layout.css'):
        with urllib.request.urlopen(ROOT + path, timeout=3) as response:
            assert response.status == 200, path

    async with connect('ws://127.0.0.1:8000/ws/telemetry',
                       origin=ORIGIN, open_timeout=3, close_timeout=2) as telemetry:
        data = json.loads(await asyncio.wait_for(telemetry.recv(), 5))
    if require_live:
        assert data['source'] == 'live', data['source']
        assert data['sources']['nano'] == 'live', data['sources']
        assert data['vehicle']['speed_mph'] is None
        print('HTTP/WebSocket PASS; live Nano and GPS values may be present', flush=True)
    else:
        assert data['source'] == 'mock', data['source']
        print('HTTP/WebSocket PASS; mock telemetry', flush=True)

    tabs = json.load(urllib.request.urlopen('http://127.0.0.1:9226/json', timeout=3))
    page = next(item for item in tabs if item.get('type') == 'page')
    async with connect(page['webSocketDebuggerUrl'], open_timeout=3, close_timeout=2) as ws:
        sequence = 0
        async def call(method, params=None):
            nonlocal sequence
            global LAST_COMMAND
            sequence += 1
            ident = sequence
            LAST_COMMAND = method
            await ws.send(json.dumps({'id': ident, 'method': method, 'params': params or {}}))
            while True:
                message = json.loads(await asyncio.wait_for(ws.recv(), 8))
                if message.get('id') != ident:
                    continue
                if 'error' in message:
                    raise RuntimeError(f'{method} failed: {message["error"]}')
                return message.get('result', {})

        async def js(expression):
            result = await call('Runtime.evaluate', {
                'expression': expression, 'returnByValue': True, 'awaitPromise': True,
            })
            if 'exceptionDetails' in result:
                raise RuntimeError(f'{LAST_COMMAND}: {result["exceptionDetails"]}')
            return result['result'].get('value')

        await call('Emulation.setDeviceMetricsOverride', {
            'width': 1280, 'height': 800, 'deviceScaleFactor': 1, 'mobile': False,
        })
        await call('Page.navigate', {'url': ROOT + '/'})
        for _ in range(50):
            if await js("document.querySelector('nav button[data-mode=music]') !== null && document.querySelector('#connection')?.textContent === 'DATA FEED CONNECTED'"):
                break
            await asyncio.sleep(.1)
        else:
            raise RuntimeError(f'Dashboard did not connect: {await js("document.body?.innerText.slice(0,500)")}')

        modules = {
            'drive': ['map', 'conditions', 'attitude', 'obd'],
            'adventure': ['conditions', 'attitude', 'map', 'location', 'obd'],
            'music': ['radio', 'spotify'],
        }
        for mode, keys in modules.items():
            await js(f"document.querySelector('nav button[data-mode={mode}]').click()")
            assert await js('document.body.dataset.mode') == mode
            for key in keys:
                await js(f'setModuleFocus(activeModules().findIndex(item => item[0] === {json.dumps(key)})); openDetail({json.dumps(key)})')
                assert await js('!document.querySelector("#detail-overlay").hidden'), f'{mode}/{key} did not open'
                assert await js('Boolean(document.querySelector(".detail-module-panel"))')
                if key == 'conditions':
                    await js('stale()')
                    assert await js('document.querySelector("[data-road-detail=note]").textContent.startsWith("FEED LOST")')
                    for _ in range(30):
                        if await js('document.querySelector("[data-road-detail=note]").textContent.startsWith("FEED LOST") === false'):
                            break
                        await asyncio.sleep(.1)
                    else:
                        raise RuntimeError('Road detail did not recover after telemetry resumed')
                await js('closeDetail()')
                assert await js('document.querySelector("#detail-overlay").hidden && !document.querySelector(".detail-module-panel")'), f'{mode}/{key} did not restore'
        await js("document.querySelector('nav button[data-mode=camp]').click()")
        camp_count = await js('activeModules().length')
        assert camp_count == 10, camp_count
        assert await js('document.documentElement.scrollWidth <= 1280 && document.documentElement.scrollHeight <= 800')

        shot = await call('Page.captureScreenshot', {'format': 'png'})
        Path('/tmp/ovrland-live.png').write_bytes(base64.b64decode(shot['data']))
        await call('Emulation.setDeviceMetricsOverride', {
            'width': 390, 'height': 844, 'deviceScaleFactor': 1, 'mobile': True,
        })
        await js("document.querySelector('nav button[data-mode=drive]').click()")
        assert await js('document.documentElement.scrollWidth <= 390')
        print('Browser PASS: modes, all dashboard detail restore paths, Camp controls, 1280x800 and 390px fit', flush=True)


try:
    asyncio.run(asyncio.wait_for(main(), timeout=55))
except asyncio.TimeoutError as error:
    raise RuntimeError(f'Acceptance smoke timed out after 55 seconds; last command: {LAST_COMMAND}') from error
