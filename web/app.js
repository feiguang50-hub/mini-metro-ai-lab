(() => {
  const canvas = document.getElementById('metroCanvas');
  const ctx = canvas.getContext('2d');
  const $ = (id) => document.getElementById(id);
  let lastState = null;
  let toastTimer = null;

  function fmtTime(ms) {
    const total = Math.floor((Number(ms) || 0) / 1000);
    const min = Math.floor(total / 60);
    const sec = total % 60;
    return `${String(min).padStart(2, '0')}:${String(sec).padStart(2, '0')}`;
  }

  function colorOf(value, fallback) {
    if (Array.isArray(value) && value.length >= 3) return `rgb(${value[0]},${value[1]},${value[2]})`;
    if (typeof value === 'string' && value) return value;
    return fallback;
  }

  function shapeName(raw) {
    const s = String(raw ?? '').toLowerCase();
    if (s.includes('triangle') || s.includes('三角')) return 'triangle';
    if (s.includes('square') || s.includes('方')) return 'square';
    if (s.includes('cross')) return 'cross';
    return 'circle';
  }

  function drawStation(x, y, type, pressure) {
    const r = 11;
    ctx.save();
    ctx.translate(x, y);
    ctx.lineWidth = 3;
    ctx.strokeStyle = '#2d2f32';
    ctx.fillStyle = '#f7f4ed';
    ctx.beginPath();
    if (type === 'triangle') {
      ctx.moveTo(0, -r); ctx.lineTo(r, r * .8); ctx.lineTo(-r, r * .8); ctx.closePath();
    } else if (type === 'square') {
      ctx.rect(-r * .8, -r * .8, r * 1.6, r * 1.6);
    } else if (type === 'cross') {
      const a = r * .45, b = r;
      ctx.moveTo(-a,-b); ctx.lineTo(a,-b); ctx.lineTo(a,-a); ctx.lineTo(b,-a); ctx.lineTo(b,a); ctx.lineTo(a,a); ctx.lineTo(a,b); ctx.lineTo(-a,b); ctx.lineTo(-a,a); ctx.lineTo(-b,a); ctx.lineTo(-b,-a); ctx.lineTo(-a,-a); ctx.closePath();
    } else {
      ctx.arc(0, 0, r, 0, Math.PI * 2);
    }
    ctx.fill(); ctx.stroke();
    if (pressure > 0) {
      ctx.beginPath();
      ctx.arc(0, 0, r + 7, -Math.PI / 2, -Math.PI / 2 + Math.PI * 2 * Math.min(1, pressure));
      ctx.strokeStyle = pressure > .7 ? '#b95454' : '#b9a44b';
      ctx.lineWidth = 2;
      ctx.stroke();
    }
    ctx.restore();
  }

  function draw(state) {
    const game = state.game;
    const engine = state.engine;
    const stations = game.stations || [];
    const paths = game.paths || [];
    const metros = game.metros || [];
    const byId = new Map(stations.map(s => [s.id, s]));
    const sx = canvas.width / Math.max(1, engine.screen_width);
    const sy = canvas.height / Math.max(1, engine.screen_height);
    const point = (station) => ({ x: (station.position[0] + 18) * sx, y: (station.position[1] + 18) * sy });

    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = '#f7f4ed';
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    ctx.strokeStyle = 'rgba(65,67,68,.045)';
    ctx.lineWidth = 1;
    for (let x = 0; x < canvas.width; x += 80) { ctx.beginPath(); ctx.moveTo(x,0); ctx.lineTo(x,canvas.height); ctx.stroke(); }
    for (let y = 0; y < canvas.height; y += 80) { ctx.beginPath(); ctx.moveTo(0,y); ctx.lineTo(canvas.width,y); ctx.stroke(); }

    paths.forEach((path, idx) => {
      const pts = (path.station_ids || []).map(id => byId.get(id)).filter(Boolean).map(point);
      if (pts.length < 2) return;
      ctx.beginPath();
      ctx.moveTo(pts[0].x, pts[0].y);
      pts.slice(1).forEach(p => ctx.lineTo(p.x, p.y));
      if (path.is_looped) ctx.closePath();
      ctx.strokeStyle = colorOf(path.color, ['#df5f54','#4d83c4','#d3a93b','#6b9c6b'][idx % 4]);
      ctx.lineWidth = 7;
      ctx.lineJoin = 'round'; ctx.lineCap = 'round';
      ctx.stroke();
    });

    metros.forEach((metro) => {
      if (!metro.position) return;
      const x = (metro.position[0] + 12) * sx;
      const y = (metro.position[1] + 8) * sy;
      const path = paths.find(p => p.id === metro.path_id);
      ctx.save();
      ctx.translate(x, y);
      ctx.fillStyle = colorOf(path?.color, '#34373a');
      ctx.strokeStyle = '#f7f4ed';
      ctx.lineWidth = 2;
      ctx.beginPath(); ctx.roundRect(-10, -6, 20, 12, 4); ctx.fill(); ctx.stroke();
      ctx.restore();
    });

    const threshold = Math.max(1, state.runtime.overdue_threshold || 10);
    stations.forEach((station) => {
      const p = point(station);
      const waiting = Number(station.passenger_count) || 0;
      drawStation(p.x, p.y, shapeName(station.shape_type), waiting / threshold);
      if (waiting > 0) {
        ctx.font = '600 12px system-ui';
        ctx.fillStyle = waiting >= threshold * .7 ? '#a94646' : '#696b67';
        ctx.fillText(String(waiting), p.x + 17, p.y - 12);
      }
    });
  }

  function renderUI(state) {
    lastState = state;
    const game = state.game;
    const fleet = game.fleet || {};
    $('deliveries').textContent = game.deliveries ?? 0;
    $('time').textContent = fmtTime(game.time_ms);
    $('risk').textContent = `${state.runtime.risk}%`;
    $('seed').textContent = `Seed ${state.runtime.seed}`;
    $('algorithm').textContent = state.runtime.algorithm;
    $('decisionTitle').textContent = state.decision.title;
    $('decisionDetail').textContent = state.decision.detail;
    $('actionChip').textContent = state.decision.action?.type || 'noop';
    $('lineCount').textContent = (game.paths || []).length;
    $('locoCount').textContent = `${fleet.locomotives_assigned ?? 0}/${fleet.locomotives_total ?? 0}`;
    $('carriageCount').textContent = `${fleet.carriages_assigned ?? 0}/${fleet.carriages_total ?? 0}`;
    $('stationCount').textContent = (game.stations || []).length;

    const dead = Boolean(game.is_game_over);
    const paused = Boolean(state.runtime.paused);
    $('statusText').textContent = dead ? '本局结束' : paused ? '已暂停' : '运行中';
    $('pauseBtn').textContent = paused ? '继续' : '暂停';
    $('statusDot').className = `status-dot${dead ? ' dead' : paused ? ' paused' : ''}`;
    document.querySelectorAll('.speed').forEach(btn => btn.classList.toggle('active', Number(btn.dataset.speed) === state.runtime.speed));

    const history = $('history');
    history.innerHTML = '';
    if (!state.history.length) {
      history.innerHTML = '<div class="empty">暂无重大调整</div>';
    } else {
      state.history.slice(0, 6).forEach(item => {
        const el = document.createElement('div');
        el.className = `history-item${item.ok ? '' : ' bad'}`;
        const title = document.createElement('strong');
        title.textContent = `${fmtTime(item.time_ms)} · ${item.title}${item.ok ? '' : '（未执行）'}`;
        const p = document.createElement('p');
        p.textContent = item.detail;
        el.append(title, p); history.appendChild(el);
      });
    }
    draw(state);
  }

  function toast(text) {
    const node = $('toast');
    node.textContent = text; node.classList.add('show');
    clearTimeout(toastTimer); toastTimer = setTimeout(() => node.classList.remove('show'), 1400);
  }

  async function control(command, value) {
    try {
      const response = await fetch('/api/control', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({command, value}) });
      if (!response.ok) throw new Error((await response.json()).error || '控制失败');
    } catch (err) { toast(err.message || String(err)); }
  }

  $('pauseBtn').addEventListener('click', () => control(lastState?.runtime.paused ? 'resume' : 'pause'));
  $('restartBtn').addEventListener('click', () => control('restart'));
  $('randomBtn').addEventListener('click', () => control('random_restart'));
  document.querySelectorAll('.speed').forEach(btn => btn.addEventListener('click', () => control('speed', Number(btn.dataset.speed))));

  let fetching = false;
  async function poll() {
    if (fetching) return;
    fetching = true;
    try {
      const response = await fetch('/api/state', {cache: 'no-store'});
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      renderUI(await response.json());
    } catch (err) {
      $('statusText').textContent = '连接中断';
      $('statusDot').className = 'status-dot dead';
    } finally { fetching = false; }
  }

  poll();
  setInterval(poll, 120);
})();
