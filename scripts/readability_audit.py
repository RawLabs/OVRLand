"""Render OVRLand typography in isolated Chromium with simulated telemetry."""

import asyncio, base64, functools, http.server, json, pathlib, shutil, subprocess, sys, tempfile, threading, urllib.request
import websockets

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else pathlib.Path(tempfile.mkdtemp(prefix='ovr-readability-'))
OUT.mkdir(exist_ok=True)
last_command = 'Chromium startup'
chromium = shutil.which('chromium') or shutil.which('chromium-browser')
if not chromium:
    raise SystemExit('Chromium is required for the readability audit; install chromium first.')
fixture = json.loads((ROOT / 'static/mock.json').read_text())
fixture['weather'].update(apparent_temperature_c=7, humidity_pct=76, cloud_cover_pct=38,
    pressure_hpa=1013, visibility_m=18000, uv_index=3, precipitation_mm=1.2, rain_mm=.8,
    showers_mm=.4, snowfall_cm=0,
    hourly_forecast=[dict(time=f'2026-09-27T{h:02}:00', weather_code=2, temperature_c=12,
        precipitation_probability_pct=30, wind_speed_kmh=22, wind_gust_kmh=35,
        wind_direction_deg=260, visibility_m=18000, uv_index=3) for h in range(8,20)],
    daily_forecast=[dict(date=f'2026-09-{d}',weather_code=2,high_c=18,low_c=3,
        wind_speed_max_kmh=28,wind_gust_max_kmh=45,precipitation_probability_pct=30,
        precipitation_mm=1.2,snowfall_cm=0,sunrise=f'2026-09-{d}T07:30',sunset=f'2026-09-{d}T19:20') for d in (27,28)])

class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args): pass
    def do_GET(self):
        if self.path.startswith('/api/'):
            if '/music/streams' in self.path:
                data={'ok':True,'streams':[dict(id=str(i),display_name=s,station_name=s,provider='Demo',description='Assessment fixture') for i,s in enumerate(['Trail Folk','Classic Rock','Instrumental & Ambient','Country Roads','Jazz and Blues','Independent Canadian Radio'])]}
            elif '/ambient-light/' in self.path:
                data={'current':{'available':True,'rgb':[123,234,345],'brightness_raw':234},'entries':[]}
            elif '/recording/status' in self.path:
                data={'recording':False,'latest_recording_id':None}
            elif '/maps/offline' in self.path:
                data={'available':False,'message':'Offline map package unavailable'}
            else: data={}
            self.send_response(200); self.send_header('Content-Type','application/json'); self.end_headers()
            self.wfile.write(json.dumps(data).encode()); return
        if self.path=='/': self.path='/static/index.html'
        super().do_GET()

server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Handler,directory=str(ROOT)))
threading.Thread(target=server.serve_forever,daemon=True).start()
profile=tempfile.mkdtemp(prefix='ovr-type-chrome-')
log=open(OUT/'chromium.log','w')
browser=subprocess.Popen([chromium,'--headless','--disable-gpu','--no-first-run','--disable-background-networking',
    '--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'],stdout=log,stderr=log)

async def main():
    for _ in range(100):
        portfile=pathlib.Path(profile)/'DevToolsActivePort'
        if portfile.exists(): break
        await asyncio.sleep(.1)
    if not portfile.exists():
        raise RuntimeError(f'Chromium debug port did not start; see {OUT / "chromium.log"}')
    port=portfile.read_text().splitlines()[0]
    pages=json.load(urllib.request.urlopen(f'http://127.0.0.1:{port}/json',timeout=3))
    page = next(p for p in pages if p.get('type') == 'page')
    async with websockets.connect(page['webSocketDebuggerUrl'],max_size=20_000_000) as ws:
        seq=0
        async def call(method,params={}):
            nonlocal seq
            global last_command
            seq+=1; ident=seq
            last_command=method
            await ws.send(json.dumps({'id':ident,'method':method,'params':params}))
            while True:
                try:
                    message=json.loads(await asyncio.wait_for(ws.recv(),8))
                except asyncio.TimeoutError as error:
                    raise RuntimeError(f'CDP command timed out: {last_command}') from error
                if message.get('id')==ident:
                    if 'error' in message: raise RuntimeError(message['error'])
                    return message.get('result',{})
        async def evaluate(expression):
            result=await call('Runtime.evaluate',{'expression':expression,'returnByValue':True,'awaitPromise':True})
            if 'exceptionDetails' in result: raise RuntimeError(result['exceptionDetails'])
            return result['result'].get('value')
        await call('Page.enable'); await call('Network.enable')
        await call('Network.setBlockedURLs',{'urls':['https://*']})
        script='window.WebSocket = class {constructor(){setInterval(()=>{if(this.onmessage)this.onmessage({data:JSON.stringify('+json.dumps(fixture)+')})},500)} close(){}};'
        await call('Page.addScriptToEvaluateOnNewDocument',{'source':script})
        measurements=[]
        async def capture(name,w,h):
            await asyncio.sleep(.15)
            rows=await evaluate('''JSON.stringify([...document.querySelectorAll('body *')].filter(n=> {
              const r=n.getBoundingClientRect(); return r.width&&r.height&&getComputedStyle(n).visibility!=='hidden'&&[...n.childNodes].some(c=>c.nodeType===3&&c.textContent.trim());
            }).map(n=>{const s=getComputedStyle(n),r=n.getBoundingClientRect();return {tag:n.tagName,id:n.id,classes:n.className.baseVal??n.className,text:n.textContent.trim().slice(0,100),font:parseFloat(s.fontSize),color:s.color,width:r.width,height:r.height,x:r.x,y:r.y,clipped:n.scrollWidth>n.clientWidth+1&&s.overflowX!=='visible'};}))''')
            geometry=await evaluate('({width:document.documentElement.scrollWidth,height:document.documentElement.scrollHeight,detailWidth:document.querySelector(".detail-window").scrollWidth,detailClient:document.querySelector(".detail-window").clientWidth})')
            measurements.append({'screen':name,'viewport':[w,h],'text':json.loads(rows),'geometry':geometry})
            if w == 1280 and name in ('drive','adventure') and (geometry['width'] > w or geometry['height'] > h):
                raise RuntimeError(f'{name} dashboard exceeds the Waveshare viewport: {geometry}')
            if w == 1100 and name in ('drive','adventure') and geometry['width'] > w:
                raise RuntimeError(f'{name} dashboard overflows Camp Mode horizontally: {geometry}')
            if w == 1280 and name.endswith('-obd'):
                font=await evaluate('parseFloat(getComputedStyle(document.querySelector(".detail-module-panel.vehicle-strip .vehicle-strip-metric strong")).fontSize)')
                if font < 44: raise RuntimeError(f'{name} expanded OBD reading is only {font}px')
            if w == 1280 and name == 'adventure':
                font=await evaluate('parseFloat(getComputedStyle(document.querySelector(".adventure-info .coordinates")).fontSize)')
                if font < 22: raise RuntimeError(f'Adventure coordinates are only {font}px')
            if w==1280:
                shot=await call('Page.captureScreenshot',{'format':'png','captureBeyondViewport':False})
                (OUT/f'{w}-{h}-{name}.png').write_bytes(base64.b64decode(shot['data']))
        for w,h in [(1280,800),(1024,600),(1100,680),(1920,1080)]:
            await call('Emulation.setDeviceMetricsOverride',{'width':w,'height':h,'deviceScaleFactor':1,'mobile':False})
            await call('Page.navigate',{'url':f'http://127.0.0.1:{server.server_port}/'})
            for _ in range(100):
                if await evaluate('!!document.querySelector(\'nav button[data-mode="music"]\')'): break
                await asyncio.sleep(.1)
            else:
                raise RuntimeError(await evaluate('({url:location.href,title:document.title,body:document.body?.innerText.slice(0,500)})'))
            await asyncio.sleep(.7)
            for mode,keys in [('drive',['map','conditions','attitude','obd']),('adventure',['conditions','attitude','map','location','obd']),('music',['radio','spotify']),('camp',[])]:
                await evaluate(f'document.querySelector(\'nav button[data-mode="{mode}"]\').click()')
                await capture(mode,w,h)
                for key in keys:
                    await evaluate(f'setModuleFocus(activeModules().findIndex(x=>x[0]==="{key}"));openDetail("{key}")')
                    await capture(mode+'-'+key,w,h)
                    if key=='attitude':
                        await evaluate('openCalibration()'); await capture(mode+'-calibration',w,h)
                    if key=='radio':
                        await evaluate('openMusicStreams()'); await asyncio.sleep(.1); await capture('radio-stations',w,h)
                        visible=await evaluate('''(() => {
                          const frame=document.querySelector('.detail-window').getBoundingClientRect();
                          const controls=activeDetailControls();
                          for (let i=0;i<controls.length;i++) {
                            setDetailFocus(i);
                            const node=document.querySelector('[data-detail-control="' + controls[i].key + '"]');
                            if (!node) return false;
                            const rect=node.getBoundingClientRect();
                            if (rect.bottom<=frame.top || rect.top>=frame.bottom ||
                                rect.right<=frame.left || rect.left>=frame.right) return false;
                          }
                          return true;
                        })()''')
                        if not visible: raise RuntimeError(f'radio detail focus left the visible frame at {w}x{h}')
                    if key=='map':
                        for state in ['offline','gaia']:
                            await evaluate(f'window.dashboardMap.choose("{state}")'); await capture(mode+'-map-'+state,w,h)
                        await evaluate('window.dashboardMap.choose("osm")')
                    await evaluate('closeDetail()')
                    if not await evaluate('document.querySelector("#detail-overlay").hidden && !document.querySelector(".detail-module-panel")'):
                        raise RuntimeError(f'detail did not restore after {mode}-{key} at {w}x{h}')
        (OUT/'measurements.json').write_text(json.dumps(measurements,indent=2))
        print(json.dumps({'screens':len(measurements),'output':str(OUT),
            'overflow':[(m['screen'],m['viewport'],m['geometry']['width']-m['viewport'][0])
                        for m in measurements if m['geometry']['width']>m['viewport'][0]+1],
            'dashboard_heights':[(m['screen'],m['viewport'],m['geometry']['height'])
                        for m in measurements if m['screen'] in ('drive','adventure')]},indent=2))
try: asyncio.run(asyncio.wait_for(main(),timeout=240))
except asyncio.TimeoutError as error:
    raise RuntimeError(f'Readability audit exceeded 240 seconds; last CDP command: {last_command}') from error
finally:
    browser.terminate()
    try: browser.wait(timeout=5)
    except subprocess.TimeoutExpired: browser.kill(); browser.wait()
    server.shutdown(); log.close()
