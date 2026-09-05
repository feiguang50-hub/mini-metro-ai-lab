(() => {
  const $ = (id) => document.getElementById(id);
  const renderers = { left: createMetroRenderer($('leftCanvas')), right: createMetroRenderer($('rightCanvas')) };
  const labels = { idle: '等待开始', running: '运行中', finished: '预算结束', game_over: 'Game Over', error: '对战异常' };
  let state = null;
  let fetching = false;
  let pending = false;
  let generation = 0;
  let catalogReady = false;
  let controlError = "";
  const time = (ms) => `${(ms / 1000).toFixed(1)} 秒`;

  function render(next) {
    if (state?.session_id !== next.session_id) Object.values(renderers).forEach((r) => r.reset());
    state = next;
    $('battleStatus').textContent = next.status === 'finished' ? '对战结束' : labels[next.status];
    $('restartBattle').disabled = pending || !next.config;
    if (!next.config) return;
    $('battleConfig').textContent = `本局 Seed ${next.config.seed} · 每步 ${next.config.dt_ms} ms · 共同预算 ${time(next.config.budget_ms)} · 已推进 ${time(next.elapsed_ms)} · 第 ${next.round} 轮`;
    $('score').textContent = `${next.left.game.deliveries ?? 0} : ${next.right.game.deliveries ?? 0}`;
    $('margin').textContent = next.leader === 'tie' ? '平局' : `${next.leader === 'left' ? '左' : '右'}侧 +${next.delivery_margin}`;
    for (const side of ['left', 'right']) {
      const current = next[side];
      $(side + 'Name').textContent = `${side === 'left' ? '左' : '右'} · ${current.runtime.algorithm}`;
      $(side + 'Status').textContent = `${labels[current.runtime.status]} · ${time(current.game.time_ms)}`;
      $(side + 'Risk').textContent = `风险 ${current.runtime.risk}%`;
      $(side + 'Decision').textContent = `${current.decision.title}：${current.decision.detail} · 无效动作 ${current.runtime.invalid_actions}`;
    }
    if (next.error) showError(next.error);
  }

  function showError(message) {
    $('battleError').textContent = message;
    $('battleError').hidden = !message;
  }

  async function poll() {
    if (fetching || pending) return;
    fetching = true;
    const requestedGeneration = generation;
    try {
      const response = await fetch('/api/battle/state', { cache: 'no-store' });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const next = await response.json();
      if (requestedGeneration !== generation) return;
      showError(controlError);
      render(next);
    } catch (error) {
      if (requestedGeneration === generation) {
        $('battleStatus').textContent = '连接中断';
        showError(`无法获取对战状态：${error.message}`);
      }
    } finally { fetching = false; }
  }

  async function control(command, value) {
    if (pending) return;
    pending = true;
    generation += 1; // Discard an old poll that completes after a restart.
    $('startBattle').disabled = true;
    $('restartBattle').disabled = true;
    controlError = '';
    showError('');
    try {
      const response = await fetch('/api/battle/control', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ command, value }),
      });
      const payload = await response.json();
      if (!response.ok || !payload.ok) throw new Error(payload.error || '启动失败');
    } catch (error) { controlError = error.message; showError(controlError); }
    finally {
      pending = false;
      $('startBattle').disabled = !catalogReady;
      $('restartBattle').disabled = !state?.config;
    }
  }

  $('battleForm').addEventListener('submit', (event) => {
    event.preventDefault();
    const value = { left: $('leftAlgorithm').value, right: $('rightAlgorithm').value,
      seed: Number($('battleSeed').value), dt_ms: Number($('battleDt').value),
      budget_ms: Math.round(Number($('battleBudget').value) * 1000) };
    if (value.budget_ms % value.dt_ms) { showError('共同预算必须是每步时长的整数倍。'); return; }
    control('start', value);
  });
  $('restartBattle').addEventListener('click', () => control('restart'));

  async function loadCatalog() {
    try {
      const response = await fetch('/api/algorithms', { cache: 'no-store' });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const { algorithms } = await response.json();
      for (const side of ['left', 'right']) {
        const select = $(side + 'Algorithm');
        select.replaceChildren();
        algorithms.forEach((item) => {
          const option = document.createElement('option');
          option.value = item.id;
          option.textContent = `${item.name} · ${item.status}`;
          option.disabled = !item.available;
          select.appendChild(option);
        });
        select.value = algorithms.filter((item) => item.available)[side === 'left' ? 0 : 1]?.id
          || algorithms.find((item) => item.available)?.id || '';
      }
      catalogReady = true;
      $('startBattle').disabled = pending;
    } catch (error) {
      showError(`算法库读取失败，正在重试：${error.message}`);
      setTimeout(loadCatalog, 2000);
    }
  }
  function animate() {
    for (const side of ['left', 'right']) renderers[side].draw(state?.[side]);
    requestAnimationFrame(animate);
  }
  loadCatalog();
  poll();
  setInterval(poll, 120);
  requestAnimationFrame(animate);
})();
