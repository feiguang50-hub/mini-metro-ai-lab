window.createMetroRenderer = function(canvas) {
  const ctx = canvas.getContext("2d");
  let crowdVisible = true;
  let viewport = { width: 1280, height: 720, dpr: 1 };
  const trainVisuals = new Map();
  const knownStations = new Set();
  const stationBirths = new Map();
  let stationSetInitialized = false;
  function colorOf(value, fallback) {
    if (Array.isArray(value) && value.length >= 3) return `rgb(${value[0]},${value[1]},${value[2]})`;
    if (typeof value === 'string' && value) return value;
    return fallback;
  }

  function shapeName(raw) {
    const s = String(raw ?? '').toLowerCase();
    const encoded = { '1': 'square', '2': 'circle', '3': 'triangle', '4': 'cross', '5': 'diamond', '6': 'pentagon', '7': 'star' };
    if (encoded[s]) return encoded[s];
    if (s.includes('pentagon')) return 'pentagon';
    if (s.includes('triangle') || s.includes('三角')) return 'triangle';
    if (s.includes('square') || s.includes('rect') || s.includes('方')) return 'square';
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
      ctx.moveTo(x, y - r); ctx.lineTo(x + r, y + r * .8); ctx.lineTo(x - r, y + r * .8); ctx.closePath();
    } else if (type === 'square') {
      ctx.rect(x - r * .78, y - r * .78, r * 1.56, r * 1.56);
    } else if (type === 'diamond') {
      ctx.moveTo(x, y - r); ctx.lineTo(x + r, y); ctx.lineTo(x, y + r); ctx.lineTo(x - r, y); ctx.closePath();
    } else if (type === 'cross') {
      const a = r * .42, b = r;
      ctx.moveTo(x-a,y-b); ctx.lineTo(x+a,y-b); ctx.lineTo(x+a,y-a); ctx.lineTo(x+b,y-a);
      ctx.lineTo(x+b,y+a); ctx.lineTo(x+a,y+a); ctx.lineTo(x+a,y+b); ctx.lineTo(x-a,y+b);
      ctx.lineTo(x-a,y+a); ctx.lineTo(x-b,y+a); ctx.lineTo(x-b,y-a); ctx.lineTo(x-a,y-a); ctx.closePath();
    } else if (type === 'pentagon') {
      for (let i = 0; i < 5; i += 1) {
        const angle = -Math.PI / 2 + i * Math.PI * 2 / 5;
        const px = x + Math.cos(angle) * r, py = y + Math.sin(angle) * r;
        if (i === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
      }
      ctx.closePath();
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

  function trackNewStations(stations) {
    const now = Date.now();
    const active = new Set(stations.map((station) => station.id));
    for (const station of stations) {
      if (!knownStations.has(station.id)) {
        knownStations.add(station.id);
        if (stationSetInitialized) stationBirths.set(station.id, now);
      }
    }
    for (const id of [...knownStations]) {
      if (!active.has(id)) {
        knownStations.delete(id);
        stationBirths.delete(id);
      }
    }
    stationSetInitialized = true;
  }

  function drawStationArrival(station, point) {
    const bornAt = stationBirths.get(station.id);
    if (!bornAt) return;
    const age = Date.now() - bornAt;
    if (age >= 3200) {
      stationBirths.delete(station.id);
      return;
    }
    const progress = age / 3200;
    ctx.save();
    ctx.beginPath();
    ctx.arc(point.x, point.y, 17 + progress * 28, 0, Math.PI * 2);
    ctx.strokeStyle = `rgba(212, 112, 66, ${0.72 * (1 - progress)})`;
    ctx.lineWidth = 4 - progress * 2;
    ctx.stroke();
    ctx.fillStyle = `rgba(151, 67, 37, ${1 - progress})`;
    ctx.font = '700 10px system-ui';
    ctx.fillText('新站', point.x + 18, point.y - 17);
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
      const visual = trainVisuals.get(metro.id);
      if (!visual) trainVisuals.set(metro.id, { x: target.x, y: target.y, tx: target.x, ty: target.y });
      else { visual.tx = target.x; visual.ty = target.y; }
    }
    for (const id of [...trainVisuals.keys()]) if (!active.has(id)) trainVisuals.delete(id);
  }

  function drawNetwork(current) {
    if (!current) { beginFrame(); return; }
    const game = current.game || {};
    const engine = current.engine || {};
    const stations = game.stations || [];
    const paths = game.paths || [];
    const metros = game.metros || [];
    const byId = new Map(stations.map((station) => [station.id, station]));
    const waiters = waitingByStation(game);
    const threshold = Math.max(1, Number(current.runtime?.overdue_threshold) || 10);
    trackNewStations(stations);

    beginFrame();
    ctx.save();
    ctx.strokeStyle = 'rgba(44,46,45,.022)';
    ctx.lineWidth = 1;
    const grid = Math.max(90, viewport.width / 10);
    for (let x = grid; x < viewport.width; x += grid) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, viewport.height); ctx.stroke(); }
    for (let y = grid; y < viewport.height; y += grid) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(viewport.width, y); ctx.stroke(); }
    ctx.restore();

    paths.forEach((path, idx) => {
      const pts = (path.station_ids || []).map((id) => byId.get(id)).filter(Boolean).map((station) => stationPoint(station, engine));
      if (pts.length < 2) return;
      const color = colorOf(path.color, ['#d85c53','#497eb8','#d1a73a','#69936c','#8a6db1'][idx % 5]);
      const trace = () => {
        ctx.beginPath(); ctx.moveTo(pts[0].x, pts[0].y); pts.slice(1).forEach((p) => ctx.lineTo(p.x, p.y));
        if (path.is_looped) ctx.closePath();
      };
      ctx.save();
      ctx.lineJoin = 'round'; ctx.lineCap = 'round';
      trace(); ctx.strokeStyle = 'rgba(247,244,237,.96)'; ctx.lineWidth = Math.max(8.5, viewport.width / 115); ctx.stroke();
      trace(); ctx.strokeStyle = color; ctx.lineWidth = Math.max(5.2, viewport.width / 180); ctx.stroke();
      ctx.restore();
    });

    updateTrainTargets(game, engine);
    const pathById = new Map(paths.map((path) => [path.id, path]));
    for (const metro of metros) {
      const visual = trainVisuals.get(metro.id);
      if (!visual) continue;
      visual.x += (visual.tx - visual.x) * .18;
      visual.y += (visual.ty - visual.y) * .18;
      const color = colorOf(pathById.get(metro.path_id)?.color, '#34373a');
      const w = Math.max(15, viewport.width / 68);
      const h = Math.max(8, w * .56);
      ctx.save();
      ctx.translate(visual.x, visual.y);
      ctx.fillStyle = color; ctx.strokeStyle = '#f7f4ed'; ctx.lineWidth = 2;
      ctx.beginPath(); ctx.roundRect(-w / 2, -h / 2, w, h, Math.min(4, h / 2)); ctx.fill(); ctx.stroke();
      ctx.restore();
    }

    stations.forEach((station) => {
      const point = stationPoint(station, engine);
      const shapes = waiters.get(station.id) || [];
      const waiting = Math.max(Number(station.passenger_count) || 0, shapes.length);
      drawStation(point.x, point.y, shapeName(station.shape_type), waiting / threshold);
      drawWaitingPassengers(point, shapes, threshold);
      drawStationArrival(station, point);
    });
  }


  return { draw(current) { resizeCanvas(); drawNetwork(current); }, resize: resizeCanvas, reset() { trainVisuals.clear(); knownStations.clear(); stationBirths.clear(); stationSetInitialized = false; }, setCrowd(value) { crowdVisible = value; } };
};
