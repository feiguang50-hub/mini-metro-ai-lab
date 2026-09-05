const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const flush = async () => { for (let i=0; i<10; i++) await Promise.resolve(); };
function fixture() {
  const html = fs.readFileSync('web/battle.html', 'utf8');
  const elements = Object.fromEntries([...html.matchAll(/id="([^"]+)"/g)].map(([,id]) => [id, {
    value: '', disabled: false, hidden: false, textContent: '', children: [], events: {},
    addEventListener(name, fn) { this.events[name] = fn; },
    appendChild(el) { this.children.push(el); }, replaceChildren() { this.children = []; },
  }]));
  const requests = [], timers = [], renderers = [];
  const context = {
    document: { getElementById(id) { assert.ok(elements[id], `missing DOM id ${id}`); return elements[id]; }, createElement() { return {}; } },
    createMetroRenderer() { const r = { resets: 0, reset() { this.resets++; }, draw() {} }; renderers.push(r); return r; },
    fetch(url, options) { return new Promise(resolve => requests.push({url, options, resolve})); },
    setTimeout() {}, setInterval(fn) { timers.push(fn); }, requestAnimationFrame() {},
  };
  vm.runInNewContext(fs.readFileSync('web/battle.js','utf8'), context);
  const reply = (req, payload, ok=true) => req.resolve({ok, status: ok ? 200 : 400, json: async () => payload});
  return { elements, requests, timers, renderers, reply };
}
function state(session=1) {
  const side = { runtime: { algorithm: 'Greedy', risk: 20, status: 'running', invalid_actions: 0 }, progression: {station_count:3,station_limit:20,next_station_in_ms:44900}, game: { deliveries: 2, time_ms: 100 }, decision: { title: '铺线', detail: 'test' } };
  return {session_id:session, status:'running', config:{seed:42,dt_ms:100,budget_ms:300}, round:1, elapsed_ms:100, left:side, right:side, leader:'tie', delivery_margin:0};
}

test('catalog availability, paired scores and submitted common config', async () => {
  const f = fixture();
  f.reply(f.requests[0], {algorithms:[{id:'a',name:'A',available:true,status:'baseline'},{id:'b',name:'B',available:true,status:'candidate'},{id:'c',name:'C',available:false,status:'planned'}]});
  f.reply(f.requests[1], state());
  await flush();
  assert.equal(f.elements.leftAlgorithm.value, 'a');
  assert.equal(f.elements.rightAlgorithm.value, 'b');
  assert.equal(f.elements.rightAlgorithm.children[2].disabled, true);
  assert.equal(f.elements.score.textContent, '2 : 2');
  assert.equal(f.elements.leftRisk.textContent, '风险 20%');
  assert.equal(f.elements.leftStations.textContent, '3/20 站 · 下一站 44.9 秒');
  Object.assign(f.elements.battleSeed, {value:'314'});
  Object.assign(f.elements.battleDt, {value:'100'});
  Object.assign(f.elements.battleBudget, {value:'0.3'});
  f.elements.battleForm.events.submit({preventDefault(){}});
  const req = f.requests.at(-1);
  assert.equal(req.url, '/api/battle/control');
  assert.deepEqual(JSON.parse(req.options.body), {command:'start',value:{left:'a',right:'b',seed:314,dt_ms:100,budget_ms:300}});
  assert.equal(f.elements.startBattle.disabled, true);
  f.reply(req, {ok:true}); await flush();
  assert.equal(f.elements.startBattle.disabled, false);
});

test('restart discards late old snapshot, resets both renderer caches', async () => {
  const f = fixture();
  f.reply(f.requests[1], state()); await flush();
  f.timers[0]();
  const stale = f.requests.at(-1);
  f.elements.restartBattle.events.click();
  const restart = f.requests.at(-1);
  assert.deepEqual(JSON.parse(restart.options.body), {command:'restart'});
  f.reply(restart, {ok:true}); await flush();
  f.reply(stale, {...state(), round:99, elapsed_ms:9900}); await flush();
  assert.ok(!f.elements.battleConfig.textContent.includes('99 轮'));
  f.timers[0](); f.reply(f.requests.at(-1), state(2)); await flush();
  assert.deepEqual(f.renderers.map(r=>r.resets), [2,2]);
});

test('API failures visible and controls re-enabled; polling recovers', async () => {
  const f = fixture();
  f.reply(f.requests[0], {algorithms:[{id:'a',name:'A',available:true,status:'baseline'}]});
  f.reply(f.requests[1], state()); await flush();
  f.elements.restartBattle.events.click();
  f.reply(f.requests.at(-1), {ok:false,error:'invalid config'}, false); await flush();
  assert.equal(f.elements.battleError.textContent,'invalid config');
  assert.equal(f.elements.restartBattle.disabled,false);
  f.timers[0](); f.reply(f.requests.at(-1), {}, false); await flush();
  assert.equal(f.elements.battleStatus.textContent,'连接中断');
  f.timers[0](); f.reply(f.requests.at(-1), {...state(),status:'finished',leader:'right',delivery_margin:3}); await flush();
  assert.equal(f.elements.battleStatus.textContent,'对战结束');
  assert.equal(f.elements.margin.textContent,'右侧 +3');
});

test('shared renderer draws numeric engine shapes exactly like their named equivalents', () => {
  function draw(shape) {
    const calls = [];
    const ctx = new Proxy({}, {get(target, name) { return (...args) => calls.push([name, ...args]); }});
    const canvas = {width:640,height:360,getContext:()=>ctx,getBoundingClientRect:()=>({width:640,height:360})};
    const context = {window:{devicePixelRatio:1}};
    vm.runInNewContext(fs.readFileSync('web/map-renderer.js','utf8'), context);
    context.window.createMetroRenderer(canvas).draw({game:{stations:[{id:'s',position:[100,100],shape_type:shape}]}});
    return calls;
  }
  const shapes = ['square','circle','triangle','cross','diamond','pentagon','star'];
  shapes.forEach((name, index) => assert.deepEqual(draw(String(index+1)),draw(name)));
  assert.notDeepEqual(draw('1'),draw('2'));
});

test('shared renderer marks a station added after the initial frame', () => {
  const calls = [];
  const ctx = new Proxy({}, {get(target, name) { return (...args) => calls.push([name, ...args]); }});
  const canvas = {width:640,height:360,getContext:()=>ctx,getBoundingClientRect:()=>({width:640,height:360})};
  const context = {window:{devicePixelRatio:1},Date};
  vm.runInNewContext(fs.readFileSync('web/map-renderer.js','utf8'), context);
  const renderer = context.window.createMetroRenderer(canvas);
  const station = (id, x) => ({id,position:[x,100],shape_type:'2'});
  const current = (stations) => ({runtime:{overdue_threshold:2},engine:{screen_width:640,screen_height:360},game:{stations}});
  renderer.draw(current([station('a', 100), station('b', 200), station('c', 300)]));
  calls.length = 0;
  renderer.draw(current([station('a', 100), station('b', 200), station('c', 300), station('d', 400)]));
  assert.ok(calls.some((call) => call[0] === 'fillText' && call[1] === '新站'));
});
