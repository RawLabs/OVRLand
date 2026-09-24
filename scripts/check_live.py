"""One-shot smoke check. Start the server and Chromium debug port 9226 first.

The default requires live Nano telemetry. Pass ``--browser-only`` to exercise
the same rendered-dashboard checks against an explicitly mock-mode server.
"""
import asyncio
import base64
import json
import re
import sys
import urllib.request
from pathlib import Path
from websockets.asyncio.client import connect


async def main():
    require_live = '--browser-only' not in sys.argv[1:]
    root = 'http://127.0.0.1:8000'
    for path in ('/', '/static/app.js', '/static/style.css', '/static/layout.css'):
        with urllib.request.urlopen(root + path, timeout=5) as response:
            assert response.status == 200
    async with connect('ws://127.0.0.1:8000/ws/telemetry') as ws:
        data = json.loads(await asyncio.wait_for(ws.recv(), 5))
        if require_live:
            assert data['source'] == 'live'
            assert data['sources']['nano'] == 'live', data['sources']
            assert data['vehicle']['speed_mph'] is None
            assert data['location']['latitude'] is None
            print('HTTP/WebSocket PASS; live Nano sequence', data['nano']['sequence'], flush=True)
        else:
            assert data['source'] == 'mock', data['source']
            print('HTTP/WebSocket PASS; mock telemetry for browser-only check', flush=True)
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
        html = re.sub(
            r'<script src="/static/app\.js(?:\?[^\"]*)?" defer></script>',
            '',
            Path('static/index.html').read_text(),
        )
        await js('document.open();document.write(' + json.dumps(html) + ');document.close()')
        for _ in range(50):
            if await js("document.styleSheets.length >= 3 && getComputedStyle(document.documentElement).getPropertyValue('--accent').trim() === '#f2993a'"):
                break
            await asyncio.sleep(.1)
        else:
            raise AssertionError('Dashboard stylesheets did not load')
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
        navigation = await js(r'''(() => {
          const modes = {
            drive: [
              ['map', '.map-panel'], ['speed', '.speed-gauge'],
              ['rpm', '.rpm-gauge'],
              ['health', '.drive-health'], ['diagnostics', '.drive-summary'],
              ['attitude', '.drive-secondary'],
            ],
            adventure: [
              ['location', '.adventure-info'], ['map', '.map-panel'],
              ['conditions', '.adventure-secondary'],
              ['compass', '.trail-compass'], ['attitude', '.trail-attitude'],
            ],
            music: [
              ['radio', '.radio-portal'], ['spotify', '.spotify-portal'],
            ],
            camp: [
              ['stop-app', '[data-system-action="stop-app"]'],
              ['poweroff-pi', '[data-system-action="poweroff-pi"]'],
            ],
          };
          const focusSelector =
            '.joy-focus, .joy-section-focus, .joy-footer-focus, .joy-detail-focus';
          const focusedKey = () => {
            const focused = [...document.querySelectorAll(focusSelector)].filter(element => {
              const style = getComputedStyle(element);
              return element.getClientRects().length && style.display !== 'none' &&
                style.visibility !== 'hidden';
            });
            if (focused.length !== 1) {
              throw new Error(`Expected one visible focus outline, found ${focused.length}`);
            }
            const element = focused[0];
            const style = getComputedStyle(element);
            const outlined = style.outlineStyle !== 'none' && parseFloat(style.outlineWidth) > 0;
            if (!outlined && style.boxShadow === 'none') {
              throw new Error(`Focused element has no visible outline: ${element.className}`);
            }
            if (element.classList.contains('joy-detail-focus')) return 'detail';
            if (element.classList.contains('joy-footer-focus')) return 'footer';
            if (element.classList.contains('joy-focus')) return `tab:${element.dataset.mode}`;
            const entry = modes[document.body.dataset.mode].find(([, selector]) =>
              document.querySelector(selector) === element);
            if (!entry) throw new Error(`Unknown module focus: ${element.className}`);
            return entry[0];
          };
          let sessionNumber = 0;
          const start = mode => {
            document.querySelector(`button[data-mode="${mode}"]`).click();
            const state = {session: `navigation-${mode}-${++sessionNumber}`, eventId: 0};
            window.testJoystick({nano:{status:'live',session:state.session,event_id:0,events:[]},
              joystick:{x:0,y:0,pressed:false}});
            const focused = focusedKey();
            if (focused !== `tab:${mode}`) throw new Error(`Initial ${mode} focus: ${focused}`);
            return state;
          };
          const send = (state, action, pressed = false) => {
            state.eventId += 1;
            window.testJoystick({nano:{status:'live',session:state.session,
              event_id:state.eventId,events:[{id:state.eventId,action}]},
              joystick:{x:0,y:0,pressed}});
            return focusedKey();
          };
          const release = state => window.testJoystick({nano:{status:'live',
            session:state.session,event_id:state.eventId,events:[]},
            joystick:{x:0,y:0,pressed:false}});
          const result = {down: {}, right: {}, left: {}, up: {}, footerUp: {}, details: {}};
          for (const [mode, entries] of Object.entries(modes)) {
            const keys = entries.map(([key]) => key);

            let state = start(mode);
            result.down[mode] = Array.from({length: keys.length + 1}, () => send(state, 'down'));

            state = start(mode);
            result.right[mode] = [send(state, 'down')];
            for (let index = 0; index < keys.length; index += 1) {
              result.right[mode].push(send(state, 'right'));
            }

            state = start(mode);
            send(state, 'down');
            result.left[mode] = send(state, 'left');

            state = start(mode);
            send(state, 'down');
            for (let index = 1; index < keys.length; index += 1) send(state, 'right');
            result.up[mode] = [];
            for (let index = 1; index < keys.length; index += 1) {
              result.up[mode].push(send(state, 'up'));
            }
            result.up[mode].push(send(state, 'up'));

            state = start(mode);
            for (let index = 0; index <= keys.length; index += 1) send(state, 'down');
            result.footerUp[mode] = send(state, 'up');
          }

          for (const mode of ['drive', 'adventure', 'music']) {
            const keys = modes[mode].map(([key]) => key);
            const state = start(mode);
            send(state, 'down');
            result.details[mode] = [];
            for (const [index, key] of keys.entries()) {
              if (focusedKey() !== key) throw new Error(`Detail origin mismatch: ${mode}/${key}`);
              if (send(state, 'select') !== 'detail' ||
                  document.querySelector('#detail-overlay').hidden) {
                throw new Error(`Detail did not open: ${mode}/${key}`);
              }
              send(state, 'up');
              if (send(state, 'select') !== key ||
                  !document.querySelector('#detail-overlay').hidden) {
                throw new Error(`Detail focus did not restore: ${mode}/${key}`);
              }
              result.details[mode].push(key);
              if (index < keys.length - 1) send(state, 'right');
            }
          }

          const systemState = start('camp');
          send(systemState, 'down');
          result.systemGuard = modes.camp.map(([key], index) => {
            if (focusedKey() !== key) throw new Error(`System focus mismatch: ${key}`);
            send(systemState, 'select');
            const status = document.querySelector('#system-status').textContent;
            if (status !== 'HOLD BUTTON FOR 2 SECONDS TO CONFIRM') {
              throw new Error(`System action was not guarded: ${key}`);
            }
            release(systemState);
            if (index < modes.camp.length - 1) send(systemState, 'right');
            return key;
          });
          return result;
        })()''')
        orders = {
            'drive': ['map', 'speed', 'rpm', 'health',
                      'diagnostics', 'attitude'],
            'adventure': ['location', 'map', 'conditions', 'compass',
                          'attitude'],
            'music': ['radio', 'spotify'],
            'camp': ['stop-app', 'poweroff-pi'],
        }
        for mode, order in orders.items():
            assert navigation['down'][mode] == order + ['footer'], navigation
            assert navigation['right'][mode] == order + [order[0]], navigation
            assert navigation['left'][mode] == order[-1], navigation
            assert navigation['up'][mode] == list(reversed(order[:-1])) + [f'tab:{mode}'], navigation
            assert navigation['footerUp'][mode] == order[-1], navigation
        assert navigation['details'] == {
            mode: order for mode, order in orders.items() if mode != 'camp'
        }, navigation
        assert navigation['systemGuard'] == orders['camp'], navigation
        await js("document.querySelector('button[data-mode=drive]').click()")
        shot = await call('Page.captureScreenshot', {'format': 'png'})
        Path('/tmp/ovrland-live.png').write_bytes(base64.b64decode(shot['data']))
        await call('Emulation.setDeviceMetricsOverride', {'width': 390, 'height': 844, 'deviceScaleFactor': 1, 'mobile': True})
        for _ in range(50):
            mobile_width = await js('document.documentElement.scrollWidth')
            if mobile_width <= 390:
                break
            await asyncio.sleep(.1)
        assert mobile_width <= 390, mobile_width
        print('Browser PASS: live data, screen fit, modes, sequential joystick navigation, mobile width', flush=True)


asyncio.run(asyncio.wait_for(main(), 55))
