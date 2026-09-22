"""One-shot local smoke check. Start live server and Chromium debug port 9226 first."""
import asyncio
import base64
import json
import urllib.request
from pathlib import Path
from websockets.asyncio.client import connect


async def main():
    root = 'http://127.0.0.1:8000'
    for path in ('/', '/static/app.js', '/static/style.css'):
        with urllib.request.urlopen(root + path, timeout=5) as response:
            assert response.status == 200
    async with connect('ws://127.0.0.1:8000/ws/telemetry') as ws:
        data = json.loads(await asyncio.wait_for(ws.recv(), 5))
        assert data['source'] == 'live'
        assert data['sources']['nano'] == 'live', data['sources']
        assert data['vehicle']['speed_mph'] is None
        assert data['location']['latitude'] is None
        print('HTTP/WebSocket PASS; live Nano sequence', data['nano']['sequence'], flush=True)
    tabs = json.load(urllib.request.urlopen('http://127.0.0.1:9226/json', timeout=5))
    async with connect(tabs[0]['webSocketDebuggerUrl']) as ws:
        ident = 0
        async def call(method, params=None):
            nonlocal ident
            ident += 1
            await ws.send(json.dumps({'id': ident, 'method': method, 'params': params or {}}))
            while True:
                response = json.loads(await asyncio.wait_for(ws.recv(), 10))
                if response.get('id') == ident:
                    assert 'error' not in response, response
                    return response.get('result', {})
        async def js(expression):
            result = await call('Runtime.evaluate', {'expression': expression, 'returnByValue': True})
            assert 'exceptionDetails' not in result, result
            return result['result'].get('value')
        await call('Emulation.setDeviceMetricsOverride', {'width': 1280, 'height': 800, 'deviceScaleFactor': 1, 'mobile': False})
        print('Browser attached', flush=True)
        html = Path('static/index.html').read_text().replace('<link rel="stylesheet" href="/static/style.css">', '<style>' + Path('static/style.css').read_text() + '</style>').replace('<script src="/static/app.js" defer></script>', '')
        await js('document.open();document.write(' + json.dumps(html) + ');document.close()')
        await js('window.WebSocket = class { constructor() {} }; window.setInterval = () => 0;')
        await js('(function(){' + Path('static/app.js').read_text() + ';window.testRender=render;window.testJoystick=joystick;})()')
        await js('window.testRender(' + json.dumps(data) + ')')
        assert await js("document.querySelector('#nano-state')?.textContent === 'LIVE'")
        assert await js('document.documentElement.scrollHeight <= 800'), await js('document.documentElement.scrollHeight')
        assert await js('document.documentElement.scrollWidth <= 1280')
        for mode in ('adventure', 'camp', 'drive'):
            assert await js(f"document.querySelector('button[data-mode={mode}]').click(); document.body.dataset.mode") == mode
        # Feed synthetic control events to the same renderer used by the live stream.
        await js("window.testJoystick({nano:{status:'live',session:'test',event_id:0,events:[]},joystick:{x:0,y:0,pressed:false}})")
        await js("window.testJoystick({nano:{status:'live',session:'test',event_id:2,events:[{id:1,action:'right'},{id:2,action:'select'}]},joystick:{x:0,y:0,pressed:true}})")
        assert await js('document.body.dataset.mode') == 'adventure'
        await js("document.querySelector('button[data-mode=drive]').click()")
        shot = await call('Page.captureScreenshot', {'format': 'png'})
        Path('/tmp/ovrland-live.png').write_bytes(base64.b64decode(shot['data']))
        await call('Emulation.setDeviceMetricsOverride', {'width': 390, 'height': 844, 'deviceScaleFactor': 1, 'mobile': True})
        assert await js('document.documentElement.scrollWidth <= 390')
        print('Browser PASS: live data, screen fit, modes, joystick selection, mobile width', flush=True)


asyncio.run(asyncio.wait_for(main(), 55))
