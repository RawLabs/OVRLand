const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../static/app.js'), 'utf8');
const start = source.indexOf('function bindSystemHold(button)');
const end = source.indexOf("for (const button of document.querySelectorAll('[data-system-action]'))", start);
assert.ok(start >= 0 && end > start);

function target() {
  const listeners = new Map();
  return {
    addEventListener(name, callback) { listeners.set(name, callback); },
    emit(name, fields = {}) {
      const event = {pointerId: 1, button: 0, isPrimary: true, clientX: 50, clientY: 50,
        prevented: false, preventDefault() { this.prevented = true; }, ...fields};
      listeners.get(name)?.(event);
      return event;
    },
  };
}

function setup(action = 'stop-app') {
  let now = 0, nextId = 0;
  const timers = new Map();
  const actions = [];
  const status = {textContent: 'SYSTEM STANDBY'};
  const window = {...target(),
    setTimeout(callback, delay) { const id = ++nextId; timers.set(id, {callback, due: now + delay}); return id; },
    clearTimeout(id) { timers.delete(id); },
  };
  const document = {...target(), hidden: false};
  const button = {...target(), disabled: false, dataset: {systemAction: action}, captured: null,
    setPointerCapture(id) { this.captured = id; },
    hasPointerCapture(id) { return this.captured === id; },
    releasePointerCapture(id) { this.captured = null; this.emit('lostpointercapture', {pointerId: id}); },
    getBoundingClientRect() { return {left: 0, right: 100, top: 0, bottom: 100}; },
  };
  const context = vm.createContext({window, document, $: () => status,
    runSystemAction(value) { actions.push(value); status.textContent = 'REQUEST SENT'; }});
  vm.runInContext(source.slice(start, end), context);
  context.bindSystemHold(button);
  return {button, window, document, actions, status,
    advance(milliseconds) {
      now += milliseconds;
      for (const [id, timer] of [...timers]) {
        if (timer.due <= now && timers.has(id)) { timers.delete(id); timer.callback(); }
      }
    },
  };
}

for (const action of ['stop-app', 'poweroff-pi']) {
  test(`${action}: touch long press suppresses the menu and fires once after two seconds`, () => {
    const h = setup(action);
    assert.equal(h.button.emit('pointerdown', {pointerType: 'touch'}).prevented, true);
    assert.equal(h.button.captured, 1);
    h.advance(500);
    assert.equal(h.button.emit('contextmenu').prevented, true);
    h.advance(1499);
    assert.deepEqual(h.actions, []);
    h.advance(1);
    assert.deepEqual(h.actions, [action]);
    h.button.emit('pointerup');
    h.advance(3000);
    assert.deepEqual(h.actions, [action]);
    assert.equal(h.status.textContent, 'REQUEST SENT');
  });
}

const guardStart = source.indexOf('class SystemHoldGuard');
const guardEnd = source.indexOf('\nconst $ =', guardStart);
assert.ok(guardStart >= 0 && guardEnd > guardStart);
const guardContext = vm.createContext({});
vm.runInContext(source.slice(guardStart, guardEnd) + '\nthis.SystemHoldGuard = SystemHoldGuard;', guardContext);
const HoldGuard = guardContext.SystemHoldGuard;

test('joystick hold cancels before completion when navigation arrives', () => {
  const guard = new HoldGuard();
  assert.equal(guard.arm('stop-app', 'camp:stop-app:one', 0), true);
  assert.equal(guard.update({origin: 'camp:stop-app:one',
    events: [{action: 'right'}], pressed: true, now: 1000}), null);
  assert.equal(guard.update({origin: 'camp:poweroff-pi:one',
    events: [], pressed: true, now: 2100}), null);
  assert.equal(guard.arm('poweroff-pi', 'camp:poweroff-pi:one', 2100), false);
  guard.update({origin: 'camp:poweroff-pi:one', pressed: false, now: 2200});
  assert.equal(guard.arm('poweroff-pi', 'camp:poweroff-pi:one', 2300), true);
  assert.equal(guard.update({origin: 'camp:poweroff-pi:one',
    events: [], pressed: true, now: 4300}), 'poweroff-pi');
  assert.equal(guard.update({origin: 'camp:poweroff-pi:one',
    events: [], pressed: true, now: 6400}), null);
});

test('touch tab or detail focus change cancels a pending joystick hold', () => {
  for (const nextOrigin of ['drive:map:one', 'camp:radio:one']) {
    const guard = new HoldGuard();
    guard.arm('stop-app', 'camp:stop-app:one', 0);
    assert.equal(guard.update({origin: nextOrigin, events: [],
      pressed: true, now: 2100}), null);
  }
});

for (const event of ['pointerup', 'pointercancel', 'lostpointercapture', 'pointermove', 'blur', 'hidden']) {
  test(`${event} cancels an incomplete hold`, () => {
    const h = setup();
    h.button.emit('pointerdown');
    h.advance(1000);
    if (event === 'blur') h.window.emit('blur');
    else if (event === 'hidden') { h.document.hidden = true; h.document.emit('visibilitychange'); }
    else h.button.emit(event, {clientX: 101});
    h.advance(2000);
    assert.deepEqual(h.actions, []);
    assert.equal(h.status.textContent, 'SYSTEM STANDBY');
  });
}

test('other pointers cannot restart or cancel the active hold', () => {
  const h = setup();
  h.button.emit('pointerdown');
  h.advance(1000);
  h.button.emit('pointerdown', {pointerId: 2, isPrimary: false});
  h.button.emit('pointerup', {pointerId: 2});
  h.advance(1000);
  assert.deepEqual(h.actions, ['stop-app']);
});

test('right click and disabled controls do not start holds', () => {
  const h = setup();
  h.button.emit('pointerdown', {button: 2});
  h.advance(2500);
  h.button.disabled = true;
  h.button.emit('pointerdown');
  h.advance(2500);
  assert.deepEqual(h.actions, []);
});
