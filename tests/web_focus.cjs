const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

test('map focus follows stable IDs after station/path reordering and clears on reset', () => {
  const calls = [];
  const ctx = new Proxy({}, {get: (_, method) => (...args) => calls.push([method, ...args])});
  const canvas = {width: 640, height: 360, getContext: () => ctx, getBoundingClientRect: () => ({width: 640, height: 360})};
  const context = {window: {devicePixelRatio: 1}};
  vm.runInNewContext(fs.readFileSync('web/map-renderer.js', 'utf8'), context);
  const renderer = context.window.createMetroRenderer(canvas);
  const state = {engine: {screen_width: 640, screen_height: 360}, game: {
    stations: [{id: 'b', position: [400, 100]}, {id: 'a', position: [100, 100]}],
    paths: [{id: 'other', station_ids: ['b', 'a']}, {id: 'target', station_ids: ['a', 'b']}],
  }};
  renderer.setFocus({station_ids: ['a'], path_ids: ['target']});
  renderer.draw(state);
  const rings = calls.filter(call => call[0] === 'arc' && call[3] === 23);
  assert.deepEqual(rings.map(call => call.slice(1, 4)), [[118, 118, 23]]);
  renderer.reset(); calls.length = 0; renderer.draw(state);
  assert.equal(calls.filter(call => call[0] === 'arc' && call[3] === 23).length, 0);
  renderer.setFocus({station_ids: ['missing'], path_ids: ['removed']});
  calls.length = 0; renderer.draw(state);
  assert.equal(calls.filter(call => call[0] === 'arc' && call[3] === 23).length, 0);
});

test('successful restart clears focus even when the first new frame has the same time', async () => {
  const element = () => ({
    value: '', hidden: true, dataset: {}, events: {}, children: [], classList: {toggle() {}},
    addEventListener(name, fn) { this.events[name] = fn; },
    setAttribute(name, value) { this[name] = value; },
    appendChild(child) { this.children.push(child); }, append(...children) { this.children.push(...children); },
    focus() {}, style: {},
  });
  const elements = Object.fromEntries([...fs.readFileSync('web/index.html', 'utf8').matchAll(/id="([^"]+)"/g)].map(([, id]) => [id, element()]));
  const requests = [], timers = [];
  const renderer = {setFocus(value) { this.focus = value; }, reset() { this.focus = null; }, resize() {}, draw() {}};
  const context = {
    createMetroRenderer: () => renderer,
    document: {getElementById: id => elements[id], createElement: element, querySelectorAll: selector => selector === '.history-item' ? elements.history.children : []},
    window: {addEventListener() {}, matchMedia: () => ({matches: false})},
    fetch(url, options) { return new Promise(resolve => requests.push({url, options, resolve})); },
    setInterval(fn) { timers.push(fn); }, setTimeout() {}, clearTimeout() {}, requestAnimationFrame() {},
  };
  vm.runInNewContext(fs.readFileSync('web/app.js', 'utf8'), context);
  const flush = async () => { for (let i = 0; i < 15; i++) await Promise.resolve(); };
  const reply = (request, data) => request.resolve({ok: true, json: async () => data});
  const state = {runtime: {seed: 42, algorithm_id: 'a', algorithm: 'A'}, engine: {}, game: {time_ms: 100, stations: [], paths: []}, decision: {title: '观察', detail: '', action: {type: 'noop'}}, history: [{time_ms: 100, action: 'create_path', title: '建立线路', detail: '', ok: true, targets: {station_ids: ['old-station'], path_ids: []}}]};
  reply(requests[0], state); await flush();
  elements.focusLatest.events.click();
  assert.equal(elements.mapFocus.hidden, false);
  assert.ok(renderer.focus);
  elements.restartBtn.events.click();
  reply(requests.at(-1), {ok: true}); await flush();
  assert.equal(elements.mapFocus.hidden, true);
  assert.equal(renderer.focus, null);
  reply(requests.at(-1), {...state, history: []}); await flush();
  assert.equal(elements.mapFocus.hidden, true);
});
