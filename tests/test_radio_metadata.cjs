const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../static/app.js'), 'utf8');
const start = source.indexOf('async function refreshNowPlaying(streamId)');
const end = source.indexOf('async function startBrowserRadio', start);
assert.ok(start >= 0 && end > start);

function harness(fetchImpl) {
  const renders = [];
  const context = {
    nowPlayingRequest: 0,
    activeRadioStream: {id: 'station-a'},
    currentRadioTrack: null,
    trackMetadataUnavailable: false,
    radioAudio: {paused: false},
    fetch: fetchImpl,
    renderBrowserRadio(state) { renders.push(state); },
    renders,
  };
  vm.createContext(context);
  vm.runInContext(source.slice(start, end) + '\nthis.refreshNowPlaying = refreshNowPlaying;', context);
  return context;
}

test('failed metadata refresh clears the previous song and later metadata recovers', async () => {
  let response = {ok: true, async json() { return {ok: true, title: 'Song A', artist: 'Artist A'}; }};
  const app = harness(async () => response);
  await app.refreshNowPlaying('station-a');
  assert.equal(app.currentRadioTrack.title, 'Song A');
  response = {ok: false};
  await app.refreshNowPlaying('station-a');
  assert.equal(app.currentRadioTrack, null);
  assert.equal(app.trackMetadataUnavailable, true);
  response = {ok: true, async json() { return {ok: true, title: 'Song B', artist: 'Artist B'}; }};
  await app.refreshNowPlaying('station-a');
  assert.equal(app.currentRadioTrack.title, 'Song B');
  assert.equal(app.trackMetadataUnavailable, false);
});

test('in-flight metadata for a previous station cannot replace the new station', async () => {
  let resolveOld;
  const app = harness(() => new Promise(resolve => { resolveOld = resolve; }));
  const oldRequest = app.refreshNowPlaying('station-a');
  app.activeRadioStream = {id: 'station-b'};
  app.fetch = async () => ({ok: true, async json() {
    return {ok: true, title: 'Song B', artist: 'Artist B'};
  }});
  await app.refreshNowPlaying('station-b');
  resolveOld({ok: true, async json() { return {ok: true, title: 'Old Song', artist: 'Old Artist'}; }});
  await oldRequest;
  assert.equal(app.currentRadioTrack.title, 'Song B');
});
