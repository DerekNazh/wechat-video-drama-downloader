// ==================== 监控 API ====================
// 后端: /api/monitor/*

// POST /api/monitor/start - 启动监控
export async function startMonitor() {
  const res = await apiFetch("/api/monitor/start", { method: 'POST' });
  return res.json();
}

// POST /api/monitor/stop - 停止监控
export async function stopMonitor() {
  const res = await apiFetch("/api/monitor/stop", { method: 'POST' });
  return res.json();
}