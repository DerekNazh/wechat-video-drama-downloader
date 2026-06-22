// 监控按钮更新组件
function updateMonitorButton(monitorRunning) {
  const btn = document.getElementById('btnMonitor');
  if (!btn) return;

  _monitorRunning = monitorRunning;
  State.service.setMonitorRunning(monitorRunning);

  if (monitorRunning) {
    btn.classList.add('running');
    btn.querySelector('span').textContent = '停止监控';
    btn.querySelector('svg').innerHTML = '<rect x="3" y="3" width="10" height="10" rx="1.5"/>';
  } else {
    btn.classList.remove('running');
    btn.querySelector('span').textContent = '一键监控';
    btn.querySelector('svg').innerHTML = '<circle cx="8" cy="8" r="6.5" fill="none" stroke="currentColor" stroke-width="1.5"/><path d="M8 4.5v4l2.5 1.5"/>';
  }
}