(() => {
  const canvas = document.getElementById('metroCanvas');
  const renderer = createMetroRenderer(canvas);
  const resizeCanvas = renderer.resize;
  const $ = (id) => document.getElementById(id);

  let state = null;
  let fetching = false;
  let crowdVisible = true;
  let toastTimer = null;
  let catalogSignature = '';

  function fmtTime(ms) {
    const total = Math.floor((Number(ms) || 0) / 1000);
    const min = Math.floor(total / 60);
    const sec = total % 60;
    return `${String(min).padStart(2, '0')}:${String(sec).padStart(2, '0')}`;
  }

  function statusLabel(status) {
    return ({ baseline: '基线', champion: '冠军', candidate: '候选', retired: '退役', eliminated: '淘汰', archived: '归档', planned: '开发中' })[status] || status;
  }

  function renderAlgorithmLibrary(current) {
    const catalog = current.algorithms || [];
    const signature = JSON.stringify(catalog.map((item) => [item.id, item.available, item.status, item.version]));
    const select = $('algorithmSelect');
    if (signature !== catalogSignature) {
      catalogSignature = signature;
      select.innerHTML = '';
      catalog.forEach((item) => {
        const option = document.createElement('option');
        option.value = item.id;
        option.disabled = !item.available;
        option.textContent = `${item.name}${item.available ? '' : ' · 开发中'}`;
        select.appendChild(option);
      });
    }

    const activeId = current.runtime.algorithm_id;
    if (select.value !== activeId) select.value = activeId;
    const spec = catalog.find((item) => item.id === activeId);
    if (!spec) return;

    $('algorithmSummary').textContent = spec.summary || '';
    const badges = $('algorithmBadges');
    badges.innerHTML = '';
    [statusLabel(spec.status), spec.family, `v${spec.version}`, ...(spec.tags || [])].forEach((text, index) => {
      const badge = document.createElement('span');
      badge.className = `algorithm-badge${index === 0 ? ` status${spec.status === 'planned' ? ' planned' : ''}` : ''}`;
      badge.textContent = text;
      badges.appendChild(badge);
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

    renderAlgorithmLibrary(current);
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
    document.querySelectorAll('.speed').forEach((btn) => btn.classList.toggle('active', Number(btn.dataset.speed) === current.runtime.speed));

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
    toastTimer = setTimeout(() => node.classList.remove('show'), 1500);
  }

  async function control(command, value) {
    try {
      const response = await fetch('/api/control', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ command, value }),
      });
      const payload = await response.json();
      if (!response.ok || !payload.ok) throw new Error(payload.error || '控制失败');
      await poll();
      return payload;
    } catch (error) {
      toast(error.message || String(error));
      throw error;
    }
  }

  $('pauseBtn').addEventListener('click', () => control(state?.runtime.paused ? 'resume' : 'pause').catch(() => {}));
  $('restartBtn').addEventListener('click', () => control('restart').catch(() => {}));
  $('randomBtn').addEventListener('click', () => control('random_restart').catch(() => {}));
  document.querySelectorAll('.speed').forEach((btn) => btn.addEventListener('click', () => control('speed', Number(btn.dataset.speed)).catch(() => {})));

  $('algorithmSelect').addEventListener('change', async (event) => {
    const previous = state?.runtime.algorithm_id;
    const next = event.target.value;
    if (!next || next === previous) return;
    event.target.disabled = true;
    try {
      await control('algorithm', next);
      toast('已切换算法，并用同一 Seed 重开');
      renderer.reset();
    } catch (_error) {
      event.target.value = previous || '';
    } finally {
      event.target.disabled = false;
    }
  });

  $('crowdBtn').addEventListener('click', () => {
    crowdVisible = !crowdVisible;
    renderer.setCrowd(crowdVisible);
    $('crowdBtn').classList.toggle('active', crowdVisible);
    $('crowdBtn').setAttribute('aria-pressed', String(crowdVisible));
  });

  $('immersiveBtn').addEventListener('click', () => {
    const active = !document.body.classList.contains('immersive');
    document.body.classList.toggle('immersive', active);
    $('immersiveBtn').textContent = active ? '显示 AI' : '沉浸观战';
    $('immersiveBtn').classList.toggle('active', active);
    $('immersiveBtn').setAttribute('aria-pressed', String(active));
    requestAnimationFrame(resizeCanvas);
  });

  async function poll() {
    if (fetching) return;
    fetching = true;
    try {
      const response = await fetch('/api/state', { cache: 'no-store' });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const next = await response.json();
      renderUI(next);

    } catch (_error) {
      $('statusText').textContent = '连接中断';
      $('statusDot').className = 'status-dot dead';
    } finally {
      fetching = false;
    }
  }

  function animate() {
    resizeCanvas();
    renderer.draw(state);
    requestAnimationFrame(animate);
  }

  window.addEventListener('resize', resizeCanvas);
  resizeCanvas();
  poll();
  setInterval(poll, 120);
  requestAnimationFrame(animate);
})();
