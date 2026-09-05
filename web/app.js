(() => {
  const canvas = document.getElementById('metroCanvas');
  const ctx = canvas.getContext('2d');
  const $ = (id) => document.getElementById(id);

  let state = null;
  let toastTimer = null;
  let fetching = false;
  let crowdVisible = true;
  let viewport = { width: 1280, height: 720, dpr: 1 };
  const trainVisuals = new Map();

  function fmtTime(ms) {
    const total = Math.floor((Number(ms) || 0) / 1000);
    const min = Math.floor(total / 60);
    const sec = total % 60;
    return `${String(min).padStart(2, '0')}:${String(sec).padStart(2, '0')}`;
  }

  function colorOf(value, fallback) {
    if (Array.isArray(value) && value.length >= 3) {
      return `rgb(${value[0]},${value[1]},${value[2]})`;
    }
    if (typeof value === 'string' && value) return value;
    return fallback;
  }

  function shapeName(raw) {
    const s = String(raw ?? '').toLowerCase();
    if (s.includes('triangle') || s.includes('三角')) return 'triangle';
    if (s.includes('square') || s.includes('方')) return 'square';
    if (s.includes('cross') || s.includes('十字')) return 'cross';
    if (s.includes('diamond') || s.includes('菱')) return 'diamond';
    if (s.includes('star') || s.includes('星')) return 'star';
    return 'circle';
  }

  function resizeCanvas() {
    const rect = canvas.getBoundingClientRect();
    const width = Math.max(1, Math.round(rect.width));
    const height = Math.max(1, Math.round(rect.height));
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    const pixelWidth = Math.round(width * dpr);
    const pixelHeight = Math.round(height * dpr);
    if (canvas.width !== pixelWidth || canvas.height !== pixelHeight) {
      canvas.width = pixelWidth;
      canvas.height = pixelHeight;
    }
    viewport = { width, height, dpr };
  }

  function beginFrame() {
    const { width, height, dpr } = viewport;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = '#f7f4ed';
    ctx.fillRect(0, 0, width, height);
  }

  function stationPoint(station, engine) {
    const sx = viewport.width / Math.max(1, Number(engine.screen_width) || 1920);
    const sy = viewport.height / Math.max(1, Number(engine.screen_height) || 1080);
    return {
      x: (Number(station.position?.[0]) + 18) * sx,
      y: (Number(station.position?.[1]) + 18) * sy,
    };
  }

  function enginePoint(position, engine) {
    const sx = viewport.width / Math.max(1, Number(engine.screen_width) || 1920);
    const sy = viewport.height / Math.max(1, Number(engine.screen_height) || 1080);
    return {
      x: (Number(position?.[0]) + 12) * sx,
      y: (Number(position?.[1]) + 8) * sy,
    };
  }

  function traceShape(type, x, y, r) {
    ctx.beginPath();
    if (type === 'triangle') {
      ctx.moveTo(x, y - r);
      ctx.lineTo(x + r, y + r * .8);
      ctx.lineTo(x - r, y + r * .8);
      ctx.closePath();
    } else if (type === 'square') {
      ctx.rect(x - r * .78, y - r * .78, r * 1.56, r * 1.56);
    } else if (type === 'diamond') {
      ctx.moveTo(x, y - r); ctx.lineTo(x + r, y); ctx.lineTo(x, y + r); ctx.lineTo(x - r, y); ctx.closePath();
    } else if (type === 'cross') {
      const a = r * .42, b = r;
      ctx.moveTo(x-a,y-b); ctx.lineTo(x+a,y-b); ctx.lineTo(x+a,y-a); ctx.lineTo(x+b,y-a);
      ctx.lineTo(x+b,y+a); ctx.lineTo(x+a,y+a); ctx.lineTo(x+a,y+b); ctx.lineTo(x-a,y+b);
      ctx.lineTo(x-a,y+a); ctx.lineTo(x-b,y+a); ctx.lineTo(x-b,y-a); ctx.lineTo(x-a,y-a); ctx.closePath();
    } else if (type === 'star') {
      for (let i = 0; i < 10; i += 1) {
        const radius = i % 2 === 0 ? r : r * .43;
        const angle = -Math.PI / 2 + i * Math.PI / 5;
        const px = x + Math.cos(angle) * radius;
        const py = y + Math.sin(angle) * radius;
        if (i === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
      }
      ctx.closePath();
    } else {
      ctx.arc(x, y, r, 0, Math.PI * 2);
    }
  }

  function drawStation(x, y, type, pressure) {
    const r = Math.max(7.5, Math.min(11, viewport.width / 92));
    ctx.save();
    if (pressure > .02) {
      ctx.beginPath();
      ctx.arc(x, y, r + 8, -Math.PI / 2, -Math.PI / 2 + Math.PI * 2 * Math.min(1, pressure));
      ctx.strokeStyle = pressure > .72 ? 'rgba(181,75,75,.82)' : pressure > .42 ? 'rgba(184,143,52,.72)' : 'rgba(102,137,111,.55)';
      ctx.lineWidth = 2.2;
      ctx.lineCap = 'round';
      ctx.stroke();
    }

    ctx.lineWidth = 2.5;
    ctx.strokeStyle = '#303236';
    ctx.fillStyle = '#f7f4ed';
    traceShape(type, x, y, r);
    ctx.fill();
    ctx.stroke();
    ctx.restore();
  }

  function waitingByStation(game) {
    const map = new Map();
    for (const passenger of game.passengers || []) {
      const location = passenger.location;
      if (!Array.isArray(location) || location[0] !== 'station') continue;
      const stationId = location[1];
      if (!map.has(stationId)) map.set(stationId, []);
      map.get(stationId).push(shapeName(passenger.destination_shape_type));
    }
    return map;
  }

  function drawWaitingPassengers(point, shapes, threshold) {
    if (!crowdVisible || !shapes?.length) return;
    const maxVisible = 18;
    const visible = shapes.slice(0, maxVisible);
    const columns = 6;
    const spacing = 7;
    const startX = point.x + 17;
    const startY = point.y - 13;
    ctx.save();
    ctx.lineWidth = 1.2;
    ctx.strokeStyle = shapes.length >= threshold * .7 ? '#a64b4b' : '#656762';
    ctx.fillStyle = '#f7f4ed';
    visible.forEach((shape, index) => {
      const x = startX + (index % columns) * spacing;
      const y = startY + Math.floor(index / columns) * spacing;
      traceShape(shape, x, y, 2.6);
      ctx.fill();
      ctx.stroke();
    });
    if (shapes.length > maxVisible) {
      ctx.fillStyle = '#777974';
      ctx.font = '600 9px system-ui';
      ctx.fillText(`+${shapes.length - maxVisible}`, startX + 1, startY + 27);
    }
    ctx.restore();
  }

  function updateTrainTargets(game, engine) {
    const active = new Set();
    for (const metro of game.metros || []) {
      if (!metro.position) continue;
      active.add(metro.id);
      const target = enginePoint(metro.position, engine);
      const existing = trainVisuals.get(metro.id);
      if (!existing) {
        trainVisuals.set(metro.id, { x: target.x, y: target.y, tx: target.x, ty: target.y });
      } else {
        existing.tx = target.x;
        existing.ty = target.y;
      }
    }
    for (const id of [...trainVisuals.keys()]) {
      if (!active.has(id)) trainVisuals.delete(id);
    }
  }

  function drawNetwork(current) {
    if (!current) return;
    const game = current.game || {};
    const engine = current.engine || {};
    const stations = game.stations || [];
    const paths = game.paths || [];
    const metros = game.metros || [];
    const byId = new Map(stations.map((station) => [station.id, station]));
    const waiters = waitingByStation(game);
    const threshold = Math.max(1, Number(current.runtime?.overdue_threshold) || 10);

    beginFrame();

    // Barely-visible paper grain lines, enough to avoid a sterile debug-canvas feel.
    ctx.save();
    ctx.strokeStyle = 'rgba(44,46,45,.022)';
    ctx.lineWidth = 1;
    const grid = Math.max(90, viewport.width / 10);
    for (let x = grid; x < viewport.width; x += grid) {
      ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, viewport.height); ctx.stroke();
    }
    for (let y = grid; y < viewport.height; y += grid) {
      ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(viewport.width, y); ctx.stroke();
    }
    ctx.restore();

    paths.forEach((path, idx) => {
      const pts = (path.station_ids || []).map((id) => byId.get(id)).filter(Boolean).map((station) => stationPoint(station, engine));
      if (pts.length < 2) return;
      const color = colorOf(path.color, ['#d85c53','#497eb8','#d1a73a','#69936c','#8a6db1'][idx % 5]);

      const trace = () => {
        ctx.beginPath();
        ctx.moveTo(pts[0].x, pts[0].y);
        pts.slice(1).forEach((p) => ctx.lineTo(p.x, p.y));
        if (path.is_looped) ctx.closePath();
      };

      ctx.save();
      ctx.lineJoin = 'round';
      ctx.lineCap = 'round';
      trace();
      ctx.strokeStyle = 'rgba(247,244,237,.96)';
      ctx.lineWidth = Math.max(8.5, viewport.width / 115);
      ctx.stroke();
      trace();
      ctx.strokeStyle = color;
      ctx.lineWidth = Math.max(5.2, viewport.width / 180);
      ctx.stroke();
      ctx.restore();
    });

    updateTrainTargets(game, engine);
    const pathById = new Map(paths.map((path, idx) => [path.id, { path, idx }]));
    for (const metro of metros) {
      const visual = trainVisuals.get(metro.id);
      if (!visual) continue;
      visual.x += (visual.tx - visual.x) * .18;
      visual.y += (visual.ty - visual.y) * .18;
      const route = pathById.get(metro.path_id);
      const color = colorOf(route?.path?.color, '#34373a');
      const w = Math.max(15, viewport.width / 68);
      const h = Math.max(8, w * .56);
      ctx.save();
      ctx.translate(visual.x, visual.y);
      ctx.fillStyle = color;
      ctx.strokeStyle = '#f7f4ed';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.roundRect(-w / 2, -h / 2, w, h, Math.min(4, h / 2));
      ctx.fill();
      ctx.stroke();
      ctx.restore();
    }

    stations.forEach((station) => {
      const point = stationPoint(station, engine);
      const shapes = waiters.get(station.id) || [];
      const waiting = Math.max(Number(station.passenger_count) || 0, shapes.length);
      drawStation(point.x, point.y, shapeName(station.shape_type), waiting / threshold);
      drawWaitingPassengers(point, shapes, threshold);
    });
  }

  function renderUI(current) {
    state = current;
    const game = current.game || {};
    const fleet = game.fleet || {};
    const stations = game.stations || [];
    const maxWaiting = stations.reduce((max, station) => Math.max(max, Number(station.passenger_count) || 0), 0);
    const threshold = Math.max(1, Number(current.runtime.overdue_threshold) || 10);
    const pressureRatio = Math.min(1, maxWaiting / threshold);

    $('deliveries').textContent = game.deliveries ?? 0;
    $('time').textContent = fmtTime(game.time_ms);
    $('risk').textContent = `${current.runtime.risk}%`;
    $('seed').textContent = `Seed ${current.runtime.seed}`;
    $('algorithm').textContent = current.runtime.algorithm;
    $('decisionTitle').textContent = current.decision.title;
    $('decisionDetail').textContent = current.decision.detail;
    $('actionChip').textContent = current.decision.action?.type || 'noop';
    $('actionState').textContent = current.runtime.action_ok ? '已执行' : '动作未生效';
    $('actionState').className = `action-state${current.runtime.action_ok ? '' : ' bad'}`;
    $('lineCount').textContent = (game.paths || []).length;
    $('locoCount').textContent = `${fleet.locomotives_assigned ?? 0}/${fleet.locomotives_total ?? 0}`;
    $('carriageCount').textContent = `${fleet.carriages_assigned ?? 0}/${fleet.carriages_total ?? 0}`;
    $('stationCount').textContent = stations.length;
    $('pressureCount').textContent = `${maxWaiting} 人候车`;
    $('pressureHint').textContent = pressureRatio >= .75 ? '需要马上处理' : pressureRatio >= .45 ? '压力正在上升' : maxWaiting ? '仍在安全区间' : '网络很平静';
    $('pressureBar').style.width = `${Math.round(pressureRatio * 100)}%`;
    $('pressureBar').style.background = pressureRatio >= .75 ? '#b44f4f' : pressureRatio >= .45 ? '#b58a37' : '#6b8e74';
    $('engineCommit').textContent = `engine ${String(current.engine.commit || '').slice(0, 12)}`;

    const dead = Boolean(game.is_game_over);
    const paused = Boolean(current.runtime.paused);
    $('statusText').textContent = dead ? '本局结束' : paused ? '已暂停' : '运行中';
    $('pauseBtn').textContent = paused ? '继续' : '暂停';
    $('statusDot').className = `status-dot${dead ? ' dead' : paused ? ' paused' : ''}`;
    document.querySelectorAll('.speed').forEach((btn) => {
      btn.classList.toggle('active', Number(btn.dataset.speed) === current.runtime.speed);
    });

    $('gameOver').hidden = !dead;
    if (dead) $('finalScore').textContent = `运送 ${game.deliveries ?? 0} 人`;

    const history = $('history');
    history.innerHTML = '';
    if (!current.history.length) {
      history.innerHTML = '<div class="empty">暂无重大调整</div>';
    } else {
      current.history.slice(0, 6).forEach((item) => {
        const el = document.createElement('div');
        el.className = `history-item${item.ok ? '' : ' bad'}`;
        const title = document.createElement('strong');
        title.textContent = `${fmtTime(item.time_ms)} · ${item.title}${item.ok ? '' : '（未执行）'}`;
        const p = document.createElement('p');
        p.textContent = item.detail;
        el.append(title, p);
        history.appendChild(el);
      });
    }
  }

  function toast(text) {
    const node = $('toast');
    node.textContent = text;
    node.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => node.classList.remove('show'), 1400);
  }

  async function control(command, value) {
    try {
      const response = await fetch('/api/control', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({command, value}),
      });
      if (!response.ok) throw new Error((await response.json()).error || '控制失败');
      await poll();
    } catch (err) {
      toast(err.message || String(err));
    }
  }

  $('pauseBtn').addEventListener('click', () => control(state?.runtime.paused ? 'resume' : 'pause'));
  $('restartBtn').addEventListener('click', () => control('restart'));
  $('randomBtn').addEventListener('click', () => control('random_restart'));
  document.querySelectorAll('.speed').forEach((btn) => btn.addEventListener('click', () => control('speed', Number(btn.dataset.speed))));

  $('crowdBtn').addEventListener('click', () => {
    crowdVisible = !crowdVisible;
    $('crowdBtn').classList.toggle('active', crowdVisible);
    $('crowdBtn').setAttribute('aria-pressed', String(crowdVisible));
  });

  $('immersiveBtn').addEventListener('click', () => {
    const immersive = document.body.classList.toggle('immersive');
    $('immersiveBtn').classList.toggle('active', immersive);
    $('immersiveBtn').setAttribute('aria-pressed', String(immersive));
    $('immersiveBtn').textContent = immersive ? '显示 AI' : '沉浸观战';
    requestAnimationFrame(resizeCanvas);
  });

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
    } finally {
      fetching = false;
    }
  }

  function animate() {
    drawNetwork(state);
    requestAnimationFrame(animate);
  }

  resizeCanvas();
  if ('ResizeObserver' in window) {
    new ResizeObserver(resizeCanvas).observe(canvas.parentElement);
  } else {
    window.addEventListener('resize', resizeCanvas);
  }
  poll();
  setInterval(poll, 140);
  requestAnimationFrame(animate);
})();
