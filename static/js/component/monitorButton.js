// 监控按钮更新组件（自动模式：仅状态展示，不提供人工启停）
function updateMonitorButton(monitorRunning) {
  const btn = document.getElementById('btnMonitor');
  if (!btn) return;

  _monitorRunning = monitorRunning;
  State.service.setMonitorRunning(monitorRunning);

  if (monitorRunning) {
    btn.classList.add('running');
    btn.querySelector('span').textContent = '自动监控中';
    btn.querySelector('svg').innerHTML = '<circle cx="8" cy="8" r="6.5" fill="none" stroke="currentColor" stroke-width="1.5"/><circle cx="8" cy="8" r="1.8" fill="currentColor"/>';
  } else {
    btn.classList.remove('running');
    btn.querySelector('span').textContent = '等待自动监控';
    btn.querySelector('svg').innerHTML = '<circle cx="8" cy="8" r="6.5" fill="none" stroke="currentColor" stroke-width="1.5"/><path d="M8 4.5v4l2.5 1.5"/>';
  }
}